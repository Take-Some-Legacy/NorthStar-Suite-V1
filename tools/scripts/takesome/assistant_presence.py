from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRESENCE_SCHEMA = "noesis.suite.assistant_presence.v1"
ASSIGNMENT_SCHEMA = "noesis.suite.assigned_task.v1"
EVENT_SCHEMA = "noesis.suite.assistant_presence_event.v1"
VALID_STATES = {"thinking", "working", "waiting", "idle", "assigned", "blocked", "error"}


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def presence_dir(root: Path) -> Path:
    return root / ".takesome" / "intelligence"


def presence_json_path(root: Path) -> Path:
    return presence_dir(root) / "assistant-presence.json"


def assigned_task_path(root: Path) -> Path:
    return presence_dir(root) / "assigned-task.json"


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _text(value: Any) -> str:
    return str(value or "").strip()


def classify_operator_response(response: dict[str, Any] | None) -> dict[str, Any]:
    response = response if isinstance(response, dict) else {}
    text = _text(response.get("text"))
    upper = text.upper()
    if response.get("timed_out"):
        return {"state": "waiting", "kind": "timed_out", "available": False, "summary": "operator response timed out"}
    if not response.get("available"):
        return {"state": "waiting", "kind": "missing", "available": False, "summary": "operator response is not available"}
    if upper.startswith("APPROVE"):
        return {"state": "working", "kind": "approved", "available": True, "summary": "operator approved current request"}
    if upper.startswith("OVERRIDE"):
        return {"state": "working", "kind": "override", "available": True, "summary": "operator supplied override"}
    if upper.startswith("NOTE"):
        return {"state": "waiting", "kind": "note", "available": True, "summary": "operator supplied a note"}
    return {"state": "waiting", "kind": "freeform", "available": True, "summary": "operator supplied freeform response"}


def _recommendations(cycle: dict[str, Any]) -> list[dict[str, Any]]:
    value = cycle.get("recommendations")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def should_assign_task(cycle: dict[str, Any], operator_response: dict[str, Any] | None) -> tuple[bool, str]:
    response = classify_operator_response(operator_response)
    if response["kind"] in {"approved", "override"}:
        return False, "operator already selected next work"
    if response["kind"] in {"missing", "timed_out"}:
        return True, "no operator task is available; assigning the next safe recommendation"
    if response["kind"] == "note" and _recommendations(cycle):
        return True, "operator note received; preserving next recommendation as assignment"
    if not _recommendations(cycle):
        return True, "no recommendation exists; assigning default read-only maintenance"
    return False, "operator response is present"


def build_assigned_task(root: Path, cycle: dict[str, Any], *, reason: str, operator_response: dict[str, Any] | None = None) -> dict[str, Any]:
    top = (_recommendations(cycle) or [{}])[0]
    task_id = _text(top.get("key") or top.get("id") or top.get("action") or top.get("command") or top.get("label"))
    label = _text(top.get("label") or top.get("title") or top.get("summary") or task_id)
    if not task_id:
        task_id = "suite.doctor"
        label = "Run Suite doctor and summarize blocking issues"
        top = {"key": task_id, "risk": "read_only", "reason": "no recommendations were produced"}
    return {
        "schema": ASSIGNMENT_SCHEMA,
        "generated_utc": utc_iso(),
        "cycle": cycle.get("cycle"),
        "status": "assigned",
        "execution_policy": "assignment_only_no_auto_execute",
        "reason": reason,
        "operator_response": classify_operator_response(operator_response),
        "task": {"id": task_id, "label": label, "candidate": top},
        "paths": {"json": _rel(root, assigned_task_path(root)), "markdown": _rel(root, presence_dir(root) / "assigned-task.md")},
    }


def write_assigned_task(root: Path, assignment: dict[str, Any]) -> None:
    json_path = assigned_task_path(root)
    md_path = presence_dir(root) / "assigned-task.md"
    _write_json(json_path, assignment)
    task = assignment.get("task", {}) if isinstance(assignment.get("task"), dict) else {}
    md_path.write_text(
        "\n".join([
            "# Noesis Suite — Assigned Task",
            "",
            f"generated_utc: {assignment.get('generated_utc')}",
            f"cycle: {assignment.get('cycle')}",
            f"execution_policy: {assignment.get('execution_policy')}",
            "",
            f"- id: `{task.get('id', '')}`",
            f"- label: {task.get('label', '')}",
            f"- reason: {assignment.get('reason', '')}",
            "",
            "This is assignment only. The loop must not execute write/destructive work without explicit approval.",
        ]),
        encoding="utf-8",

def update_assistant_presence(
    root: Path,
    *,
    state: str,
    phase: str,
    cycle: dict[str, Any] | None = None,
    message: str = "",
    operator_response: dict[str, Any] | None = None,
    assignment: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cycle = cycle if isinstance(cycle, dict) else {}
    state = state if state in VALID_STATES else "error"
    response = classify_operator_response(operator_response)
    state_dir = presence_dir(root)
    payload = {
        "schema": PRESENCE_SCHEMA,
        "updated_utc": utc_iso(),
        "state": state,
        "phase": phase,
        "message": message,
        "cycle": cycle.get("cycle"),
        "cycle_started_utc": cycle.get("started_utc"),
        "operator_response": response,
        "assignment": assignment,
        "contract": {"check_before_work": True, "idle_policy": "assign_without_auto_execute"},
        "paths": {"json": _rel(root, presence_json_path(root)), "markdown": _rel(root, state_dir / "assistant-presence.md")},
        "extra": extra or {},
    }
    _write_json(presence_json_path(root), payload)
    _append_jsonl(state_dir / "assistant-presence-events.jsonl", {"schema": EVENT_SCHEMA, **payload})
    task = assignment.get("task", {}) if isinstance(assignment, dict) and isinstance(assignment.get("task"), dict) else {}
    lines = [
        "# Noesis Suite — Assistant Presence",
        "",
        f"updated_utc: {payload['updated_utc']}",
        f"state: `{state}`",
        f"phase: `{phase}`",
        f"cycle: `{payload.get('cycle')}`",
        "",
        message or "No message.",
        "",
        f"operator_response: `{response.get('kind')}` — {response.get('summary')}",
        f"assigned_task: `{task.get('id', '')}` {task.get('label', '')}",
