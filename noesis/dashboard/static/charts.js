// NOESIS Dashboard Charts
// Uses Chart.js when available; falls back to compact local HTML stats when offline.
(function () {
  'use strict';

  function byId(id) { return document.getElementById(id); }
  function safeRuns() {
    try {
      if (window.NOESIS_DASHBOARD && Array.isArray(window.NOESIS_DASHBOARD.recent)) return window.NOESIS_DASHBOARD.recent;
      if (window.__NOESIS_RUNS__ && Array.isArray(window.__NOESIS_RUNS__.recent)) return window.__NOESIS_RUNS__.recent;
    } catch (_) {}
    return [];
  }
  function countBy(items, fn) {
    var out = {};
    items.forEach(function (item) {
      var key = fn(item) || 'unknown';
      out[key] = (out[key] || 0) + 1;
    });
    return out;
  }
  function entries(obj) { return Object.keys(obj || {}).map(function (k) { return [k, obj[k]]; }); }
  function top(obj, limit) { return entries(obj).sort(function (a,b) { return b[1] - a[1]; }).slice(0, limit || 8); }
  function canvas(id) {
    var host = byId(id);
    if (!host) return null;
    host.innerHTML = '<canvas></canvas>';
    return host.querySelector('canvas');
  }
  function palette(n) {
    var base = ['#6ee7b7','#93c5fd','#f472b6','#fbbf24','#c4b5fd','#67e8f9','#fb7185','#a3e635'];
    var out = [];
    for (var i=0; i<n; i++) out.push(base[i % base.length]);
    return out;
  }
  function commonOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 280 },
      plugins: { legend: { labels: { color: '#dbeafe' } } },
      scales: {
        x: { ticks: { color: '#93a4c4' }, grid: { color: 'rgba(148,163,184,.12)' } },
        y: { beginAtZero: true, ticks: { color: '#93a4c4', precision: 0 }, grid: { color: 'rgba(148,163,184,.12)' } }
      }
    };
  }
  function chartJsLine(id, labels, values, label) {
    var el = canvas(id); if (!el || !window.Chart) return false;
    new window.Chart(el, {
      type: 'line',
      data: { labels: labels, datasets: [{ label: label, data: values, borderWidth: 2, tension: .35, fill: true }] },
      options: commonOptions()
    });
    return true;
  }
  function chartJsBar(id, pairs, label) {
    var el = canvas(id); if (!el || !window.Chart) return false;
    new window.Chart(el, {
      type: 'bar',
      data: { labels: pairs.map(function (p) { return p[0]; }), datasets: [{ label: label, data: pairs.map(function (p) { return p[1]; }), backgroundColor: palette(pairs.length), borderWidth: 0 }] },
      options: commonOptions()
    });
    return true;
  }
  function chartJsDoughnut(id, pairs, label) {
    var el = canvas(id); if (!el || !window.Chart) return false;
    new window.Chart(el, {
      type: 'doughnut',
      data: { labels: pairs.map(function (p) { return p[0]; }), datasets: [{ label: label, data: pairs.map(function (p) { return p[1]; }), backgroundColor: palette(pairs.length) }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#dbeafe' } } } }
    });
    return true;
  }
  function fallbackList(id, pairs) {
    var host = byId(id); if (!host) return;
    host.innerHTML = '<div class="mini-bars">' + pairs.map(function (p) {
      return '<div class="mini-bar"><span>' + String(p[0]) + '</span><strong>' + String(p[1]) + '</strong></div>';
    }).join('') + '</div>';
  }
  function renderStats(runs) {
    var host = byId('liveStats'); if (!host) return;
    var total = runs.length;
    var ready = runs.filter(function (r) { return String(r.status || '').indexOf('merge') >= 0; }).length;
    var rejected = runs.filter(function (r) { return String(r.status || '').indexOf('reject') >= 0; }).length;
    host.innerHTML = [
      '<div class="stat-chip"><strong>' + total + '</strong><span>visible runs</span></div>',
      '<div class="stat-chip ok"><strong>' + ready + '</strong><span>merge ready</span></div>',
      '<div class="stat-chip bad"><strong>' + rejected + '</strong><span>rejected</span></div>',
      '<div class="stat-chip"><strong>' + (window.Chart ? 'Chart.js' : 'local') + '</strong><span>chart provider</span></div>'
    ].join('');
  }
  function render() {
    var runs = safeRuns();
    renderStats(runs);
    var byDay = countBy(runs, function (r) { return String(r.generatedUtc || r.completedUtc || r.runId || '').slice(0,10); });
    var timeline = entries(byDay).sort(function (a,b) { return String(a[0]).localeCompare(String(b[0])); }).slice(-14);
    var status = top(countBy(runs, function (r) { return r.status; }), 8);
    var scope = top(countBy(runs, function (r) { return r.scope; }), 8);
    var reasons = top(countBy(runs.filter(function (r) { return r.reason; }), function (r) { return r.reason; }), 8);
    if (window.Chart) {
      chartJsLine('chartTimeline', timeline.map(function (p) { return p[0]; }), timeline.map(function (p) { return p[1]; }), 'runs');
      chartJsDoughnut('chartStatus', status, 'status');
      chartJsDoughnut('chartScope', scope, 'scope');
      chartJsBar('chartReasons', reasons, 'rejections');
    } else {
      fallbackList('chartTimeline', timeline);
      fallbackList('chartStatus', status);
      fallbackList('chartScope', scope);
      fallbackList('chartReasons', reasons);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', render);
  else render();
})();
