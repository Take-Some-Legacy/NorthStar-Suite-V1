from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import runpy
from pathlib import Path
from typing import Any, Dict, Iterable, List

RULES_PATH = Path("tools/scripts/takesome/rules/noesis-task-artifact-writer.md")

try:
    from .noesis_roots import resolve_files, root_context
except Exception:
    _module = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_roots.py")))
    resolve_files = _module["resolve_files"]
    root_context = _module["root_context"]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        return ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


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
        "state": "task_artifact_writer_state",
        "events": "task_artifact_writer_events",
        "proposals_dir": "task_artifact_proposals_dir",
        "drafts_dir": "task_artifact_drafts_dir",
        "review_packets_dir": "task_artifact_review_packets_dir",
        "review_requests_dir": "task_artifact_review_requests_dir",
    }
    missing = [file_key for file_key in required.values() if file_key not in files]
    if missing:
        raise RuntimeError("Noesis task artifact writer missing configured file keys: " + ", ".join(sorted(missing)))
    return {role: files[file_key] for role, file_key in required.items()}


def _flatten_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    final = decision.get("final") if isinstance(decision.get("final"), dict) else {}
    selected = decision.get("selected_candidate") if isinstance(decision.get("selected_candidate"), dict) else {}
    assigned = decision.get("assigned_task") if isinstance(decision.get("assigned_task"), dict) else {}
    return {
        "stage": str(final.get("stage") or decision.get("stage") or ""),
        "assigned_task_id": str(final.get("assigned_task_id") or final.get("selected_action_id") or assigned.get("id") or selected.get("action_id") or ""),
        "selected_action_id": str(final.get("selected_action_id") or selected.get("action_id") or ""),
        "decision_status": str(decision.get("status") or ""),
        "cycle": int(final.get("cycle") or decision.get("cycle") or 0),
        "checks_failed": int(final.get("checks_failed") or decision.get("checks_failed") or 0),
    }


def _match_condition(facts: Dict[str, Any], condition: Dict[str, Any]) -> bool:
    field = str(condition.get("field") or "")
    op = str(condition.get("op") or "")
    current = facts.get(field)
    if op == "in":
        values = condition.get("values") if isinstance(condition.get("values"), list) else []
        return str(current) in {str(x) for x in values}
    if op == "equals":
        return str(current) == str(condition.get("value") or "")
    if op == "nonempty":
        return bool(str(current or ""))
    raise RuntimeError(f"Unsupported Noesis task artifact activation operator: {op}")


def should_write(decision: Dict[str, Any], rules: Dict[str, Any], *, force: bool = False) -> bool:
    if force:
        return True
    activation = rules.get("activation") if isinstance(rules.get("activation"), list) else []
    facts = _flatten_decision(decision)
    return all(_match_condition(facts, item) for item in activation if isinstance(item, dict))


def _attachment_paths(root: Path, rules: Dict[str, Any]) -> List[str]:
    files = resolve_files(root)
    result: List[str] = []
    for key in rules.get("attachment_file_keys", []):
        if isinstance(key, str) and key in files:
            result.append(str(files[key]))
    return result


def _format(template: str, facts: Dict[str, Any], rules: Dict[str, Any], generated_utc: str, attachments: List[str]) -> str:
    data = dict(facts)
    data["generated_utc"] = generated_utc
    data["focus"] = "\n".join(f"- {x}" for x in rules.get("focus", []) if isinstance(x, str))
    data["attachments"] = "\n".join(f"- `{x}`" for x in attachments)
    return template.format(**data)


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
    proposal = (
        f"# {templates['proposal_title']}\n\n"
        f"generated_utc: {generated}\ncycle: {facts['cycle']}\nstage: {facts['stage']}\nassigned_task_id: `{facts['assigned_task_id']}`\nmode: {rules.get('artifact_mode')}\n\n"
        f"## Proposal\n\n{_format(str(templates['proposal_body']), facts, rules, generated, attachments)}\n\n"
        f"## Focus\n\n{_format('{focus}', facts, rules, generated, attachments)}\n\n"
        f"## Attachments\n\n{_format('{attachments}', facts, rules, generated, attachments)}\n"
    )
    draft = (
        f"# {templates['draft_title']}\n\n"
        f"generated_utc: {generated}\ncycle: {facts['cycle']}\nstage: {facts['stage']}\nassigned_task_id: `{facts['assigned_task_id']}`\n\n"
        f"{_format(str(templates['draft_body']), facts, rules, generated, attachments)}\n\n"
        "## Review Gate\n\nThis is an artifact-only draft. Source changes, config writes, commits and pushes require explicit approval.\n"
    )
    request = (
        f"# {templates['review_request_title']}\n\n"
        f"generated_utc: {generated}\ncycle: {facts['cycle']}\nstage: {facts['stage']}\nassigned_task_id: `{facts['assigned_task_id']}`\n\n"
        f"{_format(str(templates['review_request_body']), facts, rules, generated, attachments)}\n"
    )
    packet = {
        "schema": "noesis.suite.task_artifact_packet.v1",
        "generated_utc": generated,
        "mode": rules.get("artifact_mode"),
        "safety": rules.get("safety", {}),
        "facts": facts,
        "root_context": root_context(root),
        "paths": {},
        "attachments": attachments,
    }
    proposal_path = paths["proposals_dir"] / f"{suffix}.md"
    draft_path = paths["drafts_dir"] / f"{suffix}.md"
    packet_path = paths["review_packets_dir"] / f"{suffix}.json"
    request_path = paths["review_requests_dir"] / f"{suffix}.md"
    for path, content in [
        (paths["proposal_current"], proposal),
        (proposal_path, proposal),
        (paths["draft_current"], draft),
        (draft_path, draft),
        (paths["request_current"], request),
        (request_path, request),
    ]:
        write_text(path, content)
    packet["paths"] = {
        "proposal_current": str(paths["proposal_current"]),
        "proposal": str(proposal_path),
        "draft_current": str(paths["draft_current"]),
        "draft": str(draft_path),
        "review_current": str(paths["review_current"]),
        "review_packet": str(packet_path),
        "request_current": str(paths["request_current"]),
        "review_request": str(request_path),
    }
    write_json(paths["review_current"], packet)
    write_json(packet_path, packet)
    event = {"schema": "noesis.suite.task_artifact_writer_event.v1", "generated_utc": generated, "written": True, "facts": facts, "paths": packet["paths"]}
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
        "review_request_exists": paths["request_current"].exists(),
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
