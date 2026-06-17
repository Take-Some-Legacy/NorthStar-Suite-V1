// NOESIS Suite action selection and execution.
(function (global) {
  'use strict';

  var Core = global.NoesisOperationsCore;
  var Console = global.NoesisOperationConsole;
  if (!Core || !Console) return;
  var $ = Core.$;

  function selectActionRow(row) {
    if (!row) return;
    document.querySelectorAll('#actions-table tr').forEach(function (item) {
      item.classList.remove('selected', 'active');
      item.removeAttribute('aria-selected');
    });
    row.classList.add('selected', 'active');
    row.setAttribute('aria-selected', 'true');
    var id = row.getAttribute('data-action-id') || row.getAttribute('data-action') || (row.cells && row.cells.length ? row.cells[0].textContent.trim() : '');
    Core.setInlineStatus('action-run-status', id ? 'Selected: ' + id : 'Action selected', 'selected');
  }

  function selectedActionId() {
    var active = document.querySelector('#actions-table tr.active, #actions-table tr.selected, #actions-table tr[aria-selected="true"]');
    var id = active && (active.getAttribute('data-action-id') || active.getAttribute('data-action'));
    if (id) return id;
    if (active && active.cells && active.cells.length) return active.cells[0].textContent.trim();
    var data = Core.dashboardData();
    var actions = data.operatorTasks && data.operatorTasks.availableActions;
    if (Array.isArray(actions) && actions.length) return actions[0].id || actions[0].actionId || '';
    return '';
  }

  function runSelectedAction(button) {
    var finish = Core.buttonStart(button, 'Starting...');
    Console.ensureConsole();
    var actionId = selectedActionId();
    if (!actionId) {
      Console.renderOperation({status:'failed', title:'run selected action', stderr:'No selected Suite action.', finishedUtc:Core.nowIso()});
      Core.setInlineStatus('action-run-status', 'No selected Suite action.', 'failed');
      finish('failed');
      Core.notify('error', 'Select an action first.');
      return;
    }
    Core.setInlineStatus('action-run-status', 'Starting: ' + actionId, 'running');
    Console.renderOperation({status:'starting', actionId:actionId, startedUtc:Core.nowIso(), report:{message:'Submitting operation...', request:{actionId:actionId}}});
    Core.jsonFetch('/api/operations', {method:'POST', body: JSON.stringify({actionId: actionId, timeoutSec: 300})}).then(function (j) {
      var opId = j.operationId || (j.operation && j.operation.operationId);
      if (!j.ok || !opId) {
        Console.renderOperation({status:'failed', actionId:actionId, stderr:j.error || 'operation start failed', report:j, finishedUtc:Core.nowIso()});
        Core.setInlineStatus('action-run-status', 'Start failed: ' + (j.error || 'unknown error'), 'failed');
        finish('failed');
        return;
      }
      Core.setInlineStatus('action-run-status', 'Running operation: ' + opId, 'running');
      Core.notify('info', 'Operation started.');
      Console.pollOperation(opId, finish);
    }).catch(function (err) {
      Console.renderOperation({status:'failed', actionId:actionId, stderr:String(err), finishedUtc:Core.nowIso()});
      Core.setInlineStatus('action-run-status', 'Start failed: ' + String(err), 'failed');
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

  function bindActionControls() {
    var run = $('run-selected-action');
    if (run && run.dataset.noesisBound !== '1') {
      run.dataset.noesisBound = '1';
      run.addEventListener('click', function () { runSelectedAction(run); });
    }
  }

  global.NoesisOperationActions = Object.freeze({
    selectActionRow: selectActionRow,
    selectedActionId: selectedActionId,
    runSelectedAction: runSelectedAction,
    bindActionRows: bindActionRows,
    bindActionControls: bindActionControls
  });
})(window);
