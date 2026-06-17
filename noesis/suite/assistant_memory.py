from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEMORY_SCHEMA = "noesis.suite.assistant_memory.v1"
CONTROL_DIR = ".takesome"


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def memory_dir(root: Path) -> Path:
    return root / CONTROL_DIR / "intelligence"


def memory_json_path(root: Path) -> Path:
    return memory_dir(root) / "assistant-memory.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl_tail(path: Path, *, limit: int) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []
    items: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            items.append(value)
    return items


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _action_id(value: dict[str, Any]) -> str:
    return str(value.get("action_id") or value.get("key") or value.get("id") or value.get("command") or "").strip()


def load_assistant_memory(root: Path, *, limit: int = 25) -> dict[str, Any]:
    state_dir = memory_dir(root)
    cycles = _read_jsonl_tail(state_dir / "loop-events.jsonl", limit=limit)
    presence_events = _read_jsonl_tail(state_dir / "assistant-presence-events.jsonl", limit=limit)
    last_cycle = _read_json(state_dir / "loop-state.json")
    last_assignment = _read_json(state_dir / "assigned-task.json")
    previous_memory = _read_json(memory_json_path(root))

    recommended_actions: list[str] = []
    stage_counter: Counter[str] = Counter()
    failed_check_counter: Counter[str] = Counter()
    assigned_counter: Counter[str] = Counter()

    for cycle in cycles:
        for candidate in cycle.get("recommendations", []) if isinstance(cycle.get("recommendations"), list) else []:
            if isinstance(candidate, dict):
                action_id = _action_id(candidate)
                if action_id:
                    recommended_actions.append(action_id)
        stage = cycle.get("stage") if isinstance(cycle.get("stage"), dict) else {}
        if stage.get("stage"):
            stage_counter[str(stage.get("stage"))] += 1
        for check in cycle.get("self_checks", []) if isinstance(cycle.get("self_checks"), list) else []:
            if isinstance(check, dict) and not check.get("ok"):
                failed_check_counter[str(check.get("name") or "unnamed_check")] += 1
        assignment = cycle.get("assigned_task") if isinstance(cycle.get("assigned_task"), dict) else {}
        task = assignment.get("task") if isinstance(assignment.get("task"), dict) else {}
        if task.get("id"):
            assigned_counter[str(task.get("id"))] += 1

    assignment_task = last_assignment.get("task") if isinstance(last_assignment.get("task"), dict) else {}
    memory = {
        "schema": MEMORY_SCHEMA,
        "generated_utc": utc_iso(),
        "window": {"cycle_limit": limit, "cycle_count": len(cycles), "presence_event_count": len(presence_events)},
        "last_cycle": {
            "cycle": last_cycle.get("cycle"),
            "started_utc": last_cycle.get("started_utc"),
            "schema": last_cycle.get("schema"),
            "stage": (last_cycle.get("stage") or {}).get("stage") if isinstance(last_cycle.get("stage"), dict) else "",
            "operator_response": (last_cycle.get("operator_response") or {}).get("available") if isinstance(last_cycle.get("operator_response"), dict) else False,
        },
        "last_assignment": {
            "status": last_assignment.get("status"),
            "task_id": assignment_task.get("id"),
            "label": assignment_task.get("label"),
            "generated_utc": last_assignment.get("generated_utc"),
        },
        "frequent_recommendations": Counter(recommended_actions).most_common(10),
        "frequent_assignments": assigned_counter.most_common(10),
        "stage_history": stage_counter.most_common(10),
        "recurring_failed_checks": failed_check_counter.most_common(10),
        "previous_summary": previous_memory.get("summary", {}) if isinstance(previous_memory.get("summary"), dict) else {},
    }
    memory["summary"] = summarize_memory(memory)
    return memory


def summarize_memory(memory: dict[str, Any]) -> dict[str, Any]:
    recurring_failed = memory.get("recurring_failed_checks") if isinstance(memory.get("recurring_failed_checks"), list) else []
    frequent_assignments = memory.get("frequent_assignments") if isinstance(memory.get("frequent_assignments"), list) else []
    stage_history = memory.get("stage_history") if isinstance(memory.get("stage_history"), list) else []
    return {
        "has_history": bool(memory.get("window", {}).get("cycle_count") if isinstance(memory.get("window"), dict) else 0),
        "last_stage": memory.get("last_cycle", {}).get("stage") if isinstance(memory.get("last_cycle"), dict) else "",
        "last_assigned_task": memory.get("last_assignment", {}).get("task_id") if isinstance(memory.get("last_assignment"), dict) else "",
        "recurring_failed_check_count": len(recurring_failed),
        "most_common_stage": stage_history[0][0] if stage_history else "",
        "most_common_assignment": frequent_assignments[0][0] if frequent_assignments else "",
    }


def write_memory_snapshot(root: Path, memory: dict[str, Any], *, cycle: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(memory)
    payload["written_utc"] = utc_iso()
    if isinstance(cycle, dict):
        payload["current_cycle"] = {
            "cycle": cycle.get("cycle"),
            "stage": (cycle.get("stage") or {}).get("stage") if isinstance(cycle.get("stage"), dict) else "",
            "assigned_task": ((cycle.get("assigned_task") or {}).get("task") or {}).get("id") if isinstance(cycle.get("assigned_task"), dict) else "",
        }
    _write_json(memory_json_path(root), payload)
    md = memory_dir(root) / "assistant-memory.md"
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    md.write_text(
        "\n".join([
            "# Noesis Suite — Assistant Memory",
            "",
            f"generated_utc: {payload.get('generated_utc')}",
            f"written_utc: {payload.get('written_utc')}",
            f"has_history: {summary.get('has_history')}",
            f"last_stage: {summary.get('last_stage')}",
            f"last_assigned_task: {summary.get('last_assigned_task')}",
            f"recurring_failed_check_count: {summary.get('recurring_failed_check_count')}",
            "",
        ]),
        encoding="utf-8",
    )
    return payload
