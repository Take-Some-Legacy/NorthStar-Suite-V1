// NOESIS dashboard state and shared render helpers.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var dataNode = document.getElementById('runs-data');
  var DATA = dataNode ? JSON.parse(dataNode.textContent || '{}') : {};

  function set(nextData) {
    DATA = nextData || DATA || {};
    global.NOESIS_DASHBOARD = DATA;
    global.__NOESIS_RUNS__ = DATA;
    return DATA;
  }

  function get() { return DATA || {}; }
  function worker() { return get().worker || get().node || {}; }
  function nodeGroup() { return worker().nodeGroup || worker().cluster || {}; }
  function statusClass(value) { return ['merge_ready', 'rejected'].indexOf(value) >= 0 ? value : 'unknown'; }
  function duration(ms) { return !ms ? '' : (ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's'); }
  function track(promise) { return Dom.trackRequest ? Dom.trackRequest(promise) : promise; }

  set(DATA);

  global.NoesisDashboardState = Object.freeze({
    get: get,
    set: set,
    worker: worker,
    nodeGroup: nodeGroup,
    statusClass: statusClass,
    duration: duration,
    track: track
  });
})(window);
