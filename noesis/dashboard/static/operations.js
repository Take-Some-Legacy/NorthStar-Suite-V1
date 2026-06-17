// NOESIS Dashboard Operation Console bootstrap.
(function (global) {
  'use strict';

  var Core = global.NoesisOperationsCore;
  var Console = global.NoesisOperationConsole;
  var Paths = global.NoesisOperationPaths;
  var Actions = global.NoesisOperationActions;
  var Tasks = global.NoesisOperationTasks;
  var Autocomplete = global.NoesisOperationAutocomplete;

  function bind() {
    if (!Core || !Console || !Paths || !Actions || !Tasks || !Autocomplete) return;
    Console.ensureConsole();
    Actions.bindActionRows();
    Paths.bindDirtyInputs();
    Autocomplete.setupCommandAutocomplete();
    Tasks.bindTaskControls();
    Paths.bindPathControls();
    Actions.bindActionControls();
  }

  global.NoesisOperations = Object.freeze({
    bind: bind,
    renderOperation: Console && Console.renderOperation,
    pollOperation: Console && Console.pollOperation,
    collectPathUpdates: Paths && Paths.collectPathUpdates,
    savePaths: Paths && Paths.savePaths,
    runSelectedAction: Actions && Actions.runSelectedAction,
    submitTask: Tasks && Tasks.submitTask
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
})(window);
