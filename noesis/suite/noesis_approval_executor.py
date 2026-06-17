from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import runpy
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

RULES_PATH = Path("noesis/suite/rules/noesis-approval-executor.md")

try:
    from .noesis_roots import resolve_files, root_context
except Exception:
    _roots = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_roots.py")))
    resolve_files = _roots["resolve_files"]
    root_context = _roots["root_context"]

try:
    from .noesis_source_apply_gate import status as source_apply_status
except Exception:
    _gate = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_source_apply_gate.py")))
    source_apply_status = _gate["status"]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        return ""


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def load_rules(root: Path) -> Dict[str, Any]:
    text = read_text(root / RULES_PATH)
    match = re.search(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        raise RuntimeError(f"Noesis approval executor rules JSON block is missing: {root / RULES_PATH}")
    try:
        value = json.loads(match.group(1))
    except Exception as exc:
        raise RuntimeError(f"Invalid Noesis approval executor rules JSON: {root / RULES_PATH}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Noesis approval executor rules must be an object: {root / RULES_PATH}")
    return value


def configured_paths(root: Path) -> Dict[str, Path]:
    files = resolve_files(root)
    mapping = load_rules(root).get("files")
    if not isinstance(mapping, dict) or not mapping:
        raise RuntimeError("Noesis approval executor file mapping is missing in MD rules")
    missing = [file_key for file_key in mapping.values() if str(file_key) not in files]
    if missing:
        raise RuntimeError("Noesis approval executor file keys are missing from config: " + ", ".join(sorted(map(str, missing))))
    return {str(role): files[str(file_key)] for role, file_key in mapping.items()}


def event(root: Path, kind: str, payload: Dict[str, Any]) -> None:
    paths = configured_paths(root)
    append_jsonl(paths["executor_events"], {"schema": "noesis.suite.approval_executor_event.v1", "created_utc": now_utc(), "kind": kind, **payload})


def sha16(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def run_cmd(root: Path, args: List[str], *, stdin_text: str | None = None, timeout: int = 120) -> Dict[str, Any]:
    started = now_utc()
    try:
        proc = subprocess.run(
            args,
            cwd=str(root),
            input=stdin_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
        )
        return {
            "ok": proc.returncode == 0,
            "started_utc": started,
            "finished_utc": now_utc(),
            "args": args,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
        }
    except Exception as exc:
        return {"ok": False, "started_utc": started, "finished_utc": now_utc(), "args": args, "returncode": -1, "stdout": "", "stderr": str(exc)}


def current_request(root: Path) -> Dict[str, Any]:
    paths = configured_paths(root)
    state = read_json(paths["source_apply_state"])
    request_id = str(state.get("current_request_id") or "").strip()
    if request_id:
        candidate = paths["source_apply_requests_dir"] / f"{request_id}.json"
        data = read_json(candidate)
        if data:
            return data
    return {"id": request_id, "state": state, "request_md": read_text(paths["source_apply_request_current"])}


def approval_id(payload: Dict[str, Any]) -> str:
    return "approval-" + sha16(payload)


def approve(root: Path, *, approved_by: str, reason: str = "", request_id: str = "", approval_text: str = "") -> Dict[str, Any]:
    paths = configured_paths(root)
    rules = load_rules(root)
    policy = rules.get("policy") if isinstance(rules.get("policy"), dict) else {}
    gate = source_apply_status(root)
    capability = gate.get("capability") if isinstance(gate.get("capability"), dict) else {}
    if policy.get("requires_source_apply_capability_enabled", True) and not bool(capability.get("enabled")):
        result = {"ok": False, "reason": "source_apply_capability_disabled", "source_apply_status": gate}
        event(root, "approval_rejected", result)
        return result
    req = current_request(root)
    rid = request_id or str(req.get("id") or req.get("state", {}).get("current_request_id") or "").strip()
    created = now_utc()
    envelope = {
        "schema": "noesis.suite.source_apply_approval.v1",
        "id": "",
        "status": "approved",
        "created_utc": created,
        "updated_utc": created,
        "request_id": rid,
        "approved_by": approved_by,
        "reason": reason,
        "approval_text": approval_text,
        "capability": capability,
        "root_context": root_context(root),
    }
    envelope["id"] = approval_id(envelope)
    write_json(paths["approval_current"], envelope)
    write_json(paths["approvals_dir"] / f"{envelope['id']}.json", envelope)
    state = read_json(paths["executor_state"])
    state.update({
        "schema": "noesis.suite.approval_executor_state.v1",
        "updated_utc": created,
        "status": "approved",
        "current_approval_id": envelope["id"],
        "current_request_id": rid,
    })
    write_json(paths["executor_state"], state)
    event(root, "approved", {"approval_id": envelope["id"], "request_id": rid, "approved_by": approved_by})
    return {"ok": True, "approval": envelope, "approval_path": str(paths["approval_current"])}


def _json_pointer_get(doc: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return doc
    if not pointer.startswith("/"):
        return None
    node = doc
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            node = node.get(token)
        elif isinstance(node, list):
            try:
                node = node[int(token)]
            except Exception:
                return None
        else:
            return None
    return node


def _patch_from_review_packet(root: Path) -> Tuple[str, str]:
    paths = configured_paths(root)
    packet = read_json(paths["review_packet"])
    rules = load_rules(root)
    for pointer in rules.get("patch_sources", []) if isinstance(rules.get("patch_sources"), list) else []:
        value = _json_pointer_get(packet, str(pointer))
        if isinstance(value, str) and value.strip():
            maybe = Path(value)
            if maybe.exists():
                return maybe.read_text(encoding="utf-8", errors="replace"), f"review_packet:{pointer}:file"
            return value, f"review_packet:{pointer}"
    return "", ""


def load_patch(root: Path, *, patch_file: str = "", patch_text: str = "") -> Tuple[str, str]:
    if patch_text.strip():
        return patch_text, "cli_text"
    if patch_file.strip():
        path = Path(patch_file).expanduser()
        if not path.is_absolute():
            path = root / path
        return path.read_text(encoding="utf-8", errors="replace"), str(path)
    return _patch_from_review_packet(root)


def current_approval(root: Path, approval_id_value: str = "") -> Dict[str, Any]:
    paths = configured_paths(root)
    if approval_id_value:
        data = read_json(paths["approvals_dir"] / f"{approval_id_value}.json")
        if data:
            return data
    return read_json(paths["approval_current"])


def workspace_dirty(root: Path) -> Dict[str, Any]:
    result = run_cmd(root, ["git", "status", "--porcelain"], timeout=60)
    dirty = bool(str(result.get("stdout") or "").strip()) if result.get("ok") else True
    return {"dirty": dirty, "result": result}


def changed_files(root: Path) -> List[str]:
    result = run_cmd(root, ["git", "status", "--porcelain"], timeout=60)
    lines = str(result.get("stdout") or "").splitlines()
    out: List[str] = []
    for line in lines:
        if len(line) >= 4:
            out.append(line[3:].strip())
    return out


def validate_after_apply(root: Path, changed: List[str]) -> Dict[str, Any]:
    rules = load_rules(root)
    validation = rules.get("validation") if isinstance(rules.get("validation"), dict) else {}
    checks: List[Dict[str, Any]] = []
    if validation.get("git_status_after_apply", True):
        checks.append({"name": "git_status", **run_cmd(root, ["git", "status", "--short"], timeout=60)})
    py_files = [x for x in changed if x.endswith(".py") and (root / x).exists()]
    if validation.get("python_compile_changed", True) and py_files:
        checks.append({"name": "python_compile_changed", **run_cmd(root, ["py", "-m", "compileall", *py_files], timeout=180)})
    ok = all(bool(item.get("ok")) for item in checks) if checks else True
    return {"schema": "noesis.suite.source_apply_validation_report.v1", "ok": ok, "generated_utc": now_utc(), "changed_files": changed, "checks": checks}


def render_commit_request(envelope: Dict[str, Any]) -> str:
    changed = envelope.get("changed_files") if isinstance(envelope.get("changed_files"), list) else []
    validation = envelope.get("validation") if isinstance(envelope.get("validation"), dict) else {}
    approval = envelope.get("approval") if isinstance(envelope.get("approval"), dict) else {}
    lines = [
        "# Noesis Source Apply — Commit Request",
        "",
        f"generated_utc: {envelope.get('updated_utc', '')}",
        f"execution_id: {envelope.get('id', '')}",
        f"approval_id: {approval.get('id', '')}",
        f"validation_ok: {validation.get('ok')}",
        f"auto_commit: {envelope.get('auto_commit')}",
        f"auto_push: {envelope.get('auto_push')}",
        "",
        "## Changed files",
    ]
    lines.extend([f"- `{item}`" for item in changed] or ["- none"])
    lines.extend([
        "",
        "## Required next gate",
        "Explicit commit approval is required before committing these changes.",
        "Push requires a separate request.",
        "",
    ])
    return "\n".join(lines)


def execute(root: Path, *, approval_id_value: str = "", patch_file: str = "", patch_text: str = "", dry_run: bool = False, allow_dirty: bool = False) -> Dict[str, Any]:
    paths = configured_paths(root)
    rules = load_rules(root)
    policy = rules.get("policy") if isinstance(rules.get("policy"), dict) else {}
    gate = source_apply_status(root)
    capability = gate.get("capability") if isinstance(gate.get("capability"), dict) else {}
    if policy.get("requires_source_apply_capability_enabled", True) and not bool(capability.get("enabled")):
        result = {"ok": False, "reason": "source_apply_capability_disabled", "source_apply_status": gate}
        event(root, "execute_rejected", result)
        return result
    approval = current_approval(root, approval_id_value)
    required_status = str(policy.get("approval_status_required") or "approved")
    if policy.get("requires_explicit_approval_record", True) and approval.get("status") != required_status:
        result = {"ok": False, "reason": "approval_missing_or_not_approved", "approval": approval}
        event(root, "execute_rejected", result)
        return result
    patch, source = load_patch(root, patch_file=patch_file, patch_text=patch_text)
    if not patch.strip():
        result = {"ok": False, "reason": "patch_missing", "approval": approval}
        event(root, "execute_rejected", result)
        return result
    dirty = workspace_dirty(root)
    if policy.get("dirty_workspace_requires_override", True) and dirty.get("dirty") and not allow_dirty:
        result = {"ok": False, "reason": "workspace_dirty", "dirty": dirty}
        event(root, "execute_rejected", {"reason": "workspace_dirty"})
        return result
    created = now_utc()
    execution_id = "exec-" + sha16({"approval": approval.get("id"), "patch": patch, "time": created})
    patch_path = paths["patch_staging_dir"] / f"{execution_id}.patch"
    write_text(patch_path, patch)
    check = run_cmd(root, ["git", "apply", "--check", str(patch_path)], timeout=120)
    applied = False
    apply_result: Dict[str, Any] = {"ok": True, "skipped": True, "reason": "dry_run"}
    if check.get("ok") and not dry_run:
        apply_result = run_cmd(root, ["git", "apply", str(patch_path)], timeout=120)
        applied = bool(apply_result.get("ok"))
    changed = changed_files(root) if applied else []
    validation = validate_after_apply(root, changed) if applied else {"schema": "noesis.suite.source_apply_validation_report.v1", "ok": bool(check.get("ok")), "generated_utc": now_utc(), "checks": [check], "dry_run": dry_run}
    envelope = {
        "schema": "noesis.suite.approval_execution.v1",
        "id": execution_id,
        "created_utc": created,
        "updated_utc": now_utc(),
        "status": "applied" if applied else ("dry_run_checked" if dry_run and check.get("ok") else "failed"),
        "dry_run": dry_run,
        "patch_source": source,
        "patch_path": str(patch_path),
        "approval": approval,
        "capability": capability,
        "git_apply_check": check,
        "git_apply": apply_result,
        "changed_files": changed,
        "validation": validation,
        "auto_commit": bool(capability.get("auto_commit")),
        "auto_push": bool(capability.get("auto_push")),
        "root_context": root_context(root),
    }
    write_json(paths["executions_dir"] / f"{execution_id}.json", envelope)
    write_json(paths["validation_current"], validation)
    write_json(paths["validation_reports_dir"] / f"{execution_id}.json", validation)
    if applied:
        write_text(paths["commit_request_current"], render_commit_request(envelope))
        write_json(paths["commit_requests_dir"] / f"{execution_id}.json", envelope)
    state = {
        "schema": "noesis.suite.approval_executor_state.v1",
        "updated_utc": envelope["updated_utc"],
        "status": envelope["status"],
        "current_execution_id": execution_id,
        "current_approval_id": approval.get("id"),
        "patch_path": str(patch_path),
        "validation_ok": bool(validation.get("ok")),
        "commit_request": str(paths["commit_request_current"]) if applied else "",
    }
    write_json(paths["executor_state"], state)
    event(root, "executed", {"execution_id": execution_id, "status": envelope["status"], "dry_run": dry_run, "applied": applied})
    return {"ok": bool(check.get("ok")) and (dry_run or applied), "execution": envelope, "state": state}


def status(root: Path) -> Dict[str, Any]:
    paths = configured_paths(root)
    approvals = list(paths["approvals_dir"].glob("*.json")) if paths["approvals_dir"].exists() else []
    executions = list(paths["executions_dir"].glob("*.json")) if paths["executions_dir"].exists() else []
    return {
        "schema": "noesis.suite.approval_executor_status.v1",
        "ok": True,
        "generated_utc": now_utc(),
        "source_apply_status": source_apply_status(root),
        "current_approval": read_json(paths["approval_current"]),
        "state": read_json(paths["executor_state"]),
        "counts": {"approvals": len(approvals), "executions": len(executions)},
        "paths": {key: str(value) for key, value in paths.items()},
    }




# --- Noesis admin implicit approval executor override v1 ---
def _implicit_admin_approval(capability: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": "noesis.suite.source_apply_approval.v1",
        "id": "approval-admin-runtime-default",
        "created_utc": now_utc(),
        "status": "approved",
        "approved_by": capability.get("enabled_by", "admin_runtime_default"),
        "reason": capability.get("enable_reason", "Admin runtime default permissions are active."),
        "approval_text": "Implicit approval from admin runtime default permission profile.",
        "source": "admin_runtime_default",
    }


_original_current_approval = current_approval

def current_approval(root: Path, approval_id_value: str = "") -> Dict[str, Any]:
    approval = _original_current_approval(root, approval_id_value)
    if approval:
        return approval
    gate = source_apply_status(root)
    capability = gate.get("capability", {}) if isinstance(gate, dict) else {}
    if capability.get("enabled") and capability.get("approval_required") is False:
        return _implicit_admin_approval(capability)
    return approval

# --- /Noesis admin implicit approval executor override v1 ---


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Noesis approval-gated source apply executor")
    parser.add_argument("command", choices=["status", "approve", "execute"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--approved-by", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--approval-text", default="")
    parser.add_argument("--approval-id", default="")
    parser.add_argument("--patch-file", default="")
    parser.add_argument("--patch-text", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    ns = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(ns.root).resolve()
    if ns.command == "status":
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "approve":
        result = approve(root, approved_by=ns.approved_by, reason=ns.reason, request_id=ns.request_id, approval_text=ns.approval_text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if ns.command == "execute":
        result = execute(root, approval_id_value=ns.approval_id, patch_file=ns.patch_file, patch_text=ns.patch_text, dry_run=ns.dry_run, allow_dirty=ns.allow_dirty)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
