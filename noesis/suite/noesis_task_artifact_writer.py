from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import runpy
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

RULES_PATH = Path("noesis/suite/rules/noesis-task-artifact-writer.md")

try:
    from .noesis_roots import resolve_files, root_context
except Exception:
    _module = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_roots.py")))
    resolve_files = _module["resolve_files"]
    root_context = _module["root_context"]

try:
    from .noesis_audit_log import atomic_write_json, atomic_write_text, append_jsonl as _append_jsonl
except Exception:
    _audit_module = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_audit_log.py")))
    atomic_write_json = _audit_module["atomic_write_json"]
    atomic_write_text = _audit_module["atomic_write_text"]
    _append_jsonl = _audit_module["append_jsonl"]

_AUDIT_CONTEXT: Dict[str, Any] = {"cycle": None, "task": ""}


try:
    from .noesis_task_completion import update_task_completion_state
except Exception:  # pragma: no cover
    update_task_completion_state = None

def _artifact_kind(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".patch") or name.endswith(".diff"):
        return "repo-patch"
    if name.endswith(".json"):
        return "task-artifact-json"
    if name.endswith(".md"):
        return "task-artifact-md"
    return "task-artifact-file"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        return ""


def write_text(path: Path, text: str) -> None:
    atomic_write_text(path, text, kind=_artifact_kind(path), cycle=_AUDIT_CONTEXT.get("cycle"), task=str(_AUDIT_CONTEXT.get("task") or ""), action="write-task-artifact")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: Dict[str, Any]) -> None:
    atomic_write_json(path, value, kind=_artifact_kind(path), cycle=_AUDIT_CONTEXT.get("cycle"), task=str(_AUDIT_CONTEXT.get("task") or ""), action="write-task-artifact-json")


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    _append_jsonl(path, value, kind="task-artifact-event", cycle=_AUDIT_CONTEXT.get("cycle"), task=str(_AUDIT_CONTEXT.get("task") or ""), action="append-task-artifact-event")


def extract_json_block(markdown: str) -> Dict[str, Any]:
    match = re.search(r"```json[^\n]*\n(.*?)\n```", markdown, re.S)
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def load_rules(root: Path) -> Dict[str, Any]:
    rules = extract_json_block(read_text(root / RULES_PATH))
    if rules:
        return rules
    raise RuntimeError(f"Missing or invalid Noesis task artifact writer rules file: {root / RULES_PATH}")


def configured_paths(root: Path) -> Dict[str, Path]:
    files = resolve_files(root)
    required = {
        "decision": "workloop_decision",
        "proposal_current": "task_artifact_current_proposal",
        "draft_current": "task_artifact_current_draft",
        "review_current": "task_artifact_current_review_packet",
        "request_current": "task_artifact_current_review_request",
        "updated_version_current": "task_artifact_current_updated_version",
        "state": "task_artifact_writer_state",
        "events": "task_artifact_writer_events",
        "proposals_dir": "task_artifact_proposals_dir",
        "drafts_dir": "task_artifact_drafts_dir",
        "review_packets_dir": "task_artifact_review_packets_dir",
        "review_requests_dir": "task_artifact_review_requests_dir",
        "updated_versions_dir": "task_artifact_updated_versions_dir",
        "repo_manifest_current": "task_artifact_current_repo_update_manifest",
        "repo_patch_current": "task_artifact_current_repo_patch",
        "repo_files_current_dir": "task_artifact_current_repo_files_dir",
        "repo_manifests_dir": "task_artifact_repo_update_manifests_dir",
        "repo_patches_dir": "task_artifact_repo_patches_dir",
        "repo_files_dir": "task_artifact_repo_files_dir",
    }
    missing = [file_key for file_key in required.values() if file_key not in files]
    if missing:
        raise RuntimeError("Noesis task artifact writer missing configured file keys: " + ", ".join(sorted(missing)))
    return {role: files[file_key] for role, file_key in required.items()}


def _flatten_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    selected = decision.get("selected_candidate") if isinstance(decision.get("selected_candidate"), dict) else {}
    assigned = decision.get("assigned_task") if isinstance(decision.get("assigned_task"), dict) else {}
    return {
        "cycle": int(decision.get("cycle") or 0),
        "stage": str(decision.get("stage") or ""),
        "decision_status": str(decision.get("decision_status") or decision.get("status") or ""),
        "selected_action_id": str(selected.get("action_id") or decision.get("selected_action_id") or ""),
        "assigned_task_id": str(assigned.get("id") or selected.get("action_id") or decision.get("assigned_task_id") or ""),
        "label": str(assigned.get("label") or selected.get("label") or decision.get("label") or ""),
        "reason": str(assigned.get("reason") or selected.get("reason") or decision.get("reason") or ""),
    }


