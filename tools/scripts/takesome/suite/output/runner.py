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


def _status_icon(status: Any, exit_code: Any = None) -> str:
    status_text = str(status or "").lower()
    try:
        code = int(exit_code)
    except Exception:
        code = None
    if status_text in {"ok", "success", "passed"} or code == 0:
        return "✅"
    if status_text in {"timeout", "timed_out"}:
        return "⏱️"
    if status_text in {"failed", "fail", "error"} or (code is not None and code != 0):
        return "❌"
    return "ℹ️"


def _risk_icon(risk: Any) -> str:
    risk_text = str(risk or "").lower()
    if risk_text in {"safe", "readonly", "read_only", "diagnostic"}:
        return "🟢"
    if "write" in risk_text or "mutat" in risk_text:
        return "🟠"
    if "danger" in risk_text or "destructive" in risk_text:
        return "🔴"
    return "⚪"


def _emit_compact_result(envelope: dict[str, Any]) -> None:
    result = envelope.get("result") if isinstance(envelope.get("result"), dict) else {}
    call_note = result.get("call_note") if isinstance(result, dict) else {}
    call_result = result.get("call_result") if isinstance(result, dict) else {}
    summary = envelope.get("summary") if isinstance(envelope.get("summary"), dict) else {}
    artifacts = envelope.get("artifacts") if isinstance(envelope.get("artifacts"), list) else []
    artifact_paths = [item.get("path") for item in artifacts if isinstance(item, dict) and item.get("path")]
    status = call_result.get("status") or envelope.get("status")
    exit_code = call_result.get("exit_code") if call_result else result.get("exit_code")
    status_icon = _status_icon(status, exit_code)
    risk = call_note.get("risk_level") or "<unknown>"
    lines = [
        "🧭 [SUITE CALL]",
        f"🔧 command: {call_note.get('command_id') or envelope.get('action_id')}",
        f"🎯 purpose: {call_note.get('purpose') or summary.get('human') or '<unknown>'}",
        f"{_risk_icon(risk)} risk: {risk}",
        f"📌 expected: {call_note.get('expected_result') or '<unknown>'}",
        "",
        f"{status_icon} [SUITE RESULT]",
        f"🔧 command: {call_result.get('command_id') or envelope.get('action_id')}",
        f"{status_icon} status: {status}",
        f"{status_icon} exit_code: {exit_code}",
        f"⏱️ duration_ms: {call_result.get('duration_ms') or envelope.get('duration_ms')}",
        f"📤 stdout_bytes: {call_result.get('stdout_bytes', 0)}",
        f"📥 stderr_bytes: {call_result.get('stderr_bytes', 0)}",
        f"📝 summary: {call_result.get('summary') or summary.get('human') or ''}",
    ]
    if artifact_paths:
        lines.append("📦 artifacts:")
        for artifact_path in artifact_paths[:8]:
            lines.append(f"  📄 {artifact_path}")
    stdout_tail = str(call_result.get("stdout_tail") or "")
    stderr_tail = str(call_result.get("stderr_tail") or "")
    if stdout_tail:
        lines.extend(["", "📤 [STDOUT TAIL]", stdout_tail])
    if stderr_tail:
        lines.extend(["", "📥 [STDERR TAIL]", stderr_tail])
    sys.stdout.write("\n".join(lines).rstrip() + "\n")

def _write_and_attach(root: Path, envelope: dict[str, Any], output_dir: str | Path | None) -> dict[str, Any]:
    return write_suite_output(root, envelope, output_dir)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _tail_text(text: str, *, max_lines: int = 12, max_chars: int = 2400) -> str:
    if not text:
        return ""
    lines = text.rstrip().splitlines()[-max_lines:]
    tail = "\n".join(lines)
    if len(tail) > max_chars:
        return "…" + tail[-max_chars:]
    return tail


def _make_call_note(action_id: str, action: Any | None) -> dict[str, Any]:
    metadata = _action_metadata(action) if action is not None else {"key": action_id}
    purpose = _first_non_empty(
        metadata.get("detail"),
        metadata.get("label"),
        metadata.get("primary_tag"),
        "Run Suite action through the structured command surface.",
    )
    return {
        "schema": "northstar.suite.call_note.v1",
        "command_id": action_id,
        "label": _first_non_empty(metadata.get("label"), action_id),
        "purpose": purpose,
        "risk_level": _first_non_empty(metadata.get("risk_level"), "unspecified"),
        "target_domain": _first_non_empty(metadata.get("target_domain"), metadata.get("category"), "suite"),
        "expected_result": _first_non_empty(
            metadata.get("output_schema"),
            "exit_code=0 with stdout/stderr captured and diagnostics written",
        ),
        "output_mode": _first_non_empty(metadata.get("output_mode"), "process_exit"),
    }


def _make_call_result(
    *,
    action_id: str,
    status: str,
    exit_code: int,
    duration_ms: int,
    stdout: str,
    stderr: str,
    exception_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    summary_bits = [f"{action_id} finished with status={status}", f"exit_code={exit_code}"]
    if stderr:
        summary_bits.append("stderr captured")
    if exception_payload is not None:
        summary_bits.append(f"exception={exception_payload.get('type')}")
    return {
        "schema": "northstar.suite.call_result.v1",
        "command_id": action_id,
        "status": status,
        "exit_code": int(exit_code),
        "duration_ms": int(duration_ms),
        "stdout_tail": _tail_text(stdout),
        "stderr_tail": _tail_text(stderr),
        "stdout_bytes": len(stdout.encode("utf-8", errors="replace")),
        "stderr_bytes": len(stderr.encode("utf-8", errors="replace")),
        "summary": "; ".join(summary_bits) + ".",
    }


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
    compact = bool(getattr(args, "compact", False))
    timer = Timer()
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    exit_code = 2
    exception_payload: dict[str, Any] | None = None
    action: Any | None = None
    call_note: dict[str, Any] = {
        "schema": "northstar.suite.call_note.v1",
        "command_id": action_id,
        "purpose": "Resolve Suite action metadata before execution.",
        "risk_level": "unknown",
        "target_domain": "suite",
        "expected_result": "resolved Suite action or structured failure envelope",
    }

    try:
        registry = build_registry()
        action = registry.action(action_id)
        call_note = _make_call_note(action_id, action)
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
    call_result = _make_call_result(
        action_id=action_id,
        status=status,
        exit_code=int(exit_code),
        duration_ms=int(duration_ms),
        stdout=stdout,
        stderr=stderr,
        exception_payload=exception_payload,
    )
    result = {
        "exit_code": int(exit_code),
        "stdout": stdout,
        "stderr": stderr,
        "action": _action_metadata(action) if action is not None else {"key": action_id},
        "process_contract": "exit_code_zero_means_ok",
        "declared_output_schema": declared_output_schema,
        "exception": exception_payload,
        "call_note": call_note,
        "call_result": call_result,
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
        summary_human=f"{call_note.get('purpose')} Result: {call_result.get('summary')}",
    )

    ensure_builtin_output_schemas(root)
    envelope["diagnostics"].extend(validate_suite_output_envelope(envelope))
    envelope = _write_and_attach(root, envelope, output_dir)
    if compact:
        _emit_compact_result(envelope)
    else:
        _emit_json(envelope)
    return int(exit_code)
