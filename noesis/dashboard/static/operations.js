// NOESIS Dashboard Operation Console
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function dashboardData() { return window.NOESIS_DASHBOARD || window.__NOESIS_RUNS__ || {}; }
  function setText(id, value) { var el = $(id); if (el) el.textContent = value; }
  function show(el, yes) { if (el) el.hidden = !yes; }

  function jsonFetch(url, options) {
    options = options || {};
    options.headers = Object.assign({'Content-Type':'application/json'}, options.headers || {});
    return fetch(url, options).then(function (r) {
      return r.json().then(function (j) {
        j.__httpStatus = r.status;
        return j;
      });
    });
  }

  function ensureConsole() {
    var host = $('operation-console');
    if (!host) {
      var main = document.querySelector('main') || document.body;
      host = document.createElement('section');
      host.id = 'operation-console';
      host.className = 'card operation-console';
      main.insertBefore(host, main.firstChild || null);
    }
    if (!host.querySelector('#op-console-output')) {
      host.innerHTML = [
        '<div class="op-head">',
        '<div><h3>Operation console</h3><p class="muted">Every long operation reports loader, progress and exact stdout/stderr/report output.</p></div>',
        '<div class="op-state"><span id="op-spinner" class="op-spinner" hidden></span><strong id="op-status">idle</strong></div>',
        '</div>',
        '<div class="op-progress"><div id="op-progress-bar"></div></div>',
        '<div class="op-meta"><span id="op-id">no operation</span><span id="op-title"></span></div>',
        '<pre id="op-console-output" class="op-output">Ready.</pre>'
      ].join('');
    }
    return host;
  }

  function focusConsole() {
    var host = ensureConsole();
    host.classList.add('is-active');
    if (host.scrollIntoView) host.scrollIntoView({block:'nearest', behavior:'smooth'});
  }

  function setProgress(value, indeterminate) {
    var bar = $('op-progress-bar');
    if (!bar) return;
    if (indeterminate) {
      bar.style.width = '38%';
      bar.classList.add('indeterminate');
      return;
    }
    bar.classList.remove('indeterminate');
    var pct = Math.max(0, Math.min(100, Number(value) || 0));
    bar.style.width = pct + '%';
  }

  function reportLine(label, value) {
    if (value === undefined || value === null || value === '') return '';
    return '\n[' + label + ']\n' + (typeof value === 'string' ? value : JSON.stringify(value, null, 2));
  }

  function nowIso() { return new Date().toISOString(); }

  function renderOperation(op) {
    ensureConsole();
    op = op || {};
    var status = op.status || (op.ok === false ? 'failed' : 'running');
    setText('op-status', status);
    setText('op-id', op.operationId ? 'operationId: ' + op.operationId : 'operation: local/pending');
    setText('op-title', op.actionId || op.title || '');
    show($('op-spinner'), status === 'queued' || status === 'running' || status === 'starting');
    var total = Number(op.totalSteps || 0);
    var done = Number(op.completedSteps || 0);
    if (total > 0) setProgress((done / total) * 100, false);
    else setProgress(status === 'ok' ? 100 : status === 'failed' ? 100 : 35, status === 'queued' || status === 'running' || status === 'starting');
    var text = 'status: ' + status + '\n';
    if (op.startedUtc) text += 'startedUtc: ' + op.startedUtc + '\n';
    if (op.finishedUtc) text += 'finishedUtc: ' + op.finishedUtc + '\n';
    text += reportLine('stdout', op.stdout);
    text += reportLine('stderr', op.stderr);
    text += reportLine('report', op.report || op.result);
    var out = $('op-console-output');
    if (out) out.textContent = text;
    focusConsole();
  }

  function buttonStart(button, label) {
    if (!button) return function () {};
    var oldText = button.textContent;
    button.dataset.originalText = oldText;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.classList.remove('is-ok', 'is-failed');
    button.classList.add('is-running');
    button.textContent = label || 'Running...';
    return function finish(status, finalText) {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.classList.remove('is-running');
      button.classList.add(status === 'ok' ? 'is-ok' : 'is-failed');
      button.textContent = finalText || (status === 'ok' ? 'Done' : 'Failed');
      window.setTimeout(function () {
        button.classList.remove('is-ok', 'is-failed');
        button.textContent = button.dataset.originalText || oldText;
      }, 1800);
    };
  }

  function setInlineStatus(id, text, status) {
    var el = $(id);
    if (!el) return;
    el.textContent = text || '';
    el.dataset.status = status || 'idle';
  }

  function pollOperation(operationId, finishButton) {
    renderOperation({operationId: operationId, status: 'running', report:{message:'Polling operation status...'}});
    var stop = false;
    function tick() {
      if (stop) return;
      jsonFetch('/api/operations/' + encodeURIComponent(operationId)).then(function (j) {
        var op = j.operation || j;
        renderOperation(op);
        if (op.status === 'queued' || op.status === 'running') {
          window.setTimeout(tick, 900);
        } else {
          stop = true;
          if (finishButton) finishButton(op.status === 'ok' ? 'ok' : 'failed');
        }
      }).catch(function (err) {
        renderOperation({operationId: operationId, status: 'failed', stderr: String(err), finishedUtc: nowIso()});
        stop = true;
        if (finishButton) finishButton('failed');
      });
    }
    tick();
  }

  function collectPathUpdates() {
    var updates = {};
    document.querySelectorAll('[data-path-key]').forEach(function (input) {
      if (input.disabled || input.readOnly) return;
      var key = input.getAttribute('data-path-key');
      var original = input.getAttribute('data-original') || '';
      var value = input.value || '';
      input.classList.toggle('is-dirty', value !== original);
      if (key && value !== original) updates[key] = value;
    });
    return updates;
  }

  function savePaths(button) {
    var finish = buttonStart(button, 'Saving...');
    ensureConsole();
    setInlineStatus('paths-save-status', 'Saving paths...', 'running');
    var updates = collectPathUpdates();
    var keys = Object.keys(updates);
    if (!keys.length) {
      renderOperation({status:'ok', title:'save editable roots', startedUtc:nowIso(), finishedUtc:nowIso(), report:{message:'No path changes to save.'}});
      setInlineStatus('paths-save-status', 'No changes.', 'ok');
      finish('ok', 'No changes');
      return;
    }
    renderOperation({status:'starting', title:'save editable roots', startedUtc:nowIso(), totalSteps:2, completedSteps:1, report:{message:'Submitting path update request...', updates:updates}});
    jsonFetch('/api/config/paths', {method:'POST', body: JSON.stringify({updates: updates})}).then(function (j) {
      var ok = !!j.ok;
      renderOperation({status: ok ? 'ok' : 'failed', title:'save editable roots', totalSteps:2, completedSteps:2, finishedUtc:nowIso(), report:j, stderr:ok ? '' : (j.error || 'path update failed')});
      setInlineStatus('paths-save-status', ok ? 'Saved. Refresh dashboard data to see recomputed paths.' : 'Save failed: ' + (j.error || 'unknown error'), ok ? 'ok' : 'failed');
      finish(ok ? 'ok' : 'failed');
    }).catch(function (err) {
      renderOperation({status:'failed', title:'save editable roots', stderr:String(err), finishedUtc:nowIso()});
      setInlineStatus('paths-save-status', 'Save failed: ' + String(err), 'failed');
      finish('failed');
    });
  }

  function selectActionRow(row) {
    if (!row) return;
    document.querySelectorAll('#actions-table tr').forEach(function (r) {
      r.classList.remove('selected', 'active');
      r.removeAttribute('aria-selected');
    });
    row.classList.add('selected', 'active');
    row.setAttribute('aria-selected', 'true');
    var id = row.getAttribute('data-action-id') || row.getAttribute('data-action') || (row.cells && row.cells.length ? row.cells[0].textContent.trim() : '');
    setInlineStatus('action-run-status', id ? 'Selected: ' + id : 'Action selected', 'selected');
  }

  function selectedActionId() {
    var active = document.querySelector('#actions-table tr.active, #actions-table tr.selected, #actions-table tr[aria-selected="true"]');
    var id = active && (active.getAttribute('data-action-id') || active.getAttribute('data-action'));
    if (id) return id;
    if (active && active.cells && active.cells.length) return active.cells[0].textContent.trim();
    var data = dashboardData();
    var actions = data.operatorTasks && data.operatorTasks.availableActions;
    if (Array.isArray(actions) && actions.length) return actions[0].id || actions[0].actionId || '';
    return '';
  }

  function runSelectedAction(button) {
    var finish = buttonStart(button, 'Starting...');
    ensureConsole();
    var actionId = selectedActionId();
    if (!actionId) {
      renderOperation({status:'failed', title:'run selected action', stderr:'No selected Suite action.', finishedUtc:nowIso()});
      setInlineStatus('action-run-status', 'No selected Suite action.', 'failed');
      finish('failed');
      return;
    }
    setInlineStatus('action-run-status', 'Starting: ' + actionId, 'running');
    renderOperation({status:'starting', actionId:actionId, startedUtc:nowIso(), report:{message:'Submitting operation...', request:{actionId:actionId}}});
    jsonFetch('/api/operations', {method:'POST', body: JSON.stringify({actionId: actionId, timeoutSec: 300})}).then(function (j) {
      var opId = j.operationId || (j.operation && j.operation.operationId);
      if (!j.ok || !opId) {
        renderOperation({status:'failed', actionId:actionId, stderr:j.error || 'operation start failed', report:j, finishedUtc:nowIso()});
        setInlineStatus('action-run-status', 'Start failed: ' + (j.error || 'unknown error'), 'failed');
        finish('failed');
        return;
      }
      setInlineStatus('action-run-status', 'Running operation: ' + opId, 'running');
      pollOperation(opId, finish);
    }).catch(function (err) {
      renderOperation({status:'failed', actionId:actionId, stderr:String(err), finishedUtc:nowIso()});
      setInlineStatus('action-run-status', 'Start failed: ' + String(err), 'failed');
      finish('failed');
    });
  }

  function bindActionRows() {
    document.querySelectorAll('#actions-table tr').forEach(function (row) {
      if (row.dataset.noesisBound === '1') return;
      row.dataset.noesisBound = '1';
      row.addEventListener('click', function () { selectActionRow(row); });
    });
  }


  function parseTaskArgs() {
    var raw = $('task-args-json') ? $('task-args-json').value.trim() : '';
    if (!raw) return {};
    try { return JSON.parse(raw); }
    catch (err) { throw new Error('Invalid task args JSON: ' + String(err.message || err)); }
  }

  function submitTask(button) {
    var finish = buttonStart(button, 'Submitting...');
    ensureConsole();
    focusConsole();
    var input = $('task-action-id');
    var actionId = (input && input.value.trim()) || selectedActionId();
    if (!actionId) {
      renderOperation({status:'failed', title:'submit task', stderr:'No action id selected.', finishedUtc:nowIso()});
      setInlineStatus('task-submit-status', 'No action id selected.', 'failed');
      finish('failed');
      return;
    }
    var args = {};
    try { args = parseTaskArgs(); }
    catch (err) {
      renderOperation({status:'failed', title:'submit task', stderr:String(err), finishedUtc:nowIso()});
      setInlineStatus('task-submit-status', String(err), 'failed');
      finish('failed');
      return;
    }
    setInlineStatus('task-submit-status', 'Submitting: ' + actionId, 'running');
    renderOperation({status:'starting', title:'submit task', actionId:actionId, startedUtc:nowIso(), report:{message:'Submitting task to Suite operation API...', actionId:actionId, args:args}});
    jsonFetch('/api/operations', {method:'POST', body: JSON.stringify({actionId:actionId, args:args})}).then(function (j) {
      var op = j.operation || j;
      if (op.operationId) {
        setInlineStatus('task-submit-status', 'Running: ' + op.operationId, 'running');
        pollOperation(op.operationId, function (status) {
          setInlineStatus('task-submit-status', status === 'ok' ? 'Done: ' + actionId : 'Failed: ' + actionId, status === 'ok' ? 'ok' : 'failed');
          finish(status === 'ok' ? 'ok' : 'failed');
        });
      } else {
        renderOperation(Object.assign({title:'submit task'}, op));
        setInlineStatus('task-submit-status', op.ok === false ? 'Task failed to start.' : 'Task submitted.', op.ok === false ? 'failed' : 'ok');
        finish(op.ok === false ? 'failed' : 'ok');
      }
    }).catch(function (err) {
      renderOperation({status:'failed', title:'submit task', stderr:String(err), finishedUtc:nowIso()});
      setInlineStatus('task-submit-status', 'Submit failed: ' + String(err), 'failed');
      finish('failed');
    });
  }

  function bindDirtyInputs() {
    document.querySelectorAll('[data-path-key]').forEach(function (input) {
      if (input.dataset.noesisBound === '1') return;
      input.dataset.noesisBound = '1';
      input.addEventListener('input', function () {
        var original = input.getAttribute('data-original') || '';
        input.classList.toggle('is-dirty', (input.value || '') !== original);
        setInlineStatus('paths-save-status', 'Unsaved changes.', 'dirty');
      });
    });
  }


  function htmlEscape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c];
    });
  }

  function commandActions() {
    var data = dashboardData();
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
          '<span class="command-main"><b>' + htmlEscape(action.id) + '</b><small>' + htmlEscape(action.title) + '</small></span>' +
          '<span class="command-meta"><code>' + htmlEscape(action.group || 'suite') + '</code><code>' + htmlEscape(action.dangerLevel || 'normal') + '</code></span>' +
          '<span class="command-desc">' + htmlEscape(desc) + '</span>' +
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

    input.addEventListener('input', function () {
      input.dataset.selectedActionId = '';
      update();
    });
    input.addEventListener('focus', update);
    input.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        if (!current.length) update();
        active = Math.min(active + 1, Math.max(current.length - 1, 0));
        render();
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        active = Math.max(active - 1, 0);
        render();
        return;
      }
      if (event.key === 'Tab') {
        if (current.length || input.value.trim()) {
          if (!current.length) update();
          if (current[active]) {
            event.preventDefault();
            apply(current[active]);
          }
        }
        return;
      }
      if (event.key === 'Enter') {
        if (current[active]) {
          event.preventDefault();
          apply(current[active]);
        }
        return;
      }
      if (event.key === 'Escape') hide();
    });
    suggestions.addEventListener('click', function (event) {
      var button = event.target.closest('[data-suggestion-index]');
      if (!button) return;
      apply(current[Number(button.dataset.suggestionIndex)]);
    });
    document.addEventListener('click', function (event) {
      if (event.target === input || suggestions.contains(event.target)) return;
      hide();
    });
  }

  function bind() {
    ensureConsole();
    bindActionRows();
    bindDirtyInputs();
    setupCommandAutocomplete();
    document.querySelectorAll('#task-recommended [data-copy]').forEach(function (btn) {
      if (btn.dataset.noesisTaskBound === '1') return;
      btn.dataset.noesisTaskBound = '1';
      btn.addEventListener('click', function () {
        var cmd = btn.getAttribute('data-copy') || '';
        var m = cmd.match(/--run\s+([^\s]+)/);
        var actionId = m ? m[1] : '';
        if ($('task-action-id') && actionId) $('task-action-id').value = actionId;
        setInlineStatus('task-submit-status', actionId ? 'Prepared: ' + actionId : 'Command copied/prepared.', 'selected');
      });
    });
    var submit = $('submit-task');
    if (submit && submit.dataset.noesisBound !== '1') {
      submit.dataset.noesisBound = '1';
      submit.addEventListener('click', function () { submitTask(submit); });
    }
    var save = $('save-paths');
    if (save && save.dataset.noesisBound !== '1') {
      save.dataset.noesisBound = '1';
      save.addEventListener('click', function () { savePaths(save); });
    }
    var run = $('run-selected-action');
    if (run && run.dataset.noesisBound !== '1') {
      run.dataset.noesisBound = '1';
      run.addEventListener('click', function () { runSelectedAction(run); });
    }
  }

  window.NoesisOperations = Object.freeze({
    bind: bind,
    renderOperation: renderOperation,
    pollOperation: pollOperation,
    collectPathUpdates: collectPathUpdates,
    savePaths: savePaths,
    runSelectedAction: runSelectedAction,
    submitTask: submitTask
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
})();
