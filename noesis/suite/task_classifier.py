from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .operator_response import scoring_rules

CLASSIFIER_SCHEMA = "noesis.suite.task_candidates.v1"


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _action_id(candidate: dict[str, Any]) -> str:
    return _text(candidate.get("action_id") or candidate.get("key") or candidate.get("id") or candidate.get("command") or candidate.get("label"))


def _candidate_text(item: dict[str, Any]) -> str:
    parts = [
        _action_id(item),
        _text(item.get("label")),
        _text(item.get("detail")),
        _text(item.get("category")),
        _text(item.get("target_domain")),
    ]
    return " ".join(parts)


def _matches_any(patterns: Any, text: str) -> bool:
    if isinstance(patterns, str):
        patterns = [patterns]
    if not isinstance(patterns, list) or not patterns:
        return True
    return any(isinstance(pattern, str) and re.search(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE) for pattern in patterns)


def _rule_applies(rule: dict[str, Any], *, stage_name: str, signals: dict[str, Any], risk: str, text: str) -> bool:
    stages = rule.get("when_stage_any")
    if isinstance(stages, list) and stages and stage_name not in stages:
        return False
    signal_name = rule.get("when_signal_true")
    if isinstance(signal_name, str) and signal_name and not signals.get(signal_name):
        return False
    risks = rule.get("risk_any")
    if isinstance(risks, list) and risks and risk not in [str(item).lower() for item in risks]:
        return False
    if not _matches_any(rule.get("candidate_regex_any"), text):
        return False
    return True


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
    rule_set = scoring_rules()

    source_recommendations = [item for item in recommendations if isinstance(item, dict)] if isinstance(recommendations, list) else []
    response = stage.get("operator_response") if isinstance(stage.get("operator_response"), dict) else {}
    response_candidate = response.get("candidate") if isinstance(response.get("candidate"), dict) else None
    if response_candidate:
        source_recommendations = [response_candidate, *source_recommendations]

    classified: list[dict[str, Any]] = []
    for index, candidate in enumerate(source_recommendations):
        item = dict(candidate)
        action_id = _action_id(item)
        risk = _text(item.get("risk_level") or item.get("risk") or item.get("riskTier")).lower()
        requires_approval = bool(item.get("requires_approval"))
        base_score = float(item.get("score") or item.get("final_score") or 0.0)
        boost = 0.0
        reasons = list(item.get("reasons") or []) if isinstance(item.get("reasons"), list) else []
        text = _candidate_text(item)

        for rule in rule_set:
            if _rule_applies(rule, stage_name=stage_name, signals=signals, risk=risk, text=text):
                boost += float(rule.get("boost") or 0.0)
                if rule.get("reason"):
                    reasons.append(str(rule.get("reason")))

        if memory_summary.get("last_assigned_task") == action_id:
            boost -= 0.18
            reasons.append("memory penalty: same task was assigned last time")
        if recurring_failed and any(str(row[0]).lower() in text.lower() for row in recurring_failed if isinstance(row, (list, tuple)) and row):
            boost += 0.20
            reasons.append("memory boost: recurring failed check matches task text")

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
        "rules_source": response.get("rules_source", ""),
    }
