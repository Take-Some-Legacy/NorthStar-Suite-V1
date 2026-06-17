from __future__ import annotations

from .patch_inspector import render_patch_inspector_panel


def render_runs_table_section() -> str:
    patch_panel = render_patch_inspector_panel()
    return '      <section class="card" id="runs-block"><h3>Runs</h3><div class="table-scroll"><table><thead><tr><th>Run</th><th>Status</th><th>Scope</th><th>Phase</th><th>Reason</th><th>Tests</th><th>Changed</th><th>Duration</th><th>Artifacts</th></tr></thead><tbody id="runs"></tbody></table></div><div class="drawer" id="details-block"><div class="detail-head"><h3 id="drawer-title">Run details</h3><div class="mini-actions"><button id="copy-run-json">Copy JSON</button><button id="copy-patch-show">Copy patch command</button><button id="copy-patch-check">Copy check command</button></div></div><div class="detail-grid"><div class="detail-panel"><h3>Report JSON</h3><pre id="drawer-json"></pre></div>{patch_panel}</div></div></section>'.format(patch_panel=patch_panel)
