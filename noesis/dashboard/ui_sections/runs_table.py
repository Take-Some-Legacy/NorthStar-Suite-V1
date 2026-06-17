from __future__ import annotations

from noesis.dashboard.templates import render_template

from .patch_inspector import render_patch_inspector_panel


def render_runs_table_section() -> str:
    return render_template(
        "sections/runs_table.html",
        patch_panel=render_patch_inspector_panel(),
    )
