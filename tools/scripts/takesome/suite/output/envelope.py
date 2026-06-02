from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_run_id(action_id: str, started_at: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in action_id).strip("-") or "suite"
    stamp = started_at.replace(":", "").replace("-", "").replace("T", "-").replace("Z", "")
    return f"{safe}-{stamp}"


def status_from_exit_code(exit_code: int) -> str:
    return "ok" if int(exit_code) == 0 else "failed"


def severity_from_status(status: str) -> str:
    if status == "ok":
        return "info"
    if status in {"failed", "error"}:
        return "error"
    return "warn"


def make_envelope(
    *,
    suite_version: str,
    action_id: str,
    run_id: str,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    status: str,
    result_schema: str | None,
    result: Dict[str, Any],
    diagnostics: list[Dict[str, Any]] | None = None,
    artifacts: list[Dict[str, Any]] | None = None,
    next_actions: list[Dict[str, Any]] | None = None,
    profile: Dict[str, Any] | None = None,
    summary_title: str | None = None,
    summary_human: str | None = None,
) -> Dict[str, Any]:
    severity = severity_from_status(status)
    return {
        "schema": "northstar.suite.output.v1",
        "suite_version": suite_version,
        "action_id": action_id,
        "run_id": run_id,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": int(duration_ms),
        "profile": profile or {},
        "summary": {
            "title": summary_title or f"Suite action {action_id} {status}",
            "severity": severity,
            "human": summary_human or f"{action_id} finished with status={status}",
        },
        "result_schema": result_schema,
        "result": result,
        "diagnostics": diagnostics or [],
        "artifacts": artifacts or [],
        "next_actions": next_actions or [],
        "model_hints": {
            "read_order": ["summary", "diagnostics", "result", "artifacts", "next_actions"],
            "truth_source": "result.json and structured result fields",
            "stdout_policy": "stdout/stderr are diagnostic text; prefer typed result fields and declared artifact schemas for machine reasoning.",
            "status_policy": "status=ok means the Suite action returned exit_code 0; failed/error requires reading diagnostics before result.",
        },
    }


class Timer:
    def __init__(self) -> None:
        self.started_monotonic = time.monotonic()
        self.started_at = utc_now()

    def finish(self) -> tuple[str, int]:
        finished_at = utc_now()
        return finished_at, int((time.monotonic() - self.started_monotonic) * 1000)
