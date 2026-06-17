// NOESIS dashboard overview, paths, task and attention renderers.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var State = global.NoesisDashboardState;
  if (!State) return;
  var esc = Dom.esc || function (value) { return String(value == null ? '' : value); };
  var setHtml = Dom.setHtml || function (id, html) { var el = document.getElementById(id); if (el) el.innerHTML = html; };
  var copyText = Dom.copyText || function () {};

  function metricCard(label, value, cls, hint) {
    return '<div class="card"><h3>' + esc(label) + '</h3><div class="metric ' + esc(cls) + '">' + esc(value) + '</div><div class="metric-label">' + esc(hint || '') + '</div></div>';
  }

  function kvRow(key, value) {
    return '<div><span>' + esc(key) + '</span><b>' + esc(value || 'unknown') + '</b></div>';
  }

  function renderCards() {
    var data = State.get();
    var c = data.counts || {}, i = data.insights || {};
    setHtml('cards', [
      metricCard('Runs', c.runs || 0, 'muted', 'indexed proof runs'),
      metricCard('Merge ready', c.mergeReady || 0, 'good', 'focused ready'),
      metricCard('Rejected', c.rejected || 0, (c.rejected || 0) ? 'bad' : 'muted', 'requires attention'),
      metricCard('Whole repo ready', c.wholeRepositoryReady || 0, (c.wholeRepositoryReady || 0) ? 'good' : 'warn', i.headline || 'not global')
    ].join(''));
  }

  function renderWorker() {
    var data = State.get(), w = State.worker(), g = State.nodeGroup();
    setHtml('worker-card', [
      kvRow('role', w.role), kvRow('node', w.machineId || w.nodeId || w.hostId),
      kvRow('root', w.root || data.root), kvRow('surface', 'dashboard.runs'), kvRow('contract', 'noesis.web.v1')
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

  function pathBadge(entry) {
    return '<span class="status ' + (entry.exists ? 'ok' : 'bad') + '">' + (entry.exists ? 'exists' : 'missing') + '</span>';
  }

  function renderPaths() {
    var paths = State.get().paths || {}, bases = paths.baseRoots || {}, derived = paths.derived || {};
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

  function taskStatusBadge(value) {
    var v = String(value || 'unknown');
    return '<span class="status ' + State.statusClass(v) + '">' + esc(v) + '</span>';
  }

  function renderTasks() {
    var tasks = State.get().operatorTasks || {}, summary = tasks.summary || {}, active = tasks.activeObserved || [];
    var summaryRows = [['available actions', summary.availableActions || 0], ['recommended tasks', summary.recommended || 0], ['active observed', summary.activeObserved || 0], ['submission', summary.submissionMode || 'suite-cli']]
      .map(function (e) { return '<div class="timeline-item"><span>' + esc(e[0]) + '</span><b>' + esc(e[1]) + '</b></div>'; }).join('');
    setHtml('task-status', summaryRows + active.map(function (x) {
      return '<div class="timeline-item"><span>' + esc(x.name) + '</span><b>' + taskStatusBadge(x.status) + ' ' + esc(x.runId || '') + '</b></div>';
    }).join(''));
    setHtml('task-recommended', (tasks.recommended || []).map(function (task) {
      return '<button data-copy="' + esc(task.command || '') + '"><b>' + esc(task.title) + '</b> ' + taskStatusBadge(task.status) + '<br><code>' + esc(task.command || '') + '</code></button>';
    }).join(''));
  }

  function renderTimeline(id, run) {
    if (!run) { setHtml(id, '<div class="muted">No run yet.</div>'); return; }
    setHtml(id, [['Run', run.runId], ['Status', run.status], ['Reason', run.reason || run.failedPhase || ''], ['Changed', run.changedFiles], ['Tests', String(run.testsPassed) + '/' + String(run.testsFailed)]]
      .map(function (e) { return '<div class="timeline-item"><span>' + esc(e[0]) + '</span><b>' + esc(e[1]) + '</b></div>'; }).join(''));
  }

  function renderLists() {
    var i = State.get().insights || {}, attention = i.attention && i.attention.length ? i.attention : ['No immediate attention items.'];
    setHtml('attention', attention.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join(''));
    setHtml('reasons', (i.topReasons || []).map(function (x) { return '<li><b>' + esc(x.count) + '</b> × ' + esc(x.reason) + '</li>'; }).join('') || '<li>No failures.</li>');
    renderTimeline('latest-core', i.lastCore);
    renderTimeline('latest-full', i.lastFull);
  }

  function render() {
    renderCards();
    renderWorker();
    renderControls();
    renderPaths();
    renderTasks();
    renderLists();
  }

  global.NoesisDashboardOverview = Object.freeze({render: render, renderTasks: renderTasks, renderPaths: renderPaths});
})(window);
