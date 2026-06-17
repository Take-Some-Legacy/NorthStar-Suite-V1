from __future__ import annotations


def render_tasks_card() -> str:
    return '        <div class="card" id="tasks-block"><h3>Task control</h3><p class="muted">Choose a recommended action or open the catalog. The command composer lives in the Operation Console below.</p><div id="task-status" class="timeline"></div><div class="control-grid" id="task-recommended"></div></div>'
