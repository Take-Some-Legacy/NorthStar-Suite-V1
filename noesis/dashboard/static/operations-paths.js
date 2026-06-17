// NOESIS editable path operations.
(function (global) {
  'use strict';

  var Core = global.NoesisOperationsCore;
  var Console = global.NoesisOperationConsole;
  if (!Core || !Console) return;
  var $ = Core.$;

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
    var finish = Core.buttonStart(button, 'Saving...');
    Console.ensureConsole();
    Core.setInlineStatus('paths-save-status', 'Saving paths...', 'running');
    var updates = collectPathUpdates();
    var keys = Object.keys(updates);
    if (!keys.length) {
      Console.renderOperation({status:'ok', title:'save editable roots', startedUtc:Core.nowIso(), finishedUtc:Core.nowIso(), report:{message:'No path changes to save.'}});
      Core.setInlineStatus('paths-save-status', 'No changes.', 'ok');
      finish('ok', 'No changes');
      Core.notify('info', 'Nothing to save.');
      return;
    }
    Console.renderOperation({status:'starting', title:'save editable roots', startedUtc:Core.nowIso(), totalSteps:2, completedSteps:1, report:{message:'Submitting path update request...', updates:updates}});
    Core.jsonFetch('/api/config/paths', {method:'POST', body: JSON.stringify({updates: updates})}).then(function (j) {
      var ok = !!j.ok;
      Console.renderOperation({status: ok ? 'ok' : 'failed', title:'save editable roots', totalSteps:2, completedSteps:2, finishedUtc:Core.nowIso(), report:j, stderr:ok ? '' : (j.error || 'path update failed')});
      Core.setInlineStatus('paths-save-status', ok ? 'Saved. Refresh dashboard data to see recomputed paths.' : 'Save failed: ' + (j.error || 'unknown error'), ok ? 'ok' : 'failed');
      finish(ok ? 'ok' : 'failed');
      Core.notify(ok ? 'success' : 'error', ok ? 'Paths saved.' : 'Path save failed.');
    }).catch(function (err) {
      Console.renderOperation({status:'failed', title:'save editable roots', stderr:String(err), finishedUtc:Core.nowIso()});
      Core.setInlineStatus('paths-save-status', 'Save failed: ' + String(err), 'failed');
      finish('failed');
      Core.notify('error', 'Path save failed.');
    });
  }

  function bindDirtyInputs() {
    document.querySelectorAll('[data-path-key]').forEach(function (input) {
      if (input.dataset.noesisBound === '1') return;
      input.dataset.noesisBound = '1';
      input.addEventListener('input', function () {
        var original = input.getAttribute('data-original') || '';
        input.classList.toggle('is-dirty', (input.value || '') !== original);
        Core.setInlineStatus('paths-save-status', 'Unsaved changes.', 'dirty');
      });
    });
  }

  function bindPathControls() {
    var save = $('save-paths');
    if (save && save.dataset.noesisBound !== '1') {
      save.dataset.noesisBound = '1';
      save.addEventListener('click', function () { savePaths(save); });
    }
  }

  global.NoesisOperationPaths = Object.freeze({
    collectPathUpdates: collectPathUpdates,
    savePaths: savePaths,
    bindDirtyInputs: bindDirtyInputs,
    bindPathControls: bindPathControls
  });
})(window);
