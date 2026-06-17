from __future__ import annotations

from noesis.dashboard.templates import render_template


def render_action_catalog_section() -> str:
    return render_template("sections/action_catalog.html")
