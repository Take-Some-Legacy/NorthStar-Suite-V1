from __future__ import annotations


def render_dashboard_runtime_script() -> str:
    return r"""  <script>
(function () {
  'use strict';

  var dataNode = document.getElementById('runs-data');
  var DATA = dataNode ? JSON.parse(dataNode.textContent || '{}') : {};
  window.NOESIS_DASHBOARD = DATA;
  window.__NOESIS_RUNS__ = DATA;

  function $(id) { return document.getElementById(id); }
  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c];
    });
  }
  function statusClass(value) { return ['merge_ready', 'rejected'].indexOf(value) >= 0 ? value : 'unknown'; }
  function duration(ms) { return !ms ? '' : (ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's'); }
  function worker() { return DATA.worker || DATA.node || {}; }
  function nodeGroup() { return worker().nodeGroup || worker().cluster || {}; }
  function setHtml(id, html) { var el = $(id); if (el) el.innerHTML = html; }
  function copyText(text) { try { if (navigator.clipboard) navigator.clipboard.writeText(text || ''); } catch (_) {} }

  function metricCard(label, value, cls, hint) {
    return '<div class="card"><h3>' + esc(label) + '</h3><div class="metric ' + esc(cls) + '">' + esc(value) + '</div><div class="metric-label">' + esc(hint || '') + '</div></div>';
  }
  function kvRow(key, value) { return '<div><span>' + esc(key) + '</span><b>' + esc(value || 'unknown') + '</b></div>'; }

  function renderCards() {
    var c = DATA.counts || {}, i = DATA.insights || {};
    setHtml('cards', [
      metricCard('Runs', c.runs || 0, 'muted', 'indexed proof runs'),
      metricCard('Merge ready', c.mergeReady || 0, 'good', 'focused ready'),
      metricCard('Rejected', c.rejected || 0, (c.rejected || 0) ? 'bad' : 'muted', 'requires attention'),
      metricCard('Whole repo ready', c.wholeRepositoryReady || 0, (c.wholeRepositoryReady || 0) ? 'good' : 'warn', i.headline || 'not global')
    ].join(''));
  }

  function renderWorker() {
    var w = worker(), g = nodeGroup();
    setHtml('worker-card', [
      kvRow('role', w.role), kvRow('node', w.machineId || w.nodeId || w.hostId),
      kvRow('root', w.root || DATA.root), kvRow('surface', 'dashboard.runs'), kvRow('contract', 'noesis.web.v1')
    ].join(''));
    setHtml('cluster-card', [
      kvRow('enabled', g.enabled), kvRow('id', g.id || g.groupId || g.clusterId), kvRow('role', g.role || w.role),
      kvRow('members', g.memberCount == null ? (g.members || []).length : g.memberCount), kvRow('mode', g.mode || g.networkMode)
    ].join(''));
  }

  function renderControls() {
    var commands = [
      ['Refresh dashboard index', 'python -m noesis runs index'],
      ['Serve operator dashboard', 'python -m noesis runs serve --open'],
      ['Run focused gate', 'python -m noesis noesis-test-dev-repo verify --scope noesis-core --apply-current-diff'],
      ['Run full gate skeleton', 'python -m noesis noesis-test-dev-repo verify --scope full-repo --apply-current-diff']
    ];
    setHtml('control-card', commands.map(function (entry) {
      return '<button data-copy="' + esc(entry[1]) + '"><b>' + esc(entry[0]) + '</b><br><code>' + esc(entry[1]) + '</code></button>';
    }).join(''));
    document.querySelectorAll('#control-card [data-copy]').forEach(function (button) {
      button.addEventListener('click', function () {
        copyText(button.getAttribute('data-copy'));
        button.classList.add('primary');
        window.setTimeout(function () { button.classList.remove('primary'); }, 700);
      });
    });
  }

  function pathBadge(entry) { return '<span class="status ' + (entry.exists ? 'ok' : 'bad') + '">' + (entry.exists ? 'exists' : 'missing') + '</span>'; }
  function renderPaths() {
    var paths = DATA.paths || {}, bases = paths.baseRoots || {}, derived = paths.derived || {};
    function editField(key, entry) {
      var tag = entry.editable ? 'editable' : 'read-only';
      return '<article class="edit-field path-row base-path"><header><label>' + esc(key) + '</label>' + pathBadge(entry) + '</header>' +
        '<input data-path-key="' + esc(key) + '" data-original="' + esc(entry.path || '') + '" value="' + esc(entry.path || '') + '" ' + (entry.editable ? '' : 'readonly') + ' />' +
        '<div class="edit-meta"><span>' + esc(tag) + '</span><span>baseRoot</span></div></article>';
    }
    function computedField(key, entry) {
      var expr = entry.base ? '${' + entry.base + '}/' + (entry.relative || '') : (entry.path || '');
      return '<article class="edit-field path-row derived-path"><header><label>' + esc(key) + '</label>' + pathBadge(entry) + '</header>' +
        '<div class="edit-expression">' + esc(expr) + '</div><div class="edit-meta"><span>computed</span><span>' + esc(entry.relative || '') + '</span></div></article>';
    }
    setHtml('paths-card', [
      '<section class="edit-section"><h4>Base roots</h4><div class="edit-grid">' + Object.keys(bases).map(function (k) { return editField(k, bases[k] || {}); }).join('') + '</div></section>',
      '<section class="edit-section"><h4>Derived paths</h4><div class="edit-grid">' + Object.keys(derived).map(function (k) { return computedField(k, derived[k] || {}); }).join('') + '</div></section>'
    ].join(''));
    document.querySelectorAll('#paths-card [data-path-key]').forEach(function (input) {
      input.addEventListener('input', function () { input.closest('.edit-field').classList.toggle('edit-dirty', input.value !== input.getAttribute('data-original')); });
    });
  }

  function taskStatusBadge(value) { var v = String(value || 'unknown'); return '<span class="status ' + statusClass(v) + '">' + esc(v) + '</span>'; }
  function renderTasks() {
    var tasks = DATA.operatorTasks || {}, summary = tasks.summary || {}, active = tasks.activeObserved || [];
    var summaryRows = [['available actions', summary.availableActions || 0], ['recommended tasks', summary.recommended || 0], ['active observed', summary.activeObserved || 0], ['submission', summary.submissionMode || 'suite-cli']]
      .map(function (e) { return '<div class="timeline-item"><span>' + esc(e[0]) + '</span><b>' + esc(e[1]) + '</b></div>'; }).join('');
    setHtml('task-status', summaryRows + active.map(function (x) {
      return '<div class="timeline-item"><span>' + esc(x.name) + '</span><b>' + taskStatusBadge(x.status) + ' ' + esc(x.runId || '') + '</b></div>';
    }).join(''));
    setHtml('task-recommended', (tasks.recommended || []).map(function (task) {
      return '<button data-copy="' + esc(task.command || '') + '"><b>' + esc(task.title) + '</b> ' + taskStatusBadge(task.status) + '<br><code>' + esc(task.command || '') + '</code></button>';
    }).join(''));
  }

  var SELECTED_ACTION_COMMAND = '';
  function actionGroups() {
    var seen = {}, actions = (DATA.operatorTasks || {}).availableActions || [];
    actions.forEach(function (action) { if (action.group) seen[action.group] = true; });
    return Object.keys(seen).sort();
  }
  function filteredActions() {
    var actions = (DATA.operatorTasks || {}).availableActions || [];
    var q = (($('action-search') || {}).value || '').toLowerCase().trim();
    var group = (($('action-group') || {}).value || '');
    var danger = (($('action-danger') || {}).value || '');
    return actions.filter(function (a) {
      if (group && a.group !== group) return false;
      if (danger && a.dangerLevel !== danger) return false;
      return !q || [a.id, a.title, a.group, a.description].join(' ').toLowerCase().indexOf(q) !== -1;
    }).slice(0, 120);
  }
  function selectActionRow(row) {
    document.querySelectorAll('[data-action-row]').forEach(function (item) {
      item.classList.remove('action-selected', 'selected', 'active', 'is-selected');
      item.removeAttribute('aria-selected');
    });
    row.classList.add('action-selected', 'selected', 'active', 'is-selected');
    row.setAttribute('aria-selected', 'true');
    SELECTED_ACTION_COMMAND = row.getAttribute('data-copy') || '';
  }
  function renderActionCatalog() {
    var groupSelect = $('action-group');
    if (groupSelect && groupSelect.options.length <= 1) {
      groupSelect.innerHTML = '<option value="">all groups</option>' + actionGroups().map(function (g) { return '<option>' + esc(g) + '</option>'; }).join('');
    }
    var rows = filteredActions();
    setHtml('actions-table', rows.map(function (a, index) {
      return '<tr class="action-row" data-action-row="' + index + '" data-action-id="' + esc(a.id || '') + '" data-copy="' + esc(a.suiteCommand || '') + '">' +
        '<td><span class="action-id">' + esc(a.id) + '</span></td><td>' + esc(a.group) + '</td><td>' + esc(a.dangerLevel) + '</td><td>' + esc(a.title) + '</td><td><code>' + esc(a.suiteCommand || '') + '</code></td></tr>';
    }).join(''));
    document.querySelectorAll('[data-action-row]').forEach(function (row, index) {
      row.addEventListener('click', function () { selectActionRow(row); });
      if (index === 0 && !SELECTED_ACTION_COMMAND) selectActionRow(row);
    });
  }

  function renderTimeline(id, run) {
    if (!run) { setHtml(id, '<div class="muted">No run yet.</div>'); return; }
    setHtml(id, [['Run', run.runId], ['Status', run.status], ['Reason', run.reason || run.failedPhase || ''], ['Changed', run.changedFiles], ['Tests', String(run.testsPassed) + '/' + String(run.testsFailed)]]
      .map(function (e) { return '<div class="timeline-item"><span>' + esc(e[0]) + '</span><b>' + esc(e[1]) + '</b></div>'; }).join(''));
  }
  function renderLists() {
    var i = DATA.insights || {}, attention = i.attention && i.attention.length ? i.attention : ['No immediate attention items.'];
    setHtml('attention', attention.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join(''));
    setHtml('reasons', (i.topReasons || []).map(function (x) { return '<li><b>' + esc(x.count) + '</b> × ' + esc(x.reason) + '</li>'; }).join('') || '<li>No failures.</li>');
    renderTimeline('latest-core', i.lastCore);
    renderTimeline('latest-full', i.lastFull);
  }

  function filteredRuns() {
    var q = ($('search') ? $('search').value : '').toLowerCase().trim();
    var scope = $('scope') ? $('scope').value : '';
    var status = $('status') ? $('status').value : '';
    return (DATA.recent || []).slice().reverse().filter(function (run) {
      if (scope && run.scope !== scope) return false;
      if (status && run.status !== status) return false;
      return !q || [run.runId, run.status, run.scope, run.reason, run.failedPhase, run.readinessKind].join(' ').toLowerCase().indexOf(q) !== -1;
    });
  }
  function artifactLinks(run) {
    var artifacts = run.artifacts || [];
    if (!artifacts.length) return '';
    return '<div class="artifact-list">' + artifacts.slice(0, 5).map(function (a) { return '<a href="' + esc(a.url) + '" target="_blank">' + esc(a.name) + '</a>'; }).join('') + '</div>';
  }
  function renderRuns() {
    setHtml('runs', filteredRuns().map(function (r) {
      return '<tr><td><a href="#" class="run-id" data-run="' + esc(r.runId) + '">' + esc(r.runId) + '</a></td><td><span class="status ' + statusClass(r.status) + '">' + esc(r.status) + '</span></td><td>' + esc(r.scope) + '</td><td>' + esc(r.failedPhase || '') + '</td><td>' + esc(r.reason || '') + '</td><td>' + esc(r.testsPassed) + '/' + esc(r.testsFailed) + '</td><td>' + esc(r.changedFiles) + '</td><td>' + esc(duration(r.durationMs)) + '</td><td>' + artifactLinks(r) + '</td></tr>';
    }).join(''));
    document.querySelectorAll('[data-run]').forEach(function (link) {
      link.addEventListener('click', function (event) { event.preventDefault(); showRun(link.getAttribute('data-run')); });
    });
  }

  var CURRENT_RUN_JSON = '';
  var CURRENT_PATCH_COMMANDS = {};
  function renderPatch(item) {
    CURRENT_PATCH_COMMANDS = (item && item.commands) || {};
    if (!item || !item.ok) {
      setHtml('patch-summary', '<div class="patch-empty">No patch artifact for this run. ' + esc((item && item.error) || '') + '</div>');
      setHtml('patch-stats', ''); setHtml('patch-commands', '');
      if ($('patch-preview')) $('patch-preview').textContent = '';
      return;
    }
    var s = item.stats || {};
    setHtml('patch-summary', '<b>' + esc(item.patchName) + '</b><br><span class="muted">' + esc(item.patchPath) + '</span>');
    setHtml('patch-stats', [['Files', s.fileCount || 0], ['Additions', s.additions || 0], ['Deletions', s.deletions || 0], ['Hunks', s.hunks || 0]].map(function (e) {
      return '<div class="patch-stat"><b>' + esc(e[1]) + '</b><span>' + esc(e[0]) + '</span></div>';
    }).join(''));
    var cmds = item.commands || {};
    setHtml('patch-commands', [['Inspect', cmds.inspect], ['Show patch', cmds.show], ['Dry-run check', cmds.dryRun], ['Explicit integrate', cmds.apply]].filter(function (e) { return e[1]; }).map(function (e) {
      return '<button data-copy="' + esc(e[1]) + '"><b>' + esc(e[0]) + '</b><br><code>' + esc(e[1]) + '</code></button>';
    }).join(''));
    document.querySelectorAll('#patch-commands [data-copy]').forEach(function (button) { button.addEventListener('click', function () { copyText(button.getAttribute('data-copy')); }); });
    if ($('patch-preview')) $('patch-preview').textContent = item.preview || '';
  }

  function showRun(id) {
    var payload = (DATA.recent || []).filter(function (run) { return run.runId === id; })[0] || {runId: id};
    return fetch('/api/runs/' + encodeURIComponent(id)).then(function (response) { return response.ok ? response.json() : payload; }).catch(function () { return payload; })
      .then(function (runPayload) {
        payload = runPayload;
        return fetch('/api/runs/' + encodeURIComponent(id) + '/patch').then(function (response) { return response.json(); }).catch(function () {
          return {ok:false, error:'patch_api_unavailable', commands:{inspect:'python -m noesis runs patch ' + id + ' --json', show:'python -m noesis runs patch ' + id + ' --show', dryRun:'python -m noesis runs patch ' + id + ' --check', apply:'python -m noesis runs patch ' + id + ' --apply'}};
        });
      }).then(function (patchPayload) {
        CURRENT_RUN_JSON = JSON.stringify(payload, null, 2);
        if ($('drawer-title')) $('drawer-title').textContent = 'Run ' + id;
        if ($('drawer-json')) $('drawer-json').textContent = CURRENT_RUN_JSON;
        renderPatch(patchPayload);
        if ($('details-block')) { $('details-block').classList.add('open'); $('details-block').scrollIntoView({behavior:'smooth', block:'start'}); }
      });
  }

  function bindExternalOperations() { if (window.NoesisOperations && typeof window.NoesisOperations.bind === 'function') window.NoesisOperations.bind(); }
  function renderAll() { renderCards(); renderWorker(); renderControls(); renderPaths(); renderTasks(); renderActionCatalog(); renderLists(); renderRuns(); bindExternalOperations(); }
  function refresh() {
    return fetch('/dashboard/data.json?refresh=1').then(function (response) { return response.ok ? response.json() : Promise.reject(new Error('dashboard data unavailable')); })
      .catch(function () { return fetch('/api/runs?refresh=1').then(function (response) { return response.ok ? response.json() : DATA; }); })
      .then(function (nextData) { DATA = nextData || DATA; window.NOESIS_DASHBOARD = DATA; window.__NOESIS_RUNS__ = DATA; renderAll(); })
      .catch(renderAll);
  }

  function bindStaticControls() {
    ['search', 'scope', 'status'].forEach(function (id) { if ($(id)) $(id).addEventListener('input', renderRuns); });
    ['action-search', 'action-group', 'action-danger'].forEach(function (id) { if ($(id)) $(id).addEventListener('input', renderActionCatalog); });
    if ($('copy-selected-action')) $('copy-selected-action').addEventListener('click', function () { copyText(SELECTED_ACTION_COMMAND); });
    if ($('copy-paths-json')) $('copy-paths-json').addEventListener('click', function () { copyText(JSON.stringify(DATA.paths || {}, null, 2)); });
    if ($('copy-runtime-path')) $('copy-runtime-path').addEventListener('click', function () { copyText(((((DATA.paths || {}).entries || {}).runtimeConfig || {}).path) || ''); });
    if ($('refresh')) $('refresh').addEventListener('click', refresh);
    if ($('copy-run-json')) $('copy-run-json').addEventListener('click', function () { copyText(CURRENT_RUN_JSON); });
    if ($('copy-patch-show')) $('copy-patch-show').addEventListener('click', function () { copyText(CURRENT_PATCH_COMMANDS.show); });
    if ($('copy-patch-check')) $('copy-patch-check').addEventListener('click', function () { copyText(CURRENT_PATCH_COMMANDS.dryRun); });
    if ($('burger')) $('burger').addEventListener('click', function () { document.body.classList.toggle('nav-open'); });
    document.querySelectorAll('[data-jump]').forEach(function (button) {
      button.addEventListener('click', function () {
        document.querySelectorAll('[data-jump]').forEach(function (item) { item.classList.remove('active'); });
        button.classList.add('active');
        document.body.classList.remove('nav-open');
        var target = document.getElementById(button.dataset.jump);
        if (target) target.scrollIntoView({behavior:'smooth'});
      });
    });
  }

  window.NoesisDashboard = Object.freeze({refresh: refresh, renderAll: renderAll, showRun: showRun});
  bindStaticControls();
  renderAll();
})();
  </script>"""
