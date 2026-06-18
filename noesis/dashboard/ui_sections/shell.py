from __future__ import annotations

from noesis.dashboard.templates import render_template

from .action_catalog import render_action_catalog_section
from .charts import render_charts_section
from .client_runtime import render_dashboard_runtime_script
from .hero import render_hero_section
from .operation_console import render_operation_console_section
from .paths import render_paths_card
from .runs_table import render_runs_table_section
from .tasks import render_tasks_card


HTML_LANG = "en"
FEEDBACK_BRIDGE_ENABLED = True


def _render_head() -> str:
    return render_template("head.html")


def _render_topbar() -> str:
    return render_template("topbar.html")


def _nav_button(target: str, label: str, index: int, *, active: bool = False) -> str:
    return render_template(
        "nav_button.html",
        active_class="active" if active else "",
        aria_current="page" if active else "false",
        target=target,
        label=label,
        index=f"{index:02d}",
    )


def _render_sidebar() -> str:
    nav_items = [
        ("live-charts", "Live"),
        ("overview", "Overview"),
        ("operator-brief", "Brief"),
        ("cards", "Metrics"),
        ("readiness-block", "Readiness"),
        ("worker-block", "Worker"),
        ("cluster-block", "Cluster"),
        ("paths-block", "Paths"),
        ("tasks-block", "Tasks"),
        ("controls-block", "Suite Control"),
        ("operation-console", "Console"),
        ("actions-block", "Actions"),
        ("attention-block", "Attention"),
        ("activity-block", "Activity"),
        ("runs-block", "Runs"),
        ("details-block", "Details"),
        ("patch-block", "Patch"),
    ]
    nav_buttons = "\n".join(
        _nav_button(target, label, index, active=index == 1)
        for index, (target, label) in enumerate(nav_items, start=1)
    )
    return render_template("sidebar.html", nav_buttons=nav_buttons)


def _render_identity_cards() -> str:
    return render_template("sections/identity_cards.html")


def _render_paths_tasks_row() -> str:
    return render_template(
        "sections/paths_tasks_row.html",
        paths_card=render_paths_card(),
        tasks_card=render_tasks_card(),
    )


def _render_attention_sections() -> str:
    return render_template("sections/attention_sections.html")


def _render_runs_toolbar() -> str:
    return render_template("sections/runs_toolbar.html")


def _render_main(generated: str, root: str) -> str:
    sections = [
        render_charts_section(),
        render_hero_section(generated=generated, root=root),
        _render_identity_cards(),
        _render_paths_tasks_row(),
        render_operation_console_section(),
        render_action_catalog_section(),
        _render_attention_sections(),
        _render_runs_toolbar(),
        render_runs_table_section(),
        render_template("sections/footer.html"),
    ]
    return render_template("main.html", sections="\n\n".join(sections))


def _render_scripts(data: str) -> str:
    return render_template(
        "scripts.html",
        data=data,
        runtime_script=render_dashboard_runtime_script(),
    )


def render_dashboard_shell(*, data: str, generated: str, root: str) -> str:
    return render_template(
        "shell.html",
        html_lang=HTML_LANG,
        head=_render_head(),
        topbar=_render_topbar(),
        sidebar=_render_sidebar(),
        main=_render_main(generated, root),
        scripts=_render_scripts(data),
    )
