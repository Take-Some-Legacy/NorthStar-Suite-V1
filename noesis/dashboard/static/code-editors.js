// NOESIS Dashboard CodeMirror integration
(function () {
  'use strict';

  var taskArgsEditor = null;
  var outputEditor = null;

  function $(id) { return document.getElementById(id); }
  function cm() { return window.CodeMirror || null; }

  function refreshEditor(editor) {
    if (!editor) return;
    window.setTimeout(function () { editor.refresh(); }, 0);
  }

  function normalizeMode(mode) {
    var value = String(mode || '').toLowerCase();
    if (value === 'json' || value === 'application/json') return {name: 'javascript', json: true};
    if (value === 'diff' || value === 'text/x-diff') return 'text/x-diff';
    if (value === 'shell' || value === 'bash' || value === 'text/x-sh') return 'text/x-sh';
    if (value === 'python' || value === 'text/x-python') return 'text/x-python';
    if (value === 'javascript' || value === 'js') return 'javascript';
    return {name: 'javascript', json: true};
  }

  function inferMode(text) {
    var sample = String(text || '').trim();
    if (!sample) return 'application/json';
    if (sample.indexOf('diff --git ') === 0 || sample.indexOf('@@ ') === 0) return 'text/x-diff';
    if (sample.indexOf('{') === 0 || sample.indexOf('[') === 0) return 'application/json';
    if (sample.indexOf('python -m ') >= 0 || sample.indexOf('$ ') >= 0 || sample.indexOf('PS ') >= 0) return 'text/x-sh';
    return 'application/json';
  }

  function bindTaskArgs() {
    var CodeMirror = cm();
    var textarea = $('task-args-json');
    if (!CodeMirror || !textarea || taskArgsEditor || textarea.dataset.noesisCodeMirror === '1') return;
    textarea.dataset.noesisCodeMirror = '1';
    taskArgsEditor = CodeMirror.fromTextArea(textarea, {
      mode: {name: 'javascript', json: true},
      theme: 'material-darker',
      lineNumbers: true,
      lineWrapping: true,
      tabSize: 2,
      indentUnit: 2,
      smartIndent: true,
      viewportMargin: 8
    });
    taskArgsEditor.on('change', function () {
      textarea.value = taskArgsEditor.getValue();
      try { textarea.dispatchEvent(new Event('input', {bubbles: true})); } catch (_) {}
    });
    refreshEditor(taskArgsEditor);
  }

  function bindOutput() {
    var CodeMirror = cm();
    var target = $('op-console-output');
    if (!CodeMirror || !target || outputEditor) {
      refreshEditor(outputEditor);
      return;
    }
    var initial = target.textContent || '';
    var container = document.createElement('div');
    container.id = 'op-console-output';
    container.className = 'op-output op-code-output';
    container.setAttribute('data-code-output', target.getAttribute('data-code-output') || 'json');
    container.setAttribute('aria-live', 'polite');
    target.parentNode.replaceChild(container, target);
    outputEditor = CodeMirror(container, {
      value: initial,
      mode: normalizeMode(inferMode(initial)),
      theme: 'material-darker',
      readOnly: 'nocursor',
      lineNumbers: false,
      lineWrapping: true,
      tabSize: 2,
      indentUnit: 2,
      viewportMargin: Infinity
    });
    outputEditor.setSize('100%', '100%');
    refreshEditor(outputEditor);
  }

  function bind() {
    bindTaskArgs();
    bindOutput();
  }

  function getTaskArgsValue() {
    if (taskArgsEditor) return taskArgsEditor.getValue();
    var textarea = $('task-args-json');
    return textarea ? textarea.value : '';
  }

  function setTaskArgsValue(value) {
    var next = String(value == null ? '' : value);
    if (!taskArgsEditor) bindTaskArgs();
    if (taskArgsEditor) {
      taskArgsEditor.setValue(next);
      refreshEditor(taskArgsEditor);
      return;
    }
    var textarea = $('task-args-json');
    if (textarea) textarea.value = next;
  }

  function setOutput(value, mode) {
    var text = String(value == null ? '' : value);
    if (!outputEditor) bindOutput();
    if (outputEditor) {
      outputEditor.setOption('mode', normalizeMode(mode || inferMode(text)));
      if (outputEditor.getValue() !== text) outputEditor.setValue(text);
      outputEditor.setCursor({line: Math.max(0, outputEditor.lineCount() - 1), ch: 0});
      refreshEditor(outputEditor);
      return;
    }
    var target = $('op-console-output');
    if (target) target.textContent = text;
  }

  window.NoesisCodeEditors = Object.freeze({
    bind: bind,
    getTaskArgsValue: getTaskArgsValue,
    setTaskArgsValue: setTaskArgsValue,
    setOutput: setOutput,
    refresh: function () {
      refreshEditor(taskArgsEditor);
      refreshEditor(outputEditor);
    }
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
})();