def _match_condition(facts: Dict[str, Any], condition: Dict[str, Any]) -> bool:
    field = str(condition.get("field") or "")
    op = str(condition.get("op") or "")
    value = facts.get(field)
    if op == "nonempty":
        return bool(str(value or "").strip())
    if op == "empty":
        return not bool(str(value or "").strip())
    if op == "equals":
        return str(value or "") == str(condition.get("value") or "")
    if op == "in":
        return str(value or "") in [str(x) for x in condition.get("values", [])]
    return False


def should_write(decision: Dict[str, Any], rules: Dict[str, Any], *, force: bool = False) -> bool:
    if force:
        return True
    facts = _flatten_decision(decision)
    activation = rules.get("activation")
    if not isinstance(activation, list) or not activation:
        return False
    return all(_match_condition(facts, c) for c in activation if isinstance(c, dict))


def _attachment_paths(root: Path, rules: Dict[str, Any]) -> List[str]:
    files = resolve_files(root)
    result = []
    for key in rules.get("attachment_file_keys", []):
        path = files.get(str(key))
        if path:
            result.append(str(path))
    return result


def _format(template: str, facts: Dict[str, Any], rules: Dict[str, Any], generated_utc: str, attachments: List[str]) -> str:
    data = dict(facts)
    data["generated_utc"] = generated_utc
    data["focus"] = "\n".join(f"- {x}" for x in rules.get("focus", []) if isinstance(x, str))
    data["attachments"] = "\n".join(f"- `{x}`" for x in attachments)
    templates = rules.get("templates")
    if isinstance(templates, dict):
        for key, value in templates.items():
            if isinstance(key, str) and isinstance(value, (str, int, float, bool)):
                data.setdefault(key, value)
    return template.format(**data)


def _safe_repo_relative_path(value: str) -> Path:
    text = str(value or "").replace("\\", "/").strip().lstrip("/")
    if not text:
        raise ValueError("empty repository path")
    path = Path(text)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe repository path: {value!r}")
    return path


def _target_root(root: Path, rules: Dict[str, Any]) -> Tuple[str, Path, Dict[str, Any]]:
    repo_cfg = rules.get("repo_file_updates") if isinstance(rules.get("repo_file_updates"), dict) else {}
    key = str(repo_cfg.get("target_root_key") or "workspace_root")
    ctx = root_context(root)
    roots = ctx.get("roots") if isinstance(ctx.get("roots"), dict) else {}
    entry = roots.get(key) if isinstance(roots.get(key), dict) else {}
    path = Path(str(entry.get("path") or "")).resolve()
    if not path.exists():
        raise RuntimeError(f"target repository root does not exist for root key {key!r}: {path}")
    return key, path, ctx


def _unified_diff(rel_path: Path, old_text: str, new_text: str) -> str:
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    if old_text and not old_text.endswith("\n"):
        old_lines.append("\n")
    if new_text and not new_text.endswith("\n"):
        new_lines.append("\n")
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{rel_path.as_posix()}",
            tofile=f"b/{rel_path.as_posix()}",
            lineterm="\n",
        )
    )


