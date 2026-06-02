from __future__ import annotations

import contextlib
import io
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from .envelope import Timer, make_envelope, make_run_id, status_from_exit_code
from .schemas import ensure_builtin_output_schemas, validate_suite_output_envelope
from .writer import write_suite_output
from ...registry.suite_action_registry import discover_suite_actions
from ...registry.suite_bridge_menu import render_bridge_menu_actions


def _action_metadata(action: Any) -> dict[str, Any]:
    if action is None:
        return {}
    chips: list[str] = []
    try:
        chips = list(action.chips())
    except Exception:
        chips = []
    target_domain = getattr(action, "target_domain", "") or getattr(action, "scope", "")
    risk_level = getattr(action, "risk_level", "") or getattr(action, "risk", "")
    profile = getattr(action, "profile", "") or getattr(action, "context_tag", "")
    return {
        "key": getattr(action, "key", ""),
        "label": getattr(action, "label", ""),
        "detail": getattr(action, "detail", ""),
        "primary_tag": getattr(action, "primary_tag", ""),
        "category": getattr(action, "category", ""),
        "target_domain": target_domain,
        "risk_level": risk_level,
        "profile": profile,
        "chips": chips,
        "progress_total": int(getattr(action, "progress_total", 1) or 1),
        "progress_unit": getattr(action, "progress_unit", "step"),
        "output_schema": getattr(action, "output_schema", None),
        "output_mode": getattr(action, "output_mode", "process_exit"),
    }


def _emit_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_and_attach(root: Path, envelope: dict[str, Any], output_dir: str | Path | None) -> dict[str, Any]:
    return write_suite_output(root, envelope, output_dir)


def emit_actions_json(root: Path, suite_version: str, build_registry: Callable[[], Any], *, output_dir: str = "") -> int:
    timer = Timer()
    registry = discover_suite_actions(root)
    actions = render_bridge_menu_actions(registry)
    finished_at, duration_ms = timer.finish()
    run_id = make_run_id("suite.list_actions", timer.started_at)
    envelope = make_envelope(
        suite_version=suite_version,
        action_id="suite.list_actions",
        run_id=run_id,
        started_at=timer.started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status="ok" if registry.ok else "failed",
        result_schema="northstar.suite.action_list.v1",
        result={
            "actions": actions,
            "action_count": len(actions),
            "descriptor_action_count": len(registry.actions),
            "registry_schema": "northstar.suite_action_registry.v1",
            "registry_ok": registry.ok,
            "validation": [item.as_dict() for item in registry.validation],
        },
        summary_title="Suite action list exported",
        summary_human=f"Exported {len(actions)} descriptor-backed Suite actions with output schema metadata.",
    )
    ensure_builtin_output_schemas(root)
    envelope["diagnostics"].extend(validate_suite_output_envelope(envelope))
    envelope = _write_and_attach(root, envelope, output_dir)
    _emit_json(envelope)
    return 0 if registry.ok else 2


def run_suite_action_structured(
    root: Path,
    args: Any,
    suite_version: str,
    build_registry: Callable[[], Any],
    *,
    ensure_env: Callable[[Path], None] | None = None,
    apply_delete: Callable[[Path], Any] | None = None,
) -> int:
    action_id = str(getattr(args, "run", "") or "").strip()
    output_dir = str(getattr(args, "output_dir", "") or "")
    timer = Timer()
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    exit_code = 2
    exception_payload: dict[str, Any] | None = None
    action: Any | None = None

    try:
        registry = build_registry()
        action = registry.action(action_id)
        if action is None:
            raise KeyError(f"Unknown Suite action: {action_id}")
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            if apply_delete is not None:
                apply_delete(root)
            if ensure_env is not None:
                try:
                    ensure_env(root, suite_version=suite_version)
                except TypeError as exc:
                    if "suite_version" not in str(exc):
                        raise
                    ensure_env(root)
            exit_code = int(registry.run(root, action))
    except BaseException as exc:
        exit_code = 1
        exception_payload = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

    finished_at, duration_ms = timer.finish()
    status = status_from_exit_code(exit_code)
    run_id = make_run_id(action_id or "suite.run", timer.started_at)
    stdout = stdout_buffer.getvalue()
    stderr = stderr_buffer.getvalue()

    diagnostics: list[dict[str, Any]] = []
    if exception_payload is not None:
        diagnostics.append({
            "severity": "error",
            "check": "suite.action.exception",
            "path": action_id,
            "message": exception_payload["message"],
        })
    elif exit_code != 0:
        diagnostics.append({
            "severity": "error",
            "check": "suite.action.exit_code",
            "path": action_id,
            "message": f"Suite action returned non-zero exit code {exit_code}",
        })

    declared_output_schema = getattr(action, "output_schema", None) if action is not None else None
    result_schema = "northstar.suite.process_result.v1"
    result = {
        "exit_code": int(exit_code),
        "stdout": stdout,
        "stderr": stderr,
        "action": _action_metadata(action) if action is not None else {"key": action_id},
        "process_contract": "exit_code_zero_means_ok",
        "declared_output_schema": declared_output_schema,
        "exception": exception_payload,
    }

    envelope = make_envelope(
        suite_version=suite_version,
        action_id=action_id,
        run_id=run_id,
        started_at=timer.started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status=status,
        result_schema=result_schema,
        result=result,
        diagnostics=diagnostics,
        summary_title=f"Suite action {action_id} {status}",
        summary_human=f"{action_id} finished with exit_code={exit_code}.",
    )

    ensure_builtin_output_schemas(root)
    envelope["diagnostics"].extend(validate_suite_output_envelope(envelope))
    envelope = _write_and_attach(root, envelope, output_dir)
    _emit_json(envelope)
    return int(exit_code)
