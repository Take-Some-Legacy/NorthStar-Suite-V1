from __future__ import annotations

from noesis.dashboard.templates import render_template


def render_charts_section() -> str:
    return render_template("sections/charts.html")