def _write_repo_file_update_artifacts(
    root: Path,
    paths: Dict[str, Path],
    rules: Dict[str, Any],
    facts: Dict[str, Any],
    generated: str,
    suffix: str,
    attachments: List[str],
) -> Dict[str, Any]:
    repo_cfg = rules.get("repo_file_updates") if isinstance(rules.get("repo_file_updates"), dict) else {}
    if not repo_cfg.get("enabled", False):
        return {"enabled": False}

    templates = rules.get("templates") if isinstance(rules.get("templates"), dict) else {}
    target_root_key, target_root, ctx = _target_root(root, rules)
    snapshots = repo_cfg.get("file_snapshots")
    if not isinstance(snapshots, list):
        snapshots = []

    shutil.rmtree(paths["repo_files_current_dir"], ignore_errors=True)
    paths["repo_files_current_dir"].mkdir(parents=True, exist_ok=True)

    archive_files_dir = paths["repo_files_dir"] / suffix
    shutil.rmtree(archive_files_dir, ignore_errors=True)
    archive_files_dir.mkdir(parents=True, exist_ok=True)

    changes: List[Dict[str, Any]] = []
    patch_chunks: List[str] = []

    for raw in snapshots:
        if not isinstance(raw, dict):
            continue
        rel_path = _safe_repo_relative_path(str(raw.get("path") or ""))
        template_name = str(raw.get("content_template") or "")
        template = str(templates.get(template_name) or raw.get("content") or "")
        content = _format(template, facts, rules, generated, attachments)
        if not content.endswith("\n"):
            content += "\n"

        staged_current = paths["repo_files_current_dir"] / rel_path
        staged_archive = archive_files_dir / rel_path
        write_text(staged_current, content)
        write_text(staged_archive, content)

        target_file = target_root / rel_path
        old = read_text(target_file)
        diff = _unified_diff(rel_path, old, content)
        status = "unchanged" if old == content else ("create" if not target_file.exists() else "modify")
        if diff.strip():
            patch_chunks.append(diff if diff.endswith("\n") else diff + "\n")

        changes.append(
            {
                "repo_relative_path": rel_path.as_posix(),
                "status": status,
                "target_file": str(target_file),
                "staged_current_file": str(staged_current),
                "staged_archive_file": str(staged_archive),
                "description": str(raw.get("description") or ""),
            }
        )

    patch_text = "\n".join(patch_chunks)
    manifest = {
        "schema": "noesis.suite.repo_file_update_manifest.v1",
        "generated_utc": generated,
        "target_root_key": target_root_key,
        "target_root": str(target_root),
        "facts": facts,
        "root_context": ctx,
        "changes": changes,
        "patch_current": str(paths["repo_patch_current"]),
        "files_current_dir": str(paths["repo_files_current_dir"]),
        "note": "These are repository file update candidates. Applying the patch changes files under the selected target root.",
    }

    manifest_archive = paths["repo_manifests_dir"] / f"{suffix}.json"
    patch_archive = paths["repo_patches_dir"] / f"{suffix}.patch"
    write_json(paths["repo_manifest_current"], manifest)
    write_json(manifest_archive, manifest)
    write_text(paths["repo_patch_current"], patch_text)
    write_text(patch_archive, patch_text)

    return {
        "enabled": True,
        "target_root_key": target_root_key,
        "target_root": str(target_root),
        "manifest_current": str(paths["repo_manifest_current"]),
        "manifest": str(manifest_archive),
        "patch_current": str(paths["repo_patch_current"]),
        "patch": str(patch_archive),
        "files_current_dir": str(paths["repo_files_current_dir"]),
        "files": str(archive_files_dir),
        "change_count": len(changes),
        "patch_nonempty": bool(patch_text.strip()),
    }


