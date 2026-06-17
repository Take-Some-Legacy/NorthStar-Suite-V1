// NOESIS operation console renderer and polling.
(function (global) {
  'use strict';

  var Core = global.NoesisOperationsCore;
  if (!Core) return;
  var $ = Core.$;

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
    Core.bindCodeEditors();
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

  function renderOperation(op) {
    ensureConsole();
    op = op || {};
    var status = op.status || (op.ok === false ? 'failed' : 'running');
    Core.setText('op-status', status);
    Core.setText('op-id', op.operationId ? 'operationId: ' + op.operationId : 'operation: local/pending');
    Core.setText('op-title', op.actionId || op.title || '');
    Core.show($('op-spinner'), status === 'queued' || status === 'running' || status === 'starting');
    var total = Number(op.totalSteps || 0);
    var done = Number(op.completedSteps || 0);
    if (total > 0) setProgress((done / total) * 100, false);
    else setProgress(status === 'ok' ? 100 : status === 'failed' ? 100 : 35, status === 'queued' || status === 'running' || status === 'starting');
    Core.setConsoleOutput(Core.safeStringify(op), 'application/json');
    focusConsole();
  }

  function pollOperation(operationId, finishButton) {
    renderOperation({operationId: operationId, status: 'running', report:{message:'Polling operation status...'}});
    var stop = false;
    function tick() {
      if (stop) return;
      Core.jsonFetch('/api/operations/' + encodeURIComponent(operationId)).then(function (j) {
        var op = j.operation || j;
        renderOperation(op);
        if (op.status === 'queued' || op.status === 'running') {
          global.setTimeout(tick, 900);
        } else {
          stop = true;
          if (finishButton) finishButton(op.status === 'ok' ? 'ok' : 'failed');
          Core.notify(op.status === 'ok' ? 'success' : 'error', op.status === 'ok' ? 'Operation completed.' : 'Operation failed.');
        }
      }).catch(function (err) {
        renderOperation({operationId: operationId, status: 'failed', stderr: String(err), finishedUtc: Core.nowIso()});
        stop = true;
        if (finishButton) finishButton('failed');
      });
    }
    tick();
  }

  global.NoesisOperationConsole = Object.freeze({
    ensureConsole: ensureConsole,
    focusConsole: focusConsole,
    renderOperation: renderOperation,
    pollOperation: pollOperation
  });
})(window);
