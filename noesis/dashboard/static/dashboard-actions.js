// NOESIS dashboard action catalog renderer.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var State = global.NoesisDashboardState;
  if (!State) return;
  var esc = Dom.esc || function (value) { return String(value == null ? '' : value); };
  var setHtml = Dom.setHtml || function (id, html) { var el = document.getElementById(id); if (el) el.innerHTML = html; };
  var SELECTED_ACTION_COMMAND = '';

  function $(id) { return Dom.$ ? Dom.$(id) : document.getElementById(id); }
  function actions() { return (State.get().operatorTasks || {}).availableActions || []; }

  function actionGroups() {
    var seen = {};
    actions().forEach(function (action) { if (action.group) seen[action.group] = true; });
    return Object.keys(seen).sort();
  }

  function filteredActions() {
    var q = (($('action-search') || {}).value || '').toLowerCase().trim();
    var group = (($('action-group') || {}).value || '');
    var danger = (($('action-danger') || {}).value || '');
    return actions().filter(function (a) {
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

  global.NoesisDashboardActions = Object.freeze({
    render: renderActionCatalog,
    selectedCommand: function () { return SELECTED_ACTION_COMMAND; }
  });
})(window);