def write_from_state(root: Path, *, force: bool = False) -> Dict[str, Any]:
    rules = load_rules(root)
    paths = configured_paths(root)
    decision = read_json(paths["decision"])
    if not should_write(decision, rules, force=force):
        return {"ok": True, "written": False, "reason": "activation_not_matched"}
    facts = _flatten_decision(decision)
    generated = now_utc()
    templates = rules.get("templates") if isinstance(rules.get("templates"), dict) else {}
    attachments = _attachment_paths(root, rules)
    suffix = f"cycle-{facts['cycle']:06d}-" + hashlib.sha256((generated + facts["assigned_task_id"]).encode("utf-8")).hexdigest()[:8]

    repo_update = _write_repo_file_update_artifacts(root, paths, rules, facts, generated, suffix, attachments)

    proposal = (
        f"# {templates['proposal_title']}\n\n"
        f"generated_utc: {generated}\ncycle: {facts['cycle']}\nstage: {facts['stage']}\nassigned_task_id: `{facts['assigned_task_id']}`\nmode: {rules.get('artifact_mode')}\n\n"
        f"## Proposal\n\n{_format(str(templates['proposal_body']), facts, rules, generated, attachments)}\n\n"
        f"## Repository file updates\n\n"
        f"- target_root_key: `{repo_update.get('target_root_key', '')}`\n"
        f"- manifest: `{repo_update.get('manifest_current', '')}`\n"
        f"- patch: `{repo_update.get('patch_current', '')}`\n"
        f"- staged files: `{repo_update.get('files_current_dir', '')}`\n"
        f"- change_count: {repo_update.get('change_count', 0)}\n"
        f"- patch_nonempty: {repo_update.get('patch_nonempty', False)}\n\n"
        f"## Focus\n\n{_format('{focus}', facts, rules, generated, attachments)}\n\n"
        f"## Attachments\n\n{_format('{attachments}', facts, rules, generated, attachments)}\n"
    )
    draft = (
        f"# {templates['draft_title']}\n\n"
        f"generated_utc: {generated}\ncycle: {facts['cycle']}\nstage: {facts['stage']}\nassigned_task_id: `{facts['assigned_task_id']}`\n\n"
        f"{_format(str(templates['draft_body']), facts, rules, generated, attachments)}\n\n"
        "## Repository file target\n\n"
        f"- root: `{repo_update.get('target_root_key', '')}`\n"
        f"- patch: `{repo_update.get('patch_current', '')}`\n"
        f"- staged files: `{repo_update.get('files_current_dir', '')}`\n"
    )
    request = (
        f"# {templates['review_request_title']}\n\n"
        f"generated_utc: {generated}\ncycle: {facts['cycle']}\nstage: {facts['stage']}\nassigned_task_id: `{facts['assigned_task_id']}`\n\n"
        f"{_format(str(templates['review_request_body']), facts, rules, generated, attachments)}\n\n"
        "## Repository file update packet\n\n"
        f"- manifest: `{repo_update.get('manifest_current', '')}`\n"
        f"- patch: `{repo_update.get('patch_current', '')}`\n"
        f"- staged files: `{repo_update.get('files_current_dir', '')}`\n"
    )
    updated_version = (
        f"# {templates['updated_version_title']}\n\n"
        f"generated_utc: {generated}\ncycle: {facts['cycle']}\nstage: {facts['stage']}\nassigned_task_id: `{facts['assigned_task_id']}`\n\n"
        f"{_format(str(templates['updated_version_body']), facts, rules, generated, attachments)}\n\n"
        "## Repository file update\n\n"
        f"- target_root_key: `{repo_update.get('target_root_key', '')}`\n"
        f"- target_root: `{repo_update.get('target_root', '')}`\n"
        f"- manifest: `{repo_update.get('manifest_current', '')}`\n"
        f"- patch: `{repo_update.get('patch_current', '')}`\n"
        f"- staged files: `{repo_update.get('files_current_dir', '')}`\n"
    )
    packet = {
        "schema": "noesis.suite.task_artifact_packet.v1",
        "generated_utc": generated,
        "mode": rules.get("artifact_mode"),
        "safety": rules.get("safety", {}),
        "facts": facts,
        "root_context": root_context(root),
        "repo_file_updates": repo_update,
        "paths": {},
        "attachments": attachments,
    }
    proposal_path = paths["proposals_dir"] / f"{suffix}.md"
    draft_path = paths["drafts_dir"] / f"{suffix}.md"
    packet_path = paths["review_packets_dir"] / f"{suffix}.json"
    request_path = paths["review_requests_dir"] / f"{suffix}.md"
    updated_version_path = paths["updated_versions_dir"] / f"{suffix}.md"
    for path, content in [
        (paths["proposal_current"], proposal),
        (proposal_path, proposal),
        (paths["draft_current"], draft),
        (draft_path, draft),
        (paths["request_current"], request),
        (request_path, request),
        (paths["updated_version_current"], updated_version),
        (updated_version_path, updated_version),
    ]:
        write_text(path, content)
    packet["paths"] = {
        "proposal_current": str(paths["proposal_current"]),
        "proposal": str(proposal_path),
        "draft_current": str(paths["draft_current"]),
        "draft": str(draft_path),
        "updated_version_current": str(paths["updated_version_current"]),
        "updated_version": str(updated_version_path),
        "review_current": str(paths["review_current"]),
        "review_packet": str(packet_path),
        "request_current": str(paths["request_current"]),
        "review_request": str(request_path),
        "repo_update_manifest_current": str(paths["repo_manifest_current"]),
        "repo_patch_current": str(paths["repo_patch_current"]),
        "repo_files_current_dir": str(paths["repo_files_current_dir"]),
    }
    write_json(paths["review_current"], packet)
    write_json(packet_path, packet)
    event = {"schema": "noesis.suite.task_artifact_writer_event.v1", "generated_utc": generated, "written": True, "facts": facts, "paths": packet["paths"], "repo_file_updates": repo_update}
    append_jsonl(paths["events"], event)
    write_json(paths["state"], {"schema": "noesis.suite.task_artifact_writer_state.v1", "updated_utc": generated, "last_event": event})
    return {"ok": True, "written": True, "event": event}


def maybe_write_task_artifacts(root: Path, *, force: bool = False) -> Dict[str, Any]:
    return write_from_state(root, force=force)


def status(root: Path) -> Dict[str, Any]:
    paths = configured_paths(root)
    return {
        "schema": "noesis.suite.task_artifact_writer_status.v1",
        "ok": True,
        "rules": str(root / RULES_PATH),
        "state_exists": paths["state"].exists(),
        "proposal_exists": paths["proposal_current"].exists(),
        "draft_exists": paths["draft_current"].exists(),
        "updated_version_exists": paths["updated_version_current"].exists(),
        "review_request_exists": paths["request_current"].exists(),
        "repo_update_manifest_exists": paths["repo_manifest_current"].exists(),
        "repo_patch_exists": paths["repo_patch_current"].exists(),
        "repo_files_current_exists": paths["repo_files_current_dir"].exists(),
        "state": read_json(paths["state"]),
    }


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Noesis generic task artifact writer")
    parser.add_argument("command", choices=["write-from-state", "status"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--force", action="store_true")
    ns = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(ns.root).resolve()
    if ns.command == "write-from-state":
        print(json.dumps(write_from_state(root, force=ns.force), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "status":
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
