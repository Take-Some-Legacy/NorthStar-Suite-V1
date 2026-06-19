// NOESIS repository space page.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var State = global.NoesisDashboardState;
  var STORAGE_KEY = 'noesis.dashboard.repositories.draft.v1';
  var selectedId = '';
  var activePage = 'dashboard';

  function $(id) { return Dom.$ ? Dom.$(id) : document.getElementById(id); }
  function esc(value) { return Dom.escapeHtml ? Dom.escapeHtml(value == null ? '' : String(value)) : String(value == null ? '' : value); }
  function copyText(text) { if (Dom.copyText) Dom.copyText(text || ''); }
  function data() { return State ? State.get() : (global.NOESIS_DASHBOARD || {}); }
  function reposPayload() { return data().repositories || {}; }
  function rows() { return (reposPayload().rows || []).slice(); }

  function loadDraft() {
    try {
      var parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  function saveDraft(draft) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft || {}, null, 2));
  }

  function draftList() {
    var draft = loadDraft();
    return Array.isArray(draft.items) ? draft.items : [];
  }

  function setDraftList(items) {
    saveDraft({schema: 'noesis.dashboard.repositories.draft.v1', updatedUtc: new Date().toISOString(), items: items || []});
  }

  function makeKey(row) {
    return row.id || row.name || row.repoDir || row.indexFile || '';
  }

  function mergeRows() {
    var byKey = {};
    rows().forEach(function (row) {
      var key = makeKey(row);
      byKey[key] = Object.assign({}, row, {draftState: 'source'});
    });
    draftList().forEach(function (item) {
      var key = item.baseId || item.id || item.name || item.repoDir || '';
      if (!key) return;
      if (item.deleted) {
        if (byKey[key]) byKey[key] = Object.assign({}, byKey[key], item, {draftState: 'deleted'});
        return;
      }
      byKey[key] = Object.assign({}, byKey[key] || {}, item, {draftState: item.mode || (byKey[key] ? 'edited' : 'added')});
    });
    return Object.keys(byKey).map(function (key) { return byKey[key]; })
      .sort(function (a, b) {
        if (a.current && !b.current) return -1;
        if (!a.current && b.current) return 1;
        return String(a.name || '').localeCompare(String(b.name || ''));
      });
  }

  function filteredRows() {
    var query = (($('repo-search') || {}).value || '').toLowerCase().trim();
    var status = (($('repo-status-filter') || {}).value || 'all');
    var kind = (($('repo-kind-filter') || {}).value || 'all');
    return mergeRows().filter(function (row) {
      var text = [row.name, row.kind, row.description, row.repoDir, (row.tags || []).join(' ')].join(' ').toLowerCase();
      var state = row.draftState || row.status || '';
      var stateMatch = status === 'all' || (status === 'draft' ? state !== 'source' : row.status === status);
      var kindMatch = kind === 'all' || String(row.kind || '').toLowerCase() === kind;
      return (!query || text.indexOf(query) >= 0) && stateMatch && kindMatch;
    });
  }

  function repoIndexJson(row) {
    return {
      schema: 'takesome.repository_operator_index.v1',
      repository: {
        name: row.name || 'repository',
        kind: row.kind || 'repository',
        description: row.description || '',
        tags: Array.isArray(row.tags) ? row.tags : []
      },
      paths: {
        workdir: 'workspace',
        dataset_dir: 'dataset',
        artifacts_dir: 'workspace/artifacts',
        logs_dir: 'workspace/logs',
        tmp_dir: 'workspace/tmp'
      },
      tools: {required: [], optional: [{id: 'git', command: 'git', version_arg: '--version'}]},
      commands: {},
      operator: {read_roots: ['.', 'dataset', 'workspace'], write_roots: ['workspace', 'dataset']}
    };
  }

  function renderKinds() {
    var select = $('repo-kind-filter');
    if (!select) return;
    var current = select.value || 'all';
    var kinds = {};
    mergeRows().forEach(function (row) { if (row.kind) kinds[String(row.kind).toLowerCase()] = row.kind; });
    select.innerHTML = '<option value="all">All kinds</option>' + Object.keys(kinds).sort().map(function (key) {
      return '<option value="' + esc(key) + '">' + esc(kinds[key]) + '</option>';
    }).join('');
    select.value = kinds[current] ? current : 'all';
  }

  function renderSummary() {
    var payload = reposPayload();
    var all = mergeRows();
    var drafts = draftList();
    var root = (payload.source || {}).reposRoot || '—';
    if ($('repo-count')) $('repo-count').textContent = String(all.filter(function (row) { return row.draftState !== 'deleted'; }).length);
    if ($('repo-ok-count')) $('repo-ok-count').textContent = String(all.filter(function (row) { return row.ok && row.draftState !== 'deleted'; }).length);
    if ($('repo-draft-count')) $('repo-draft-count').textContent = String(drafts.length);
    if ($('repo-root-label')) $('repo-root-label').textContent = root;
  }

  function statePill(row) {
    var state = row.draftState && row.draftState !== 'source' ? row.draftState : row.status;
    return '<span class="repo-state ' + esc(state || 'unknown') + '">' + esc(state || 'unknown') + '</span>';
  }

  function renderTable() {
    var body = $('repo-table-body');
    if (!body) return;
    var list = filteredRows();
    body.innerHTML = list.map(function (row) {
      var key = esc(makeKey(row));
      var tags = (row.tags || []).map(function (tag) { return '<span class="repo-tag">' + esc(tag) + '</span>'; }).join('');
      var tools = Number(row.requiredTools || 0) + '/' + Number(row.optionalTools || 0);
      return '<tr data-repo-key="' + key + '">' +
        '<td><div class="repo-name"><strong>' + esc(row.name || 'unnamed') + (row.current ? ' <span class="repo-tag">current</span>' : '') + '</strong><span class="muted">' + esc(row.description || '') + '</span><div class="repo-tags">' + tags + '</div></div></td>' +
        '<td>' + esc(row.kind || '') + '</td>' +
        '<td>' + statePill(row) + '</td>' +
        '<td><code>' + esc(row.repoDir || '') + '</code></td>' +
        '<td>' + esc(tools) + '</td>' +
        '<td>' + esc(row.commandCount || 0) + '</td>' +
        '<td><div class="repo-actions"><button type="button" data-repo-edit="' + key + '">Edit</button><button type="button" data-repo-copy="' + key + '">Copy</button><button type="button" data-repo-delete="' + key + '">Delete</button></div></td>' +
        '</tr>';
    }).join('');
    if ($('repo-empty-state')) $('repo-empty-state').style.display = list.length ? 'none' : 'block';
  }

  function findRow(key) {
    return mergeRows().filter(function (row) { return makeKey(row) === key || row.baseId === key; })[0] || null;
  }

  function selectRow(row, mode) {
    row = row || {name: '', kind: '', repoDir: '', description: '', tags: []};
    selectedId = makeKey(row);
    if ($('repo-editor-title')) $('repo-editor-title').textContent = mode === 'add' ? 'Add repository' : (row.name || 'Repository');
    if ($('repo-editor-mode')) $('repo-editor-mode').textContent = mode || row.draftState || 'edit';
    if ($('repo-field-name')) $('repo-field-name').value = row.name || '';
    if ($('repo-field-kind')) $('repo-field-kind').value = row.kind || '';
    if ($('repo-field-dir')) $('repo-field-dir').value = row.repoDir || '';
    if ($('repo-field-description')) $('repo-field-description').value = row.description || '';
    if ($('repo-field-tags')) $('repo-field-tags').value = (row.tags || []).join(', ');
    renderDiagnostics(row);
  }

  function currentEditorRow() {
    var base = findRow(selectedId) || {};
    var name = (($('repo-field-name') || {}).value || '').trim();
    var repoDir = (($('repo-field-dir') || {}).value || '').trim();
    return Object.assign({}, base, {
      baseId: selectedId || makeKey(base),
      id: name || base.id || base.name || repoDir,
      name: name,
      kind: (($('repo-field-kind') || {}).value || '').trim() || 'repository',
      repoDir: repoDir,
      description: (($('repo-field-description') || {}).value || '').trim(),
      tags: (($('repo-field-tags') || {}).value || '').split(',').map(function (item) { return item.trim(); }).filter(Boolean),
      mode: base && makeKey(base) ? 'edited' : 'added'
    });
  }

  function renderDiagnostics(row) {
    var node = $('repo-diagnostics');
    if (!node) return;
    var diagnostics = (row && row.diagnostics) || [];
    var command = row && row.doctorCommand ? row.doctorCommand : 'python -m noesis env status --repo-dir <repo-dir> --json';
    node.innerHTML = '<div><strong>Index:</strong> <code>' + esc((row && row.indexFile) || 'draft') + '</code></div>' +
      '<div><strong>Status command:</strong> <code>' + esc(command) + '</code></div>' +
      (diagnostics.length ? '<div><strong>Diagnostics:</strong><ul>' + diagnostics.map(function (item) { return '<li>' + esc(item) + '</li>'; }).join('') + '</ul></div>' : '<div class="muted">No diagnostics for selected repository.</div>');
  }

  function saveSelectedDraft() {
    var item = currentEditorRow();
    if (!item.name || !item.repoDir) return;
    var items = draftList().filter(function (existing) { return (existing.baseId || existing.id) !== (item.baseId || item.id); });
    items.push(item);
    setDraftList(items);
    selectedId = item.baseId || item.id;
    render();
  }

  function deleteSelectedDraft() {
    var row = findRow(selectedId);
    if (!row) return;
    var key = makeKey(row);
    var items = draftList().filter(function (existing) { return (existing.baseId || existing.id) !== key; });
    items.push(Object.assign({}, row, {baseId: key, deleted: true, mode: 'deleted'}));
    setDraftList(items);
    render();
  }

  function clearDraft() {
    localStorage.removeItem(STORAGE_KEY);
    render();
  }

  function copyDraft() {
    copyText(JSON.stringify(loadDraft(), null, 2));
  }

  function showPage(page) {
    activePage = page || 'dashboard';
    document.body.classList.toggle('repositories-mode', activePage === 'repositories');
    document.querySelectorAll('[data-page-tab]').forEach(function (button) {
      button.classList.toggle('active', button.dataset.pageTab === activePage);
    });
    if (activePage === 'repositories') render();
    if (global.NoesisDashboardNavigation && typeof global.NoesisDashboardNavigation.refresh === 'function') global.NoesisDashboardNavigation.refresh();
  }

  function bind() {
    document.querySelectorAll('[data-page-tab]').forEach(function (button) {
      button.addEventListener('click', function () { showPage(button.dataset.pageTab || 'dashboard'); });
    });
    ['repo-search', 'repo-status-filter', 'repo-kind-filter'].forEach(function (id) {
      if ($(id)) $(id).addEventListener('input', render);
    });
    if ($('repo-add')) $('repo-add').addEventListener('click', function () { selectRow({name: '', kind: 'repository', repoDir: '', tags: []}, 'add'); });
    if ($('repo-save-draft')) $('repo-save-draft').addEventListener('click', saveSelectedDraft);
    if ($('repo-delete-draft')) $('repo-delete-draft').addEventListener('click', deleteSelectedDraft);
    if ($('repo-export-draft')) $('repo-export-draft').addEventListener('click', copyDraft);
    if ($('repo-clear-draft')) $('repo-clear-draft').addEventListener('click', clearDraft);
    if ($('repo-copy-index')) $('repo-copy-index').addEventListener('click', function () { copyText(JSON.stringify(repoIndexJson(currentEditorRow()), null, 2)); });
    if ($('repo-copy-command')) $('repo-copy-command').addEventListener('click', function () { copyText((findRow(selectedId) || currentEditorRow()).doctorCommand || 'python -m noesis env status --repo-dir <repo-dir> --json'); });
    document.addEventListener('click', function (event) {
      var edit = event.target.closest('[data-repo-edit]');
      var copy = event.target.closest('[data-repo-copy]');
      var del = event.target.closest('[data-repo-delete]');
      if (edit) selectRow(findRow(edit.dataset.repoEdit));
      if (copy) copyText(JSON.stringify(repoIndexJson(findRow(copy.dataset.repoCopy) || {}), null, 2));
      if (del) { selectedId = del.dataset.repoDelete; deleteSelectedDraft(); }
    });
  }

  function render() {
    renderKinds();
    renderSummary();
    renderTable();
    if (!selectedId && mergeRows()[0]) selectRow(mergeRows()[0]);
  }

  bind();

  global.NoesisDashboardRepositories = Object.freeze({
    render: render,
    showPage: showPage,
    draft: loadDraft
  });
})(window);
