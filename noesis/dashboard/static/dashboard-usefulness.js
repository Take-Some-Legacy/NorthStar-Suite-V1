// NOESIS dashboard operator intelligence renderer.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var State = global.NoesisDashboardState;
  if (!State) return;

  var esc = Dom.esc || function (value) { return String(value == null ? '' : value); };
  var setHtml = Dom.setHtml || function (id, html) { var el = document.getElementById(id); if (el) el.innerHTML = html; };
  var copyText = Dom.copyText || function () {};

  function getRecent() {
    var recent = State.get().recent;
    return Array.isArray(recent) ? recent : [];
  }

  function statusClass(value) {
    return State.statusClass ? State.statusClass(value) : 'unknown';
  }

  function statusBadge(value) {
    var v = String(value || 'unknown');
    return '<span class="status ' + statusClass(v) + '">' + esc(v) + '</span>';
  }

  function pct(part, total) {
    total = Number(total) || 0;
    if (!total) return '0%';
    return Math.round((Number(part) || 0) * 100 / total) + '%';
  }

  function sum(items, fn) {
    var total = 0;
    items.forEach(function (item) { total += Number(fn(item) || 0); });
    return total;
  }

  function count(items, fn) {
    var total = 0;
    items.forEach(function (item) { if (fn(item)) total += 1; });
    return total;
  }

  function latestRun() {
    var data = State.get();
    var recent = getRecent();
    return data.latest || recent[recent.length - 1] || {};
  }

  function riskScore(data, recent) {
    var c = data.counts || {};
    var latest = latestRun();
    var score = 0;
    if (latest.status === 'rejected') score += 35;
    if ((c.rejected || 0) > 0) score += 18;
    if ((c.latestChangedFiles || 0) > 0) score += Math.min(18, Number(c.latestChangedFiles || 0));
    score += Math.min(16, sum(recent, function (run) { return run.testsFailed; }));
    score += Math.min(13, sum(recent, function (run) { return run.auditIssues; }));
    return Math.max(0, Math.min(100, score));
  }

  function grade(score) {
    if (score >= 60) return 'bad';
    if (score >= 25) return 'warn';
    return 'good';
  }

  function briefItem(title, body, cls) {
    return '<div class="brief-item ' + esc(cls || '') + '"><strong>' + esc(title) + '</strong><span>' + body + '</span></div>';
  }

  function actionItem(title, command, hint) {
    return '<div class="action-item"><div><strong>' + esc(title) + '</strong><span>' + esc(hint || '') + '</span><br><code>' + esc(command) + '</code></div><button type="button" data-usefulness-copy="' + esc(command) + '">Copy</button></div>';
  }

  function riskItem(title, body, score, cls) {
    var width = Math.max(4, Math.min(100, Number(score) || 0));
    return '<div class="risk-item ' + esc(cls || '') + '"><strong>' + esc(title) + '<span class="risk-score">' + esc(score) + '/100</span></strong><span>' + body + '</span><div class="risk-meter"><span style="width:' + width + '%"></span></div></div>';
  }

  function renderOperatorBrief() {
    var data = State.get();
    var recent = getRecent();
    var latest = latestRun();
    var c = data.counts || {};
    var i = data.insights || {};
    var score = riskScore(data, recent);
    var cls = grade(score);
    var readyRecent = count(recent, function (run) { return run.status === 'merge_ready'; });
    var blocker = latest.reason || latest.failedPhase || (i.attention || [])[0] || 'No blocking reason in latest data.';

    setHtml('operator-brief-list', [
      briefItem('State', statusBadge(latest.status) + ' ' + esc(i.headline || 'No headline available.'), latest.status === 'merge_ready' ? 'good' : cls),
      briefItem('Current blocker', esc(blocker), latest.status === 'rejected' ? 'bad' : 'warn'),
      briefItem('Visible readiness', esc(readyRecent + '/' + recent.length + ' recent runs ready (' + pct(readyRecent, recent.length) + ')'), readyRecent ? 'good' : 'warn'),
      briefItem('Change pressure', esc((c.latestChangedFiles || 0) + ' changed files in latest run'), (c.latestChangedFiles || 0) ? 'warn' : 'good')
    ].join(''));

    var sev = document.getElementById('operator-brief-severity');
    if (sev) {
      sev.textContent = cls === 'bad' ? 'high risk' : cls === 'warn' ? 'watch' : 'stable';
      sev.className = 'tag ' + cls;
    }
  }

  function renderNextActions() {
    var latest = latestRun();
    var runId = latest.runId || '';
    var items = [];
    if (latest.status === 'rejected' && runId) {
      items.push(actionItem('Inspect latest rejection', 'python -m noesis runs patch ' + runId + ' --show', 'Start from the exact failing artifact before changing code.'));
      items.push(actionItem('Dry-run latest patch', 'python -m noesis runs patch ' + runId + ' --check', 'Verify integration path without applying.'));
    }
    items.push(actionItem('Refresh dashboard data', 'python -m noesis runs index', 'Regenerate the static dashboard index and data snapshot.'));
    items.push(actionItem('Run focused gate', 'python -m noesis noesis-test-dev-repo verify --scope noesis-core --apply-current-diff', 'Fast readiness signal for NOESIS core.'));
    items.push(actionItem('Run full gate', 'python -m noesis noesis-test-dev-repo verify --scope full-repo --apply-current-diff', 'Use before merge or broad changes.'));
    setHtml('next-actions', items.slice(0, 5).join(''));
    document.querySelectorAll('[data-usefulness-copy]').forEach(function (button) {
      button.addEventListener('click', function () { copyText(button.getAttribute('data-usefulness-copy') || ''); });
    });
  }

  function renderDataHealth() {
    var data = State.get();
    var recent = getRecent();
    var c = data.counts || {};
    var paths = data.paths || {};
    var entries = paths.entries || {};
    var pathCount = Object.keys(entries).length || ((paths.rows || []).length) || 0;
    var gradeText = recent.length ? 'complete' : 'empty';
    setHtml('data-health', [
      ['indexed runs', c.runs || recent.length || 0],
      ['visible recent', recent.length],
      ['latest run', latestRun().runId || 'none'],
      ['path entries', pathCount],
      ['data root', data.root || paths.suiteRootPath || 'unknown']
    ].map(function (row) { return '<div class="timeline-item"><span>' + esc(row[0]) + '</span><b>' + esc(row[1]) + '</b></div>'; }).join(''));
    var el = document.getElementById('data-health-grade');
    if (el) el.textContent = gradeText;
  }

  function renderActivityDigest() {
    var recent = getRecent().slice(-6).reverse();
    if (!recent.length) {
      setHtml('activity-digest', '<div class="digest-item"><strong>No runs indexed</strong><span>Run the index command to populate the dashboard.</span></div>');
      return;
    }
    setHtml('activity-digest', recent.map(function (run) {
      var details = [run.scope, run.failedPhase, run.reason].filter(Boolean).join(' / ') || 'no reason recorded';
      return '<div class="digest-item"><strong>' + esc(run.runId || 'unknown') + '</strong><span>' + esc(details) + '</span>' + statusBadge(run.status) + '</div>';
    }).join(''));
  }

  function renderRiskRadar() {
    var data = State.get();
    var recent = getRecent();
    var c = data.counts || {};
    var latest = latestRun();
    var failedTests = sum(recent, function (run) { return run.testsFailed; });
    var auditIssues = sum(recent, function (run) { return run.auditIssues; });
    var score = riskScore(data, recent);
    setHtml('risk-radar', [
      riskItem('Overall risk', esc(latest.status || 'unknown') + ' latest status with ' + esc(c.rejected || 0) + ' rejected indexed runs.', score, grade(score)),
      riskItem('Test pressure', esc(failedTests) + ' failed tests in visible recent window.', Math.min(100, failedTests * 12), failedTests ? 'bad' : 'good'),
      riskItem('Audit pressure', esc(auditIssues) + ' audit issues in visible recent window.', Math.min(100, auditIssues * 16), auditIssues ? 'warn' : 'good'),
      riskItem('Change pressure', esc(c.latestChangedFiles || 0) + ' latest changed files.', Math.min(100, Number(c.latestChangedFiles || 0) * 4), (c.latestChangedFiles || 0) ? 'warn' : 'good')
    ].join(''));
  }

  function render() {
    renderOperatorBrief();
    renderNextActions();
    renderDataHealth();
    renderActivityDigest();
    renderRiskRadar();
  }

  global.NoesisDashboardUsefulness = Object.freeze({render: render});
})(window);
