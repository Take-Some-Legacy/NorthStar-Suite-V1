from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .operator_response import default_assignment_candidate

DECISION_SCHEMA = "noesis.suite.workloop_decision.v1"
CONTROL_DIR = ".takesome"


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def intelligence_dir(root: Path) -> Path:
    return root / CONTROL_DIR / "intelligence"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def decide_next_assignment(
    *,
    root: Path,
    cycle: dict[str, Any],
    memory: dict[str, Any],
    task_scan: dict[str, Any],
    stage: dict[str, Any],
    classified: dict[str, Any],
    operator_response: dict[str, Any] | None,
) -> dict[str, Any]:
    response = stage.get("operator_response") if isinstance(stage.get("operator_response"), dict) else {}
    response_policy = response.get("policy") if isinstance(response.get("policy"), dict) else {}
    kind = str(response.get("kind") or "missing")
    stage_name = str(stage.get("stage") or "")
    ready = bool(stage.get("ready_to_assign"))
    blocked = bool(stage.get("blocked"))
    candidates = classified.get("candidates") if isinstance(classified.get("candidates"), list) else []
    selected = None
    assign = False
    status = "not_assigned"
    execution_policy = "assignment_only_no_auto_execute"
    reasons: list[str] = []

    if blocked:
        reasons.append("stage is blocked; do not assign new executable work")
    elif response_policy and response_policy.get("assign") is False:
        reasons.append("operator-response markdown policy disabled new assignment")
    elif response.get("candidate"):
        selected = response.get("candidate")
        assign = bool(response_policy.get("assign", True))
        status = str(response_policy.get("status") or ("needs_approval" if selected.get("requires_approval") else "assigned"))
        execution_policy = str(response_policy.get("execution_policy") or "assignment_only_no_auto_execute")
        reasons.append("selected candidate from operator-response markdown rules")
    elif ready:
        selected = candidates[0] if candidates else None
        if selected is None:
            selected = default_assignment_candidate(root=root)
        assign = True
        requires_approval = bool(selected.get("requires_approval"))
        status = "needs_approval" if requires_approval else "assigned"
        execution_policy = "requires_explicit_approval_no_auto_execute" if requires_approval else "assignment_only_no_auto_execute"
        reasons.append("selected safest available task for current stage")
    else:
        reasons.append("stage is not ready for a new assignment")

    decision = {
        "schema": DECISION_SCHEMA,
        "generated_utc": utc_iso(),
        "cycle": cycle.get("cycle"),
        "stage": stage_name,
        "operator_response_kind": kind,
        "operator_response_intent": response.get("intent", ""),
        "assign": assign,
        "status": status,
        "execution_policy": execution_policy,
        "selected_candidate": selected,
        "reasons": reasons,
        "policy": {
            "auto_execute": False,
            "dangerous_requires_explicit_approval": True,
            "write_requires_explicit_approval": True,
            "assignment_is_not_execution": True,
            "operator_rules_source": response.get("rules_source", ""),
        },
        "memory_summary": memory.get("summary") if isinstance(memory.get("summary"), dict) else {},
    }
    _write_json(intelligence_dir(root) / "workloop-decision.json", decision)
    return decision
