// NOESIS dashboard runs table and patch inspector.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var State = global.NoesisDashboardState;
  if (!State) return;
  var esc = Dom.esc || function (value) { return String(value == null ? '' : value); };
  var setHtml = Dom.setHtml || function (id, html) { var el = document.getElementById(id); if (el) el.innerHTML = html; };
  var copyText = Dom.copyText || function () {};
  var CURRENT_RUN_JSON = '';
  var CURRENT_PATCH_COMMANDS = {};

  function $(id) { return Dom.$ ? Dom.$(id) : document.getElementById(id); }

  function filteredRuns() {
    var q = ($('search') ? $('search').value : '').toLowerCase().trim();
    var scope = $('scope') ? $('scope').value : '';
    var status = $('status') ? $('status').value : '';
    return (State.get().recent || []).slice().reverse().filter(function (run) {
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
      return '<tr><td><a href="#" class="run-id" data-run="' + esc(r.runId) + '">' + esc(r.runId) + '</a></td><td><span class="status ' + State.statusClass(r.status) + '">' + esc(r.status) + '</span></td><td>' + esc(r.scope) + '</td><td>' + esc(r.failedPhase || '') + '</td><td>' + esc(r.reason || '') + '</td><td>' + esc(r.testsPassed) + '/' + esc(r.testsFailed) + '</td><td>' + esc(r.changedFiles) + '</td><td>' + esc(State.duration(r.durationMs)) + '</td><td>' + artifactLinks(r) + '</td></tr>';
    }).join(''));
    document.querySelectorAll('[data-run]').forEach(function (link) {
      link.addEventListener('click', function (event) { event.preventDefault(); showRun(link.getAttribute('data-run')); });
    });
  }

  function renderPatch(item) {
    CURRENT_PATCH_COMMANDS = (item && item.commands) || {};
    if (!item || !item.ok) {
      setHtml('patch-summary', '<div class="patch-empty">No patch artifact for this run. ' + esc((item && item.error) || '') + '</div>');
      setHtml('patch-stats', '');
      setHtml('patch-commands', '');
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
    document.querySelectorAll('#patch-commands [data-copy]').forEach(function (button) {
      button.addEventListener('click', function () { copyText(button.getAttribute('data-copy')); });
    });
    if ($('patch-preview')) $('patch-preview').textContent = item.preview || '';
  }

  function showRun(id) {
    var payload = (State.get().recent || []).filter(function (run) { return run.runId === id; })[0] || {runId: id};
    return State.track(fetch('/api/runs/' + encodeURIComponent(id))).then(function (response) { return response.ok ? response.json() : payload; }).catch(function () { return payload; })
      .then(function (runPayload) {
        payload = runPayload;
        return State.track(fetch('/api/runs/' + encodeURIComponent(id) + '/patch')).then(function (response) { return response.json(); }).catch(function () {
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

  global.NoesisDashboardRuns = Object.freeze({
    render: renderRuns,
    showRun: showRun,
    copyRunJson: function () { copyText(CURRENT_RUN_JSON); },
    copyPatchShow: function () { copyText(CURRENT_PATCH_COMMANDS.show); },
    copyPatchCheck: function () { copyText(CURRENT_PATCH_COMMANDS.dryRun); }
  });
})(window);
