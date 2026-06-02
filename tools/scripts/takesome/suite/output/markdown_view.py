from __future__ import annotations

import json
from typing import Any, Dict

from .formatting import json_block, stream_markdown_section


def render_suite_output_markdown(envelope: Dict[str, Any]) -> str:
    summary = envelope.get("summary") if isinstance(envelope.get("summary"), dict) else {}
    lines = [
        "# Suite action result",
        "",
        f"- schema: `{envelope.get('schema')}`",
        f"- action_id: `{envelope.get('action_id')}`",
        f"- run_id: `{envelope.get('run_id')}`",
        f"- status: `{envelope.get('status')}`",
        f"- result_schema: `{envelope.get('result_schema')}`",
        f"- started_at: `{envelope.get('started_at')}`",
        f"- finished_at: `{envelope.get('finished_at')}`",
        f"- duration_ms: `{envelope.get('duration_ms')}`",
        "",
        "## Summary",
        "",
        str(summary.get("human", "")),
        "",
    ]

    result_for_call = envelope.get("result") if isinstance(envelope.get("result"), dict) else {}
    call_note = result_for_call.get("call_note") if isinstance(result_for_call, dict) else None
    call_result = result_for_call.get("call_result") if isinstance(result_for_call, dict) else None
    if isinstance(call_note, dict) or isinstance(call_result, dict):
        lines.extend(["## Suite call observability", ""])
        if isinstance(call_note, dict):
            lines.extend([
                "### Before call",
                "",
                f"- command: `{call_note.get('command_id')}`",
                f"- purpose: {call_note.get('purpose')}",
                f"- risk_level: `{call_note.get('risk_level')}`",
                f"- target_domain: `{call_note.get('target_domain')}`",
                f"- expected_result: {call_note.get('expected_result')}",
                "",
            ])
        if isinstance(call_result, dict):
            lines.extend([
                "### After call",
                "",
                f"- command: `{call_result.get('command_id')}`",
                f"- status: `{call_result.get('status')}`",
                f"- exit_code: `{call_result.get('exit_code')}`",
                f"- duration_ms: `{call_result.get('duration_ms')}`",
                f"- stdout_bytes: `{call_result.get('stdout_bytes')}`",
                f"- stderr_bytes: `{call_result.get('stderr_bytes')}`",
                f"- summary: {call_result.get('summary')}",
                "",
            ])
            stdout_tail = str(call_result.get("stdout_tail") or "")
            stderr_tail = str(call_result.get("stderr_tail") or "")
            if stdout_tail:
                lines.extend(stream_markdown_section("stdout tail", stdout_tail))
            if stderr_tail:
                lines.extend(stream_markdown_section("stderr tail", stderr_tail))

    diagnostics = envelope.get("diagnostics") or []
    if diagnostics:
        lines.extend(["## Diagnostics", ""])
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            severity = item.get("severity", "info")
            check = item.get("check", "suite")
            message = item.get("message", "")
            path = item.get("path", "")
            suffix = f" `{path}`" if path else ""
            lines.append(f"- **{severity}** `{check}`{suffix}: {message}")
        lines.append("")

    artifacts = envelope.get("artifacts") or []
    if artifacts:
        lines.extend(["## Artifacts", ""])
        for artifact in artifacts:
            if isinstance(artifact, dict):
                lines.append(f"- `{artifact.get('path')}` — {artifact.get('kind', 'artifact')}")
        lines.append("")

    result = envelope.get("result")
    if isinstance(result, dict):
        lines.extend(["## Result", ""])
        for key in ("exit_code", "process_contract", "declared_output_schema"):
            if key in result:
                lines.append(f"- `{key}`: `{result.get(key)}`")
        action = result.get("action")
        if isinstance(action, dict):
            lines.extend(["", "### action", "", json_block(action), ""])
        stdout = str(result.get("stdout", ""))
        if stdout:
            lines.extend(stream_markdown_section(
                "stdout",
                stdout,
                byte_count=_int_or_none(result.get("stdout_bytes")),
                truncated=bool(result.get("stdout_truncated", False)),
            ))
        stderr = str(result.get("stderr", ""))
        if stderr:
            lines.extend(stream_markdown_section(
                "stderr",
                stderr,
                byte_count=_int_or_none(result.get("stderr_bytes")),
                truncated=bool(result.get("stderr_truncated", False)),
            ))
        exception = result.get("exception")
        if exception:
            lines.extend(["### exception", "", json_block(exception), ""])
    elif result is not None:
        lines.extend(["## Result", "", json_block(result), ""])

    next_actions = envelope.get("next_actions") or []
    if next_actions:
        lines.extend(["## Next actions", ""])
        for item in next_actions:
            lines.append(f"- `{item}`")
        lines.append("")

    model_hints = envelope.get("model_hints")
    if isinstance(model_hints, dict):
        lines.extend(["## Model hints", "", json_block(model_hints), ""])

    return "\n".join(lines).rstrip() + "\n"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None
