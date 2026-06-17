from __future__ import annotations

import html
import json
from typing import Any

from noesis.dashboard.ui_sections.shell import render_dashboard_shell


DASHBOARD_UI_VERSION = "noesis.dashboard.ui.v3"


def json_script_payload(payload: dict[str, Any]) -> str:
    """Return a JSON payload that is safe to embed in an HTML script tag."""
    return html.escape(json.dumps(payload, ensure_ascii=False), quote=False).replace("</", "<\\/")


def render_html(payload: dict[str, Any]) -> str:
    """Render the NOESIS dashboard HTML shell.

    The heavy markup is intentionally split into ui_sections/* so ui.py remains the
    stable public entrypoint used by publisher.py, verify.py and webapp.py.
    """
    return render_dashboard_shell(
        data=json_script_payload(payload),
        generated=html.escape(str(payload.get("generatedUtc") or "")),
        root=html.escape(str(payload.get("root") or "")),
    )
