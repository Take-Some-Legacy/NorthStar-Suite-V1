from __future__ import annotations

from noesis.dashboard.templates import render_template


def render_patch_inspector_panel() -> str:
    return render_template("sections/patch_inspector.html")
