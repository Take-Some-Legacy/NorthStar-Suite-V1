from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


CLASSIFIER_SCHEMA = "noesis.suite.task_candidates.v1"
WRITE_RISKS = {"writes_workspace", "write", "sudo_write", "destructive", "dangerous"}
SAFE_RISKS = {"read_only", "safe", "diagnostics", "none", ""}


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _action_id(candidate: dict[str, Any]) -> str:
    return _text(candidate.get("action_id") or candidate.get("key") or candidate.get("id") or candidate.get("command") or candidate.get("label"))


def classify_task_candidates(
    recommendations: list[dict[str, Any]],
    *,
    stage: dict[str, Any],
    memory: dict[str, Any],
    task_scan: dict[str, Any],
) -> dict[str, Any]:
    stage_name = _text(stage.get("stage"))
    memory_summary = memory.get("summary") if isinstance(memory.get("summary"), dict) else {}
    recurring_failed = memory.get("recurring_failed_checks") if isinstance(memory.get("recurring_failed_checks"), list) else []
    signals = task_scan.get("signals") if isinstance(task_scan.get("signals"), dict) else {}

    classified: list[dict[str, Any]] = []
    for index, candidate in enumerate(recommendations if isinstance(recommendations, list) else []):
        if not isinstance(candidate, dict):
            continue
        item = dict(candidate)
        action_id = _action_id(item)
        risk = _text(item.get("risk_level") or item.get("risk") or item.get("riskTier")).lower()
        requires_approval = risk in WRITE_RISKS
        base_score = float(item.get("score") or 0.0)
        boost = 0.0
        reasons = list(item.get("reasons") or []) if isinstance(item.get("reasons"), list) else []
        text = " ".join([action_id, _text(item.get("label")), _text(item.get("detail")), _text(item.get("category"))]).lower()

        if stage_name in {"self_checks_failing", "blocked_runtime_state_in_worktree"} and any(word in text for word in ("doctor", "validate", "status", "check", "audit")):
            boost += 0.35
            reasons.append("stage boost: diagnostics needed")
        if signals.get("dirty_worktree") and any(word in text for word in ("git", "diff", "status", "patch")):
            boost += 0.25
            reasons.append("stage boost: worktree has changes")
        if memory_summary.get("last_assigned_task") == action_id:
            boost -= 0.18
            reasons.append("memory penalty: same task was assigned last time")
        if recurring_failed and any(str(row[0]).lower() in text for row in recurring_failed if isinstance(row, (list, tuple)) and row):
            boost += 0.20
            reasons.append("memory boost: recurring failed check matches task text")
        if requires_approval:
            boost -= 0.30
            reasons.append("policy penalty: write/destructive task requires explicit approval")
        if risk in SAFE_RISKS or any(word in text for word in ("status", "list", "validate", "doctor")):
            boost += 0.12
            reasons.append("policy boost: safe/diagnostic task")

        item.update({
            "action_id": action_id,
            "risk_level": risk or "unknown",
            "requires_approval": requires_approval,
            "base_score": base_score,
            "policy_boost": round(boost, 6),
            "final_score": round(base_score + boost - (index * 0.001), 6),
            "classification_reasons": reasons,
        })
        classified.append(item)

    classified.sort(key=lambda row: float(row.get("final_score") or 0.0), reverse=True)
    return {
        "schema": CLASSIFIER_SCHEMA,
        "generated_utc": utc_iso(),
        "stage": stage_name,
        "count": len(classified),
        "candidates": classified,
        "top_action_id": classified[0].get("action_id") if classified else "",
    }
