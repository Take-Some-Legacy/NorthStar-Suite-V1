// NOESIS editable path row operations.
(function (global) {
  'use strict';

  var Core = global.NoesisOperationsCore;
  var Console = global.NoesisOperationConsole;
  if (!Core || !Console) return;
  var $ = Core.$;

  function rows() { return Array.prototype.slice.call(document.querySelectorAll('[data-path-row]')); }
  function field(row, name) { return row.querySelector('[data-row-field="' + name + '"]'); }
  function valueOf(input) { return input && input.type === 'checkbox' ? (input.checked ? '1' : '0') : ((input && input.value) || ''); }
  function changed(input) { return input && valueOf(input) !== (input.getAttribute('data-original') || ''); }

  function rowPayload(row) {
    var based = field(row, 'based');
    return {
      id: row.getAttribute('data-row-id') || '',
      label: valueOf(field(row, 'label')).trim(),
      value: valueOf(field(row, 'value')).trim(),
      basedOnSuiteRoot: !!(based && based.checked),
      deleted: row.dataset.deleted === '1',
      source: row.getAttribute('data-row-source') || '',
      configTarget: row.getAttribute('data-row-target') || '',
      builtIn: row.getAttribute('data-row-built-in') === '1'
    };
  }

  function collectPathRows() {
    var dirty = 0;
    var payload = rows().map(function (row) {
      var isDirty = row.dataset.newRow === '1' || row.dataset.deleted === '1' || changed(field(row, 'label')) || changed(field(row, 'value')) || changed(field(row, 'based'));
      row.classList.toggle('edit-dirty', isDirty);
      if (isDirty) dirty += 1;
      return rowPayload(row);
    });
    return {rows: payload, dirtyCount: dirty};
  }

  function collectPathUpdates() { return collectPathRows(); }

  function markDirty(row) {
    row.classList.add('edit-dirty');
    Core.setInlineStatus('paths-save-status', 'Unsaved path registry changes.', 'dirty');
  }

  function updateValueMode(row) {
    var input = field(row, 'value');
    var based = field(row, 'based');
    if (!input || !based) return;
    input.placeholder = based.checked ? 'relative/path' : 'absolute path';
  }

  function newRowHtml() {
    var id = 'new-' + Date.now().toString(36);
    return '<article class="edit-field path-row-card edit-dirty" data-path-row="1" data-row-id="' + id + '" data-row-source="custom" data-row-target="" data-row-built-in="0" data-row-exists="0" data-new-row="1">' +
      '<header class="path-row-head"><input class="path-row-name" data-row-field="label" data-original="" value="" placeholder="entryName" /><span class="status unknown">new</span></header>' +
      '<label class="path-row-check"><input type="checkbox" data-row-field="based" data-original="1" checked /> based on suiteRoot</label>' +
      '<input class="path-row-value" data-row-field="value" data-original="" value="" placeholder="relative/path" />' +
      '<div class="edit-expression">${suiteRoot}/relative/path</div><div class="edit-meta"><span>custom</span><span>new</span></div>' +
      '<footer class="path-row-actions"><button data-path-delete="1" title="Remove row">-</button></footer></article>';
  }

  function addPathRow() {
    var grid = document.querySelector('#paths-card .path-registry-grid');
    if (!grid) return;
    grid.insertAdjacentHTML('beforeend', newRowHtml());
    var row = grid.lastElementChild;
    bindRow(row);
    markDirty(row);
    var name = field(row, 'label');
    if (name) name.focus();
  }

  function toggleDelete(row, button) {
    if (row.dataset.newRow === '1') { row.remove(); return; }
    var deleted = row.dataset.deleted !== '1';
    row.dataset.deleted = deleted ? '1' : '0';
    row.classList.toggle('is-deleted', deleted);
    Array.prototype.forEach.call(row.querySelectorAll('input'), function (input) { if (input.getAttribute('data-row-field') !== 'based') input.readOnly = deleted; });
    if (button) button.textContent = deleted ? 'Undo' : '-';
    markDirty(row);
  }

  function bindRow(row) {
    if (!row || row.dataset.noesisBound === '1') return;
    row.dataset.noesisBound = '1';
    Array.prototype.forEach.call(row.querySelectorAll('[data-row-field]'), function (input) {
      input.addEventListener('input', function () { updateValueMode(row); markDirty(row); });
      input.addEventListener('change', function () { updateValueMode(row); markDirty(row); });
    });
    var del = row.querySelector('[data-path-delete]');
    if (del && !del.disabled) del.addEventListener('click', function () { toggleDelete(row, del); });
    updateValueMode(row);
  }

  function bindDirtyInputs() { rows().forEach(bindRow); }
  function applySavedPaths(j) {
    if (j.paths && global.NoesisDashboardState) {
      var data = Core.dashboardData();
      data.paths = j.paths;
      global.NoesisDashboardState.set(data);
      if (global.NoesisDashboard && typeof global.NoesisDashboard.renderAll === 'function') global.NoesisDashboard.renderAll();
    }
  }
  function savePaths(button) {
    var finish = Core.buttonStart(button, 'Saving...');
    Console.ensureConsole();
    Core.setInlineStatus('paths-save-status', 'Saving path rows...', 'running');
    var payload = collectPathRows();
    if (!payload.dirtyCount) {
      Console.renderOperation({status:'ok', title:'save path rows', startedUtc:Core.nowIso(), finishedUtc:Core.nowIso(), report:{message:'No path row changes to save.'}});
      Core.setInlineStatus('paths-save-status', 'No changes.', 'ok');
      finish('ok', 'No changes');
      Core.notify('info', 'Nothing to save.');
      return;
    }
    Console.renderOperation({status:'starting', title:'save path rows', startedUtc:Core.nowIso(), totalSteps:2, completedSteps:1, report:{rows:payload.rows}});
    Core.jsonFetch('/api/config/paths', {method:'POST', body: JSON.stringify({rows: payload.rows})}).then(function (j) {
      var ok = !!j.ok;
      Console.renderOperation({status: ok ? 'ok' : 'failed', title:'save path rows', totalSteps:2, completedSteps:2, finishedUtc:Core.nowIso(), report:j, stderr:ok ? '' : (j.error || 'path row update failed')});
      Core.setInlineStatus('paths-save-status', ok ? 'Saved. Dashboard paths are synchronized with runtime config.' : 'Save failed: ' + (j.error || 'validation error'), ok ? 'ok' : 'failed');
      if (ok) applySavedPaths(j);
      finish(ok ? 'ok' : 'failed');
      Core.notify(ok ? 'success' : 'error', ok ? 'Path rows saved.' : 'Path row save failed.');
    }).catch(function (err) {
      Console.renderOperation({status:'failed', title:'save path rows', stderr:String(err), finishedUtc:Core.nowIso()});
      Core.setInlineStatus('paths-save-status', 'Save failed: ' + String(err), 'failed');
      finish('failed');
      Core.notify('error', 'Path row save failed.');
    });
  }
  function fixMissingPaths(button) {
    var finish = Core.buttonStart(button, 'Fixing...');
    Console.ensureConsole();
    Core.setInlineStatus('paths-save-status', 'Fixing missing path rows...', 'running');
    var payload = collectPathRows();
    var missingCount = rows().filter(function (row) { return row.dataset.deleted !== '1' && row.dataset.rowExists === '0'; }).length;
    if (!payload.dirtyCount && !missingCount) {
      Console.renderOperation({status:'ok', title:'fix missing path rows', startedUtc:Core.nowIso(), finishedUtc:Core.nowIso(), report:{message:'No missing path rows detected.'}});
      Core.setInlineStatus('paths-save-status', 'No missing paths detected.', 'ok');
      finish('ok', 'No missing');
      Core.notify('info', 'No missing paths detected.');
      return;
    }
    Console.renderOperation({status:'starting', title:'fix missing path rows', startedUtc:Core.nowIso(), totalSteps:2, completedSteps:1, report:{rows:payload.rows, missingRows:missingCount}});
    Core.jsonFetch('/api/config/paths', {method:'POST', body: JSON.stringify({rows: payload.rows, fixMissing: true})}).then(function (j) {
      var ok = !!j.ok;
      var created = Array.isArray(j.createdMissing) ? j.createdMissing.length : 0;
      Console.renderOperation({status: ok ? 'ok' : 'failed', title:'fix missing path rows', totalSteps:2, completedSteps:2, finishedUtc:Core.nowIso(), report:j, stderr:ok ? '' : (j.error || 'path row fix failed')});
      Core.setInlineStatus('paths-save-status', ok ? 'Fixed missing paths. Created: ' + created + '.' : 'Fix failed: ' + (j.error || 'validation error'), ok ? 'ok' : 'failed');
      if (ok) applySavedPaths(j);
      finish(ok ? 'ok' : 'failed');
      Core.notify(ok ? 'success' : 'error', ok ? 'Missing paths fixed: ' + created + '.' : 'Path fix failed.');
    }).catch(function (err) {
      Console.renderOperation({status:'failed', title:'fix missing path rows', stderr:String(err), finishedUtc:Core.nowIso()});
      Core.setInlineStatus('paths-save-status', 'Fix failed: ' + String(err), 'failed');
      finish('failed');
      Core.notify('error', 'Path fix failed.');
    });
  }
  function bindPathControls() {
    var save = $('save-paths');
    var add = $('add-path-row'), fix = $('fix-missing-paths');
    if (save && save.dataset.noesisBound !== '1') {
      save.dataset.noesisBound = '1';
      save.addEventListener('click', function () { savePaths(save); });
    }
    if (add && add.dataset.noesisBound !== '1') {
      add.dataset.noesisBound = '1';
      add.addEventListener('click', addPathRow);
    }
    if (fix && fix.dataset.noesisBound !== '1') {
      fix.dataset.noesisBound = '1';
      fix.addEventListener('click', function () { fixMissingPaths(fix); });
    }
  }
  global.NoesisOperationPaths = Object.freeze({collectPathUpdates: collectPathUpdates, savePaths: savePaths, fixMissingPaths: fixMissingPaths, bindDirtyInputs: bindDirtyInputs, bindPathControls: bindPathControls});
})(window);
