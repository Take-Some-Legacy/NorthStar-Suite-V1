from __future__ import annotations

from .action_catalog import render_action_catalog_section
from .charts import render_charts_section
from .hero import render_hero_section
from .operation_console import render_operation_console_section
from .patch_inspector import render_patch_inspector_panel
from .paths import render_paths_card
from .runs_table import render_runs_table_section
from .shell import render_dashboard_shell
from .tasks import render_tasks_card

__all__ = [
    "render_action_catalog_section",
    "render_charts_section",
    "render_dashboard_shell",
    "render_hero_section",
    "render_operation_console_section",
    "render_patch_inspector_panel",
    "render_paths_card",
    "render_runs_table_section",
    "render_tasks_card",
]
