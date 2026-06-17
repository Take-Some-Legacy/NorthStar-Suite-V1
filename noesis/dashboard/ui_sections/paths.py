from __future__ import annotations


def render_paths_card() -> str:
    return '        <div class="card" id="paths-block"><h3>Suite paths</h3><p class="muted">Base roots are absolute. Derived paths are displayed as <code>${base}/relative</code> to avoid repeating common prefixes.</p><div id="paths-card"></div><div class="mini-actions"><button id="copy-paths-json">Copy paths JSON</button><button id="copy-runtime-path">Copy runtime config path</button><button class="primary" id="save-paths">Save editable roots</button></div><div class="muted" id="paths-save-status"></div></div>'
