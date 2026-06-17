from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .operator_response import evaluate_operator_response

STAGE_SCHEMA = "noesis.suite.stage.v1"


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def detect_workloop_stage(
    *,
    cycle: dict[str, Any],
    memory: dict[str, Any],
    task_scan: dict[str, Any],
    operator_response: dict[str, Any] | None,
) -> dict[str, Any]:
    response_eval = evaluate_operator_response(operator_response)
    scan_signals = task_scan.get("signals") if isinstance(task_scan.get("signals"), dict) else {}
    repo = task_scan.get("repo") if isinstance(task_scan.get("repo"), dict) else {}
    cycle_info = task_scan.get("cycle") if isinstance(task_scan.get("cycle"), dict) else {}
    intelligence = task_scan.get("intelligence") if isinstance(task_scan.get("intelligence"), dict) else {}

    reasons: list[str] = []
    stage = "idle_no_task"
    state = "idle"
    ready_to_assign = True
    blocked = False
    busy = False

    if repo.get("sensitive_runtime_changes"):
        stage = "blocked_runtime_state_in_worktree"
        state = "blocked"
        ready_to_assign = False
        blocked = True
        reasons.append("runtime-like .takesome files are visible in git status")
    elif response_eval.get("available") and response_eval.get("stage"):
        stage = str(response_eval.get("stage"))
        state = str(response_eval.get("state") or "waiting")
        ready_to_assign = bool(response_eval.get("ready_to_assign"))
        blocked = bool(response_eval.get("blocked"))
        busy = bool(response_eval.get("busy"))
        reasons.extend(str(item) for item in response_eval.get("reasons", []) if item)
        reasons.append("operator-response stage selected by markdown rules")
    elif cycle_info.get("failing_check_count"):
        stage = "self_checks_failing"
        state = "working"
        ready_to_assign = True
        reasons.append("self-checks are failing and should be prioritized")
    elif intelligence.get("assigned_task_status") in {"assigned", "needs_approval"}:
        stage = "assignment_pending"
        state = "waiting"
        ready_to_assign = False
        reasons.append("an assigned task already exists and should be acknowledged first")
    elif scan_signals.get("has_inbox"):
        stage = "operator_inbox_pending"
        state = "working"
        ready_to_assign = True
        reasons.append("operator inbox contains instructions")
    elif scan_signals.get("dirty_worktree"):
        stage = "repo_changes_pending_review"
        state = "working"
        ready_to_assign = True
        reasons.append("git worktree has changes that should be reviewed")
    elif scan_signals.get("has_recommendations"):
        stage = "ready_to_assign_recommendation"
        state = "idle"
        ready_to_assign = True
        reasons.append("safe recommendations exist and no operator task is active")
    else:
        stage = "idle_no_task"
        state = "idle"
        ready_to_assign = True
        reasons.append("no active task detected; default maintenance should be assigned")

    mem_summary = memory.get("summary") if isinstance(memory.get("summary"), dict) else {}
    if mem_summary.get("recurring_failed_check_count"):
        reasons.append("memory reports recurring failed checks")

    return {
        "schema": STAGE_SCHEMA,
        "generated_utc": utc_iso(),
        "stage": stage,
        "state": state,
        "busy": busy,
        "blocked": blocked,
        "ready_to_assign": ready_to_assign,
        "operator_response": response_eval,
        "reasons": reasons,
        "memory_hint": mem_summary,
    }
