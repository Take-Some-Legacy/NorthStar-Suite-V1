from __future__ import annotations

from noesis.dashboard.templates import render_template


def render_hero_section(*, generated: str = "", root: str = "") -> str:
    return render_template("sections/hero.html", generated=generated, root=root)
