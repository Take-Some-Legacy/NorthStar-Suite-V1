from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json_object(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def operator_request_pending(request_path: Path, response_path: Path) -> bool:
    if not request_path.exists():
        return False
    try:
        request_text = request_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        request_text = ""
    if "Approve, override" not in request_text and "APPROVE" not in request_text:
        return False
    if not response_path.exists():
        return True
    try:
        return response_path.stat().st_mtime <= request_path.stat().st_mtime
    except OSError:
        return True


def should_call_cloud(*, planner_state_path: Path, request_path: Path, response_path: Path, scheduled: bool) -> tuple[bool, dict[str, Any]]:
    now = time.time()
    state = read_json_object(planner_state_path)
    next_attempt = float(state.get("next_attempt_epoch") or 0)
    pending = operator_request_pending(request_path, response_path)
    gate = {
        "scheduled": bool(scheduled),
        "request_pending": bool(pending),
        "next_attempt_epoch": next_attempt,
        "reason": "allowed",
    }
    if not scheduled:
        gate["reason"] = "not_scheduled"
        return False, gate
    if pending:
        gate["reason"] = "waiting_for_operator_response"
        return False, gate
    if next_attempt > now:
        gate["reason"] = "cloud_backoff"
        return False, gate
    return True, gate


def update_state(planner_state_path: Path, cycle: dict[str, Any]) -> None:
    cloud = cycle.get("openai", {}) if isinstance(cycle.get("openai"), dict) else {}
    prior = read_json_object(planner_state_path)
    now = time.time()
    state = {
        "schema": "northstar.suite_intelligence.cloud_planner_state.v1",
        "updated_epoch": now,
        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "last_cycle": cycle.get("cycle"),
        "model": cloud.get("model"),
        "source": cloud.get("source"),
        "attempted": bool(cloud.get("attempted")),
        "ok": bool(cloud.get("ok")),
        "last_error": str(cloud.get("error") or "")[-2000:],
        "gate_reason": cloud.get("gate_reason"),
        "next_attempt_epoch": float(prior.get("next_attempt_epoch") or 0),
        "next_attempt_utc": prior.get("next_attempt_utc", ""),
        "backoff_reason": prior.get("backoff_reason", ""),
        "last_backoff_sec": int(prior.get("last_backoff_sec") or 0),
    }
    error = str(cloud.get("error") or "").lower()
    if cloud.get("ok"):
        state["next_attempt_epoch"] = 0
        state["next_attempt_utc"] = ""
        state["backoff_reason"] = ""
        state["last_backoff_sec"] = 0
    elif cloud.get("attempted"):
        if "insufficient_quota" in error or "exceeded your current quota" in error:
            seconds = 6 * 60 * 60
            state["backoff_reason"] = "insufficient_quota"
        elif "429" in error or "rate" in error:
            seconds = min(60 * 60, max(300, int(state["last_backoff_sec"] or 300) * 2))
            state["backoff_reason"] = "rate_limited"
        else:
            seconds = 5 * 60
            state["backoff_reason"] = "cloud_error"
        state["last_backoff_sec"] = seconds
        next_epoch = now + seconds
        state["next_attempt_epoch"] = next_epoch
        state["next_attempt_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(next_epoch))
    write_json_object(planner_state_path, state)
