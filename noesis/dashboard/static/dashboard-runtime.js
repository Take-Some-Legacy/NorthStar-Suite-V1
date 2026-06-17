// NOESIS dashboard bootstrap and control bindings.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var State = global.NoesisDashboardState;
  var Overview = global.NoesisDashboardOverview;
  var Actions = global.NoesisDashboardActions;
  var Runs = global.NoesisDashboardRuns;

  function $(id) { return Dom.$ ? Dom.$(id) : document.getElementById(id); }
  function copyText(text) { if (Dom.copyText) Dom.copyText(text); }
  function bindExternalOperations() { if (global.NoesisOperations && typeof global.NoesisOperations.bind === 'function') global.NoesisOperations.bind(); }

  function renderAll() {
    if (Overview) Overview.render();
    if (Actions) Actions.render();
    if (Runs) Runs.render();
    bindExternalOperations();
  }

  function refresh() {
    return State.track(fetch('/dashboard/data.json?refresh=1')).then(function (response) { return response.ok ? response.json() : Promise.reject(new Error('dashboard data unavailable')); })
      .catch(function () { return State.track(fetch('/api/runs?refresh=1')).then(function (response) { return response.ok ? response.json() : State.get(); }); })
      .then(function (nextData) { State.set(nextData || State.get()); renderAll(); })
      .catch(renderAll);
  }

  function bindStaticControls() {
    ['search', 'scope', 'status'].forEach(function (id) { if ($(id)) $(id).addEventListener('input', function () { if (Runs) Runs.render(); }); });
    ['action-search', 'action-group', 'action-danger'].forEach(function (id) { if ($(id)) $(id).addEventListener('input', function () { if (Actions) Actions.render(); }); });
    if ($('copy-selected-action')) $('copy-selected-action').addEventListener('click', function () { copyText(Actions ? Actions.selectedCommand() : ''); });
    if ($('copy-paths-json')) $('copy-paths-json').addEventListener('click', function () { copyText(JSON.stringify(State.get().paths || {}, null, 2)); });
    if ($('copy-runtime-path')) $('copy-runtime-path').addEventListener('click', function () { copyText(((((State.get().paths || {}).entries || {}).runtimeConfig || {}).path) || ''); });
    if ($('refresh')) $('refresh').addEventListener('click', refresh);
    if ($('copy-run-json')) $('copy-run-json').addEventListener('click', function () { if (Runs) Runs.copyRunJson(); });
    if ($('copy-patch-show')) $('copy-patch-show').addEventListener('click', function () { if (Runs) Runs.copyPatchShow(); });
    if ($('copy-patch-check')) $('copy-patch-check').addEventListener('click', function () { if (Runs) Runs.copyPatchCheck(); });
    if ($('burger')) $('burger').addEventListener('click', function () { document.body.classList.toggle('nav-open'); });
    document.querySelectorAll('[data-jump]').forEach(function (button) {
      button.addEventListener('click', function () {
        document.querySelectorAll('[data-jump]').forEach(function (item) { item.classList.remove('active'); });
        button.classList.add('active');
        document.body.classList.remove('nav-open');
        var target = document.getElementById(button.dataset.jump);
        if (target) target.scrollIntoView({behavior:'smooth'});
      });
    });
  }

  global.NoesisDashboard = Object.freeze({
    refresh: refresh,
    renderAll: renderAll,
    showRun: function (id) { return Runs && Runs.showRun(id); }
  });
  bindStaticControls();
  renderAll();
})(window);
