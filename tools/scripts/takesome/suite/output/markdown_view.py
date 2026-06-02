from __future__ import annotations

from typing import Any, Dict


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
        lines.extend(["## Result preview", ""])
        for key in ("exit_code", "action", "process_contract"):
            if key in result:
                lines.append(f"- `{key}`: `{result.get(key)}`")
        stdout = str(result.get("stdout", ""))
        if stdout:
            shown = stdout[:4000]
            if len(stdout) > len(shown):
                shown += "\n... <truncated in markdown view>"
            lines.extend(["", "### stdout", "", "```text", shown, "```", ""])
        stderr = str(result.get("stderr", ""))
        if stderr:
            shown = stderr[:4000]
            if len(stderr) > len(shown):
                shown += "\n... <truncated in markdown view>"
            lines.extend(["", "### stderr", "", "```text", shown, "```", ""])

    return "\n".join(lines).rstrip() + "\n"
