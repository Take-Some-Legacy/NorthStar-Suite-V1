from __future__ import annotations

from noesis.dashboard.templates import render_template


def render_operation_console_section() -> str:
    return render_template("sections/operation_console.html")
