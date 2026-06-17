from __future__ import annotations

from noesis.dashboard.templates import render_template


def render_tasks_card() -> str:
    return render_template("sections/tasks_card.html")
