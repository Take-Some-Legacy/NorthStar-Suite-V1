from __future__ import annotations


def render_action_catalog_section() -> str:
    return """      <section class="card" id="actions-block">
        <h3>Suite action catalog</h3>
        <p class="muted">Pick an action and copy the Suite command. Execution is explicit through Suite CLI.</p>
        <section class="toolbar action-toolbar">
          <input id="action-search" placeholder="Search action id, title, group..." />
          <select id="action-group"><option value="">all groups</option></select>
          <select id="action-danger"><option value="">all levels</option><option>normal</option><option>safe</option><option>high</option></select>
          <button id="run-selected-action">Run selected</button>
          <span class="inline-status" id="action-run-status" data-status="idle">No operation started.</span>
          <button class="primary" id="copy-selected-action">Copy selected</button>
        </section>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Action</th><th>Group</th><th>Level</th><th>Title</th><th>Command</th></tr></thead>
            <tbody id="actions-table"></tbody>
          </table>
        </div>
      </section>"""
