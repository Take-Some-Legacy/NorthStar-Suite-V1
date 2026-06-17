from __future__ import annotations

from .action_catalog import render_action_catalog_section
from .charts import render_charts_section
from .client_runtime import render_dashboard_runtime_script
from .hero import render_hero_section
from .operation_console import render_operation_console_section
from .paths import render_paths_card
from .runs_table import render_runs_table_section
from .tasks import render_tasks_card


HTML_LANG = "en"


def _render_head() -> str:
    return """  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NOESIS Operator Dashboard</title>
  <link rel="stylesheet" href="/dashboard/static/noesis-dashboard.css" />
  <link rel="stylesheet" href="/dashboard/static/input-edit.css" />"""


def _render_topbar() -> str:
    return """  <div class="topbar">
    <button class="burger" id="burger">☰</button>
    <div><b>NOESIS</b> <span class="muted">Operator Dashboard</span></div>
  </div>"""


def _nav_button(target: str, label: str, index: int, *, active: bool = False) -> str:
    class_name = " class=\"active\"" if active else ""
    return f'        <button{class_name} data-jump="{target}">{label} <span>{index:02d}</span></button>'


def _render_sidebar() -> str:
    nav_items = [
        ("overview", "Overview"),
        ("worker-block", "Worker"),
        ("cluster-block", "Cluster"),
        ("paths-block", "Paths"),
        ("tasks-block", "Tasks"),
        ("controls-block", "Suite Control"),
        ("operation-console", "Console"),
        ("actions-block", "Actions"),
        ("attention-block", "Attention"),
        ("runs-block", "Runs"),
        ("details-block", "Details"),
        ("patch-block", "Patch"),
    ]
    buttons = "\n".join(
        _nav_button(target, label, index, active=index == 1)
        for index, (target, label) in enumerate(nav_items, start=1)
    )
    return f"""    <aside>
      <div class="brand">
        <div class="sigil logo-sigil" aria-label="NOESIS">
          <img src="/dashboard/static/noesis-logo.svg" alt="NOESIS" loading="eager" decoding="async" />
        </div>
        <div><h1>NOESIS</h1><p>Operator Console</p></div>
      </div>
      <div class="nav">
{buttons}
      </div>
      <div class="side-note">
        Web contract: <code>noesis.web.v1</code><br />
        Surface: <code>dashboard.runs</code><br />
        No surface owns the server. Every surface implements the web contract.
      </div>
    </aside>"""


def _render_hero(generated: str, root: str) -> str:
    return render_hero_section().replace("__GENERATED__", generated).replace("__ROOT__", root)


def _render_identity_cards() -> str:
    return """      <section class="grid" id="cards"></section>

      <section class="triple">
        <div class="card" id="worker-block"><h3>Current worker</h3><div class="kv" id="worker-card"></div></div>
        <div class="card" id="cluster-block"><h3>Node group</h3><div class="kv" id="cluster-card"></div></div>
        <div class="card" id="controls-block"><h3>Suite control</h3><div class="control-grid" id="control-card"></div></div>
      </section>"""


def _render_paths_tasks_row() -> str:
    return f"""      <section class="split" id="paths-tasks-row">
{render_paths_card()}
{render_tasks_card()}
      </section>"""


def _render_attention_sections() -> str:
    return """      <section class="split" id="attention-block">
        <div class="card"><h3>Attention</h3><ul class="list" id="attention"></ul></div>
        <div class="card"><h3>Top rejection reasons</h3><ul class="list" id="reasons"></ul></div>
      </section>

      <section class="split">
        <div class="card"><h3>Latest core</h3><div id="latest-core" class="timeline"></div></div>
        <div class="card"><h3>Latest full-repo</h3><div id="latest-full" class="timeline"></div></div>
      </section>"""


def _render_runs_toolbar() -> str:
    return """      <section class="toolbar" id="runs-toolbar">
        <input id="search" placeholder="Search runId, status, scope, reason..." />
        <select id="scope"><option value="">all scopes</option><option>noesis-core</option><option>full-repo</option></select>
        <select id="status"><option value="">all statuses</option><option>merge_ready</option><option>rejected</option><option>unknown</option></select>
        <button class="primary" id="refresh">Refresh API</button>
      </section>"""


def _render_main(generated: str, root: str) -> str:
    sections = [
        render_charts_section(),
        _render_hero(generated, root),
        _render_identity_cards(),
        _render_paths_tasks_row(),
        render_operation_console_section(),
        render_action_catalog_section(),
        _render_attention_sections(),
        _render_runs_toolbar(),
        render_runs_table_section(),
        '      <footer>Dashboard publication uses <code>noesis.dashboard.publisher</code>. Local serving uses <code>noesis.web.server</code>.</footer>',
    ]
    return "    <main>\n" + "\n\n".join(sections) + "\n    </main>"


def _render_scripts(data: str) -> str:
    return f"""  <script id="runs-data" type="application/json">{data}</script>
{render_dashboard_runtime_script()}
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="/dashboard/static/charts.js"></script>
  <script src="/dashboard/static/operations.js"></script>"""


def render_dashboard_shell(*, data: str, generated: str, root: str) -> str:
    return f"""<!doctype html>
<html lang="{HTML_LANG}">
<head>
{_render_head()}
</head>
<body>
{_render_topbar()}
  <div class="shell">
{_render_sidebar()}
{_render_main(generated, root)}
  </div>
{_render_scripts(data)}
</body>
</html>
"""
