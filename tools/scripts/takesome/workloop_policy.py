from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DECISION_SCHEMA = "noesis.suite.workloop_decision.v1"
WRITE_RISKS = {"writes_workspace", "write", "sudo_write", "destructive", "dangerous"}
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


def _response_kind(response: dict[str, Any] | None) -> str:
    response = response if isinstance(response, dict) else {}
    if response.get("timed_out"):
        return "timed_out"
    if not response.get("available"):
        return "missing"
    text = str(response.get("text") or "").strip().upper()
    if text.startswith("APPROVE"):
        return "approved"
    if text.startswith("OVERRIDE"):
        return "override"
    if text.startswith("NOTE"):
        return "note"
    return "freeform"


def _override_candidate(response: dict[str, Any] | None) -> dict[str, Any] | None:
    response = response if isinstance(response, dict) else {}
    text = str(response.get("text") or "").strip()
    if not text.upper().startswith("OVERRIDE"):
        return None
    value = text.split(":", 1)[1].strip() if ":" in text else text
    if not value:
        return None
    return {
        "action_id": value,
        "label": value,
        "detail": "operator override from operator-response.md",
        "risk_level": "unknown",
        "requires_approval": True,
        "final_score": 1.0,
        "classification_reasons": ["operator override"],
    }


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
    kind = _response_kind(operator_response)
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
    elif kind == "approved":
        reasons.append("operator approved existing request; no replacement assignment")
    elif kind == "override":
        selected = _override_candidate(operator_response)
        assign = selected is not None
        status = "needs_approval"
        execution_policy = "requires_explicit_approval_no_auto_execute"
        reasons.append("operator supplied override; record it as a controlled assignment")
    elif ready:
        selected = candidates[0] if candidates else None
        if selected is None:
            selected = {
                "action_id": "suite.doctor",
                "label": "Run Suite doctor and summarize blocking issues",
                "risk_level": "read_only",
                "requires_approval": False,
                "final_score": 0.5,
                "classification_reasons": ["fallback maintenance task"],
            }
        assign = True
        risk = str(selected.get("risk_level") or "").lower()
        requires_approval = bool(selected.get("requires_approval")) or risk in WRITE_RISKS
        if requires_approval:
            status = "needs_approval"
            execution_policy = "requires_explicit_approval_no_auto_execute"
            reasons.append("selected task may write or is unknown; explicit approval required")
        else:
            status = "assigned"
            execution_policy = "assignment_only_no_auto_execute"
            reasons.append("selected safest available task for current stage")
    else:
        reasons.append("stage is not ready for a new assignment")

    decision = {
        "schema": DECISION_SCHEMA,
        "generated_utc": utc_iso(),
        "cycle": cycle.get("cycle"),
        "stage": stage_name,
        "operator_response_kind": kind,
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
        },
        "memory_summary": memory.get("summary") if isinstance(memory.get("summary"), dict) else {},
    }
    _write_json(intelligence_dir(root) / "workloop-decision.json", decision)
    return decision
