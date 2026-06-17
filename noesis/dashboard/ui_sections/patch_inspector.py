from __future__ import annotations


def render_patch_inspector_panel() -> str:
    return '<div class="detail-panel" id="patch-block"><h3>Patch Inspector</h3><div id="patch-summary" class="muted">Select a run to inspect its patch artifact.</div><div class="patch-stats" id="patch-stats"></div><div class="command-list" id="patch-commands"></div><pre class="patch-preview" id="patch-preview"></pre></div>'
