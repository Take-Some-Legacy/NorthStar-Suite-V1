from __future__ import annotations

from noesis.dashboard.templates import render_template


def render_paths_card() -> str:
    return render_template("sections/paths_card.html")
