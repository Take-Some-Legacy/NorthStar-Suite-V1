// NOESIS dashboard path rows registry renderer.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var State = global.NoesisDashboardState;
  if (!State) return;
  var esc = Dom.esc || function (value) { return String(value == null ? '' : value); };
  var setHtml = Dom.setHtml || function (id, html) { var el = document.getElementById(id); if (el) el.innerHTML = html; };

  function badge(row) {
    if (row.locked) return '<span class="status ok">constant</span>';
    return '<span class="status ' + (row.exists ? 'ok' : 'bad') + '">' + (row.exists ? 'exists' : 'missing') + '</span>';
  }

  function expression(row) {
    return row.basedOnSuiteRoot ? '${suiteRoot}/' + (row.relative || row.value || '.') : (row.path || row.value || '');
  }

  function rowCard(row) {
    var locked = !!row.locked;
    var based = !!row.basedOnSuiteRoot;
    return '<article class="edit-field path-row-card" data-path-row="1" data-row-id="' + esc(row.id) + '" data-row-source="' + esc(row.source || '') + '" data-row-target="' + esc(row.configTarget || '') + '" data-row-built-in="' + (row.builtIn ? '1' : '0') + '" data-row-exists="' + (row.exists ? '1' : '0') + '" data-original-deleted="0">' +
      '<header class="path-row-head"><input class="path-row-name" data-row-field="label" data-original="' + esc(row.label || row.id) + '" value="' + esc(row.label || row.id) + '" ' + (locked ? 'readonly' : '') + ' />' + badge(row) + '</header>' +
      '<label class="path-row-check"><input type="checkbox" data-row-field="based" data-original="' + (based ? '1' : '0') + '" ' + (based ? 'checked' : '') + ' ' + (locked ? 'disabled' : '') + ' /> based on suiteRoot</label>' +
      '<input class="path-row-value" data-row-field="value" data-original="' + esc(row.value || '') + '" value="' + esc(row.value || '') + '" ' + (locked ? 'readonly' : '') + ' placeholder="' + (based ? 'relative/path' : 'absolute path') + '" />' +
      '<div class="edit-expression">' + esc(expression(row)) + '</div>' +
      '<div class="edit-meta"><span>' + esc(row.source || row.kind || 'path') + '</span><span>' + esc(row.id) + '</span>' + (locked ? '<span>locked</span>' : '') + '</div>' +
      '<footer class="path-row-actions">' + (locked ? '<button disabled>-</button>' : '<button data-path-delete="1" title="Delete or restore row">-</button>') + '</footer>' +
    '</article>';
  }

  function fallbackPathRows(paths) {
    var rows = [];
    var bases = paths.baseRoots || {};
    Object.keys(bases).forEach(function (key) {
      var entry = bases[key] || {};
      rows.push({id:key, label:key, source:'legacy', value:entry.path || '', path:entry.path || '', exists:!!entry.exists, locked:key === 'suiteRoot', builtIn:true});
    });
    return rows;
  }

  function render() {
    var paths = State.get().paths || {};
    var rows = paths.rows || fallbackPathRows(paths);
    var suiteRoot = paths.suiteRootPath || (((paths.entries || {}).suiteRoot || {}).path) || '';
    setHtml('paths-card', [
      '<section class="edit-section path-registry" data-suite-root="' + esc(suiteRoot) + '">',
      '<div class="path-registry-toolbar"><h4>Path Rows Registry</h4><button id="add-path-row" class="primary" type="button">+ Add row</button></div>',
      '<div class="muted">suiteRoot is immutable. Rows based on suiteRoot store only relative paths.</div>',
      '<div class="path-registry-grid">' + rows.map(rowCard).join('') + '</div>',
      '</section>'
    ].join(''));
  }

  global.NoesisDashboardPaths = Object.freeze({render: render});
})(window);
