// NOESIS direct task submission.
(function (global) {
  'use strict';

  var Core = global.NoesisOperationsCore;
  var Console = global.NoesisOperationConsole;
  var Actions = global.NoesisOperationActions;
  if (!Core || !Console || !Actions) return;
  var $ = Core.$;

  function parseTaskArgs() {
    var raw = (Core.taskArgsRaw() || '').trim();
    if (!raw) return {};
    try { return JSON.parse(raw); }
    catch (err) { throw new Error('Invalid task args JSON: ' + String(err.message || err)); }
  }

  function submitTask(button) {
    var finish = Core.buttonStart(button, 'Submitting...');
    Console.ensureConsole();
    Console.focusConsole();
    var input = $('task-action-id');
    var actionId = (input && input.value.trim()) || Actions.selectedActionId();
    if (!actionId) {
      Console.renderOperation({status:'failed', title:'submit task', stderr:'No action id selected.', finishedUtc:Core.nowIso()});
      Core.setInlineStatus('task-submit-status', 'No action id selected.', 'failed');
      finish('failed');
      return;
    }
    var args = {};
    try { args = parseTaskArgs(); }
    catch (err) {
      Console.renderOperation({status:'failed', title:'submit task', stderr:String(err), finishedUtc:Core.nowIso()});
      Core.setInlineStatus('task-submit-status', String(err), 'failed');
      finish('failed');
      return;
    }
    Core.setInlineStatus('task-submit-status', 'Submitting: ' + actionId, 'running');
    Console.renderOperation({status:'starting', title:'submit task', actionId:actionId, startedUtc:Core.nowIso(), report:{message:'Submitting task to Suite operation API...', actionId:actionId, args:args}});
    Core.jsonFetch('/api/operations', {method:'POST', body: JSON.stringify({actionId:actionId, args:args})}).then(function (j) {
      var op = j.operation || j;
      if (op.operationId) {
        Core.setInlineStatus('task-submit-status', 'Running: ' + op.operationId, 'running');
        Console.pollOperation(op.operationId, function (status) {
          Core.setInlineStatus('task-submit-status', status === 'ok' ? 'Done: ' + actionId : 'Failed: ' + actionId, status === 'ok' ? 'ok' : 'failed');
          finish(status === 'ok' ? 'ok' : 'failed');
        });
      } else {
        Console.renderOperation(Object.assign({title:'submit task'}, op));
        Core.setInlineStatus('task-submit-status', op.ok === false ? 'Task failed to start.' : 'Task submitted.', op.ok === false ? 'failed' : 'ok');
        finish(op.ok === false ? 'failed' : 'ok');
      }
    }).catch(function (err) {
      Console.renderOperation({status:'failed', title:'submit task', stderr:String(err), finishedUtc:Core.nowIso()});
      Core.setInlineStatus('task-submit-status', 'Submit failed: ' + String(err), 'failed');
      finish('failed');
    });
  }

  function bindRecommendedTaskControls() {
    document.querySelectorAll('#task-recommended [data-copy]').forEach(function (btn) {
      if (btn.dataset.noesisTaskBound === '1') return;
      btn.dataset.noesisTaskBound = '1';
      btn.addEventListener('click', function () {
        var cmd = btn.getAttribute('data-copy') || '';
        var m = cmd.match(/--run\s+([^\s]+)/);
        var actionId = m ? m[1] : '';
        if ($('task-action-id') && actionId) $('task-action-id').value = actionId;
        Core.setInlineStatus('task-submit-status', actionId ? 'Prepared: ' + actionId : 'Command copied/prepared.', 'selected');
      });
    });
  }

  function bindTaskControls() {
    bindRecommendedTaskControls();
    var submit = $('submit-task');
    if (submit && submit.dataset.noesisBound !== '1') {
      submit.dataset.noesisBound = '1';
      submit.addEventListener('click', function () { submitTask(submit); });
    }
  }

  global.NoesisOperationTasks = Object.freeze({
    parseTaskArgs: parseTaskArgs,
    submitTask: submitTask,
    bindTaskControls: bindTaskControls
  });
})(window);
