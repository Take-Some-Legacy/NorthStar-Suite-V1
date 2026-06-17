// NOESIS task command autocomplete.
(function (global) {
  'use strict';

  var Core = global.NoesisOperationsCore;
  if (!Core) return;
  var $ = Core.$;

  function commandActions() {
    var data = Core.dashboardData();
    var tasks = data.operatorTasks || {};
    var actions = Array.isArray(tasks.availableActions) ? tasks.availableActions : [];
    return actions.map(function (action) {
      return {
        id: String(action.id || action.actionId || ''),
        title: String(action.title || action.id || action.actionId || ''),
        group: String(action.group || ''),
        dangerLevel: String(action.dangerLevel || 'normal'),
        description: String(action.description || ''),
        suiteCommand: String(action.suiteCommand || '')
      };
    }).filter(function (action) { return !!action.id; });
  }

  function setupCommandAutocomplete() {
    var input = $('task-action-id');
    var suggestions = $('task-action-suggestions');
    var status = $('task-submit-status');
    if (!input || !suggestions) return;
    var actions = commandActions();
    var current = [];
    var active = 0;

    function hide() {
      suggestions.hidden = true;
      suggestions.innerHTML = '';
      active = 0;
    }

    function apply(action) {
      if (!action || !action.id) return;
      input.value = action.id;
      input.dataset.selectedActionId = action.id;
      input.dataset.selectedActionTitle = action.title || action.id;
      input.dataset.selectedActionDescription = action.description || '';
      if (status) {
        status.textContent = 'Selected: ' + action.id + (action.description ? ' — ' + action.description : '');
        status.dataset.status = 'selected';
      }
      hide();
    }

    function render() {
      if (!current.length) {
        suggestions.innerHTML = '<div class="command-suggestion empty">No matching Suite actions.</div>';
        suggestions.hidden = false;
        return;
      }
      suggestions.innerHTML = current.map(function (action, index) {
        var selected = index === active ? ' is-active' : '';
        var desc = action.description || 'No description in descriptor.';
        return '<button type="button" class="command-suggestion' + selected + '" role="option" data-suggestion-index="' + index + '">' +
          '<span class="command-main"><b>' + Core.htmlEscape(action.id) + '</b><small>' + Core.htmlEscape(action.title) + '</small></span>' +
          '<span class="command-meta"><code>' + Core.htmlEscape(action.group || 'suite') + '</code><code>' + Core.htmlEscape(action.dangerLevel || 'normal') + '</code></span>' +
          '<span class="command-desc">' + Core.htmlEscape(desc) + '</span>' +
        '</button>';
      }).join('');
      suggestions.hidden = false;
    }

    function update() {
      var query = input.value.trim().toLowerCase();
      current = actions.filter(function (action) {
        if (!query) return true;
        return [action.id, action.title, action.group, action.description].join(' ').toLowerCase().indexOf(query) !== -1;
      }).slice(0, 10);
      active = Math.min(active, Math.max(current.length - 1, 0));
      render();
    }

    input.addEventListener('input', function () { input.dataset.selectedActionId = ''; update(); });
    input.addEventListener('focus', update);
    input.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') { event.preventDefault(); if (!current.length) update(); active = Math.min(active + 1, Math.max(current.length - 1, 0)); render(); return; }
      if (event.key === 'ArrowUp') { event.preventDefault(); active = Math.max(active - 1, 0); render(); return; }
      if (event.key === 'Tab') {
        if (current.length || input.value.trim()) {
          if (!current.length) update();
          if (current[active]) { event.preventDefault(); apply(current[active]); }
        }
        return;
      }
      if (event.key === 'Enter') { if (current[active]) { event.preventDefault(); apply(current[active]); } return; }
      if (event.key === 'Escape') hide();
    });
    suggestions.addEventListener('click', function (event) {
      var button = event.target.closest('[data-suggestion-index]');
      if (button) apply(current[Number(button.dataset.suggestionIndex)]);
    });
    document.addEventListener('click', function (event) {
      if (event.target === input || suggestions.contains(event.target)) return;
      hide();
    });
  }

  global.NoesisOperationAutocomplete = Object.freeze({
    commandActions: commandActions,
    setupCommandAutocomplete: setupCommandAutocomplete
  });
})(window);
