from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import rel

TRACE_EVENT_SCHEMA = "noesis.suite.workloop_trace_event.v1"
TRACE_SUMMARY_SCHEMA = "noesis.suite.workloop_trace_summary.v1"


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def count_failed_checks(cycle: dict[str, Any]) -> int:
    checks = cycle.get("self_checks", []) if isinstance(cycle.get("self_checks"), list) else []
    return sum(1 for check in checks if isinstance(check, dict) and not check.get("ok"))


def selected_action_id(decision: dict[str, Any] | None, recommendations: list[Any] | None = None) -> str:
    decision = decision if isinstance(decision, dict) else {}
    selected = decision.get("selected_candidate") if isinstance(decision.get("selected_candidate"), dict) else {}
    if selected.get("action_id"):
        return str(selected.get("action_id"))
    recommendations = recommendations if isinstance(recommendations, list) else []
    if recommendations and isinstance(recommendations[0], dict):
        return str(recommendations[0].get("action_id") or "")
    return ""


def assignment_task_id(assignment: dict[str, Any] | None) -> str:
    if not isinstance(assignment, dict):
        return ""
    task = assignment.get("task") if isinstance(assignment.get("task"), dict) else {}
    return str(task.get("id") or "")


def operator_response_kind(operator_response: dict[str, Any] | None) -> str:
    if not isinstance(operator_response, dict):
        return "none"
    if operator_response.get("kind"):
        return str(operator_response.get("kind"))
    if operator_response.get("available"):
        return "available"
    return "none"


def append_workloop_trace(
    root: Path,
    state_dir: Path,
    *,
    cycle: dict[str, Any] | None,
    phase: str,
    message: str,
    stage: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
    assignment: dict[str, Any] | None = None,
    operator_response: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cycle = cycle if isinstance(cycle, dict) else {}
    stage = stage if isinstance(stage, dict) else (cycle.get("stage") if isinstance(cycle.get("stage"), dict) else {})
    decision = decision if isinstance(decision, dict) else (cycle.get("workloop_decision") if isinstance(cycle.get("workloop_decision"), dict) else {})
    assignment = assignment if isinstance(assignment, dict) else (cycle.get("assigned_task") if isinstance(cycle.get("assigned_task"), dict) else None)
    operator_response = operator_response if isinstance(operator_response, dict) else (cycle.get("operator_response") if isinstance(cycle.get("operator_response"), dict) else {})
    event = {
        "schema": TRACE_EVENT_SCHEMA,
        "generated_utc": utc_iso(),
        "cycle": cycle.get("cycle"),
        "phase": phase,
        "message": message,
        "stage": stage.get("stage", ""),
        "decision_status": decision.get("status", ""),
        "selected_action_id": selected_action_id(decision, cycle.get("recommendations") if isinstance(cycle.get("recommendations"), list) else []),
        "assigned_task_id": assignment_task_id(assignment),
        "checks_failed": count_failed_checks(cycle),
        "operator_response_kind": operator_response_kind(operator_response),
        "paths": {
            "decision": rel(root, state_dir / "workloop-decision.json"),
            "assignment": rel(root, state_dir / "assigned-task.json"),
            "trace": rel(root, state_dir / "workloop-trace.jsonl"),
        },
        "extra": extra or {},
    }
    trace_path = state_dir / "workloop-trace.jsonl"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    write_workloop_trace_summary(state_dir, event)
    return event


def write_workloop_trace_summary(state_dir: Path, event: dict[str, Any]) -> None:
    summary_path = state_dir / "workloop-trace.md"
    lines = [
        "# Noesis Suite — Workloop Trace",
        "",
        f"schema: {TRACE_SUMMARY_SCHEMA}",
        f"updated_utc: {event.get('generated_utc')}",
        f"cycle: {event.get('cycle')}",
        f"phase: {event.get('phase')}",
        f"stage: {event.get('stage')}",
        f"decision_status: {event.get('decision_status')}",
        f"selected_action_id: {event.get('selected_action_id')}",
        f"assigned_task_id: {event.get('assigned_task_id')}",
        f"checks_failed: {event.get('checks_failed')}",
        f"operator_response_kind: {event.get('operator_response_kind')}",
        "",
        "## Current message",
        str(event.get("message") or ""),
        "",
        "## Files",
        "- `.takesome/intelligence/workloop-trace.jsonl` — phase-by-phase trace",
        "- `.takesome/intelligence/loop-events.jsonl` — full cycle payloads",
        "- `.takesome/intelligence/loop-state.json` — latest full cycle state",
        "- `.takesome/intelligence/workloop-decision.json` — final assignment decision",
        "- `.takesome/intelligence/assigned-task.md` — operator-readable assignment",
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")


def finalize_workloop_decision(
    state_dir: Path,
    decision: dict[str, Any],
    *,
    stage: dict[str, Any],
    assignment: dict[str, Any] | None,
    recommendations: list[Any],
    cycle: dict[str, Any],
) -> dict[str, Any]:
    decision["final"] = {
        "source": "final_md_rule_aware_decision_path",
        "stage": stage.get("stage", ""),
        "selected_action_id": selected_action_id(decision, recommendations),
        "assigned_task_id": assignment_task_id(assignment),
        "cycle": cycle.get("cycle"),
        "generated_utc": utc_iso(),
    }
    if assignment is not None:
        decision["assigned_task"] = {
            "id": assignment_task_id(assignment),
            "status": assignment.get("status"),
            "execution_policy": assignment.get("execution_policy"),
        }
    write_json_atomic(state_dir / "workloop-decision.json", decision)
    return decision
