from __future__ import annotations

from noesis.dashboard.templates import render_template


def render_dashboard_runtime_script() -> str:
    return render_template("scripts/dashboard_runtime.html")
