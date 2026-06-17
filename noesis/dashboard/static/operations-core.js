// NOESIS operations core helpers.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};

  function $(id) { return Dom.$ ? Dom.$(id) : document.getElementById(id); }
  function dashboardData() { return Dom.dashboardData ? Dom.dashboardData() : (global.NOESIS_DASHBOARD || global.__NOESIS_RUNS__ || {}); }
  function htmlEscape(value) { return Dom.esc ? Dom.esc(value) : String(value == null ? '' : value); }
  function setText(id, value) { if (Dom.setText) return Dom.setText(id, value); var el = $(id); if (el) el.textContent = value; }
  function show(el, yes) { if (Dom.show) return Dom.show(el, yes); if (el) el.hidden = !yes; }

  function codeEditors() { return global.NoesisCodeEditors || null; }

  function bindCodeEditors() {
    var editors = codeEditors();
    if (editors && typeof editors.bind === 'function') editors.bind();
  }

  function setConsoleOutput(text, mode) {
    var editors = codeEditors();
    if (editors && typeof editors.setOutput === 'function') {
      editors.setOutput(text, mode || 'application/json');
      return;
    }
    var out = $('op-console-output');
    if (out) out.textContent = text;
  }

  function taskArgsRaw() {
    var editors = codeEditors();
    if (editors && typeof editors.getTaskArgsValue === 'function') return editors.getTaskArgsValue();
    return $('task-args-json') ? $('task-args-json').value : '';
  }

  function safeStringify(value) {
    try { return JSON.stringify(value, null, 2); }
    catch (err) { return JSON.stringify({error: 'output_stringify_failed', message: String(err)}, null, 2); }
  }

  function jsonFetch(url, options) {
    if (Dom.jsonFetch) return Dom.jsonFetch(url, options);
    options = options || {};
    options.headers = Object.assign({'Content-Type':'application/json'}, options.headers || {});
    return fetch(url, options).then(function (r) {
      return r.json().then(function (j) {
        j.__httpStatus = r.status;
        return j;
      });
    });
  }

  function nowIso() { return new Date().toISOString(); }

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
      global.setTimeout(function () {
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

  function notify(type, message) {
    if (global.NoesisToast && typeof global.NoesisToast.notify === 'function') {
      return global.NoesisToast.notify(type, message);
    }
  }

  global.NoesisOperationsCore = Object.freeze({
    $: $,
    dashboardData: dashboardData,
    htmlEscape: htmlEscape,
    setText: setText,
    show: show,
    codeEditors: codeEditors,
    bindCodeEditors: bindCodeEditors,
    setConsoleOutput: setConsoleOutput,
    taskArgsRaw: taskArgsRaw,
    safeStringify: safeStringify,
    jsonFetch: jsonFetch,
    nowIso: nowIso,
    buttonStart: buttonStart,
    setInlineStatus: setInlineStatus,
    notify: notify
  });
})(window);
