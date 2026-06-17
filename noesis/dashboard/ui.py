from __future__ import annotations

import html
import json
from typing import Any

from noesis.dashboard.ui_sections.shell import render_dashboard_shell


DASHBOARD_UI_VERSION = "noesis.dashboard.ui.v4"


def json_script_payload(payload: dict[str, Any]) -> str:
    """Return a JSON payload that is safe to embed in an HTML script tag."""
    return html.escape(json.dumps(payload, ensure_ascii=False), quote=False).replace("</", "<\\/")


def render_html(payload: dict[str, Any]) -> str:
    """Render the NOESIS dashboard HTML shell.

    Server-side markup lives in noesis/dashboard/tpl/*. Python modules only choose
    sections, pass values and keep the public dashboard entrypoint stable.
    """
    return render_dashboard_shell(
        data=json_script_payload(payload),
        generated=str(payload.get("generatedUtc") or ""),
        root=str(payload.get("root") or ""),
    )
