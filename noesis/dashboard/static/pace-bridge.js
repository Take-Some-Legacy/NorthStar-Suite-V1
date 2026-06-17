// NOESIS Dashboard Pace bridge
// NProgress-compatible command progress integration point.
(function () {
  'use strict';

  var active = 0;
  var fallback = null;
  var bar = null;
  var progress = 0;
  var tickTimer = null;
  var stopTimer = null;

  function getProgressApi() {
    return window.NProgress || null;
  }

  function hasProgressApi() {
    return !!getProgressApi();
  }

  function hasPace() {
    return !!(window.Pace && (typeof window.Pace.restart === 'function' || typeof window.Pace.start === 'function'));
  }

  function setBusy(enabled) {
    [document.documentElement, document.body].forEach(function (node) {
      if (!node) return;
      node.classList.toggle('noesis-pace-running', !!enabled);
    });
  }

  function ensureFallback() {
    if (hasPace() || fallback) return;
    fallback = document.createElement('div');
    fallback.className = 'pace pace-active noesis-pace-fallback';
    fallback.setAttribute('aria-hidden', 'true');
    bar = document.createElement('div');
    bar.className = 'pace-progress';
    fallback.appendChild(bar);
    (document.body || document.documentElement).appendChild(fallback);
  }

  function setProgress(value) {
    progress = Math.max(0, Math.min(100, Number(value) || 0));
    if (bar) {
      bar.style.transform = 'translate3d(' + progress + '%, 0, 0)';
      bar.setAttribute('data-progress', String(Math.round(progress)));
    }
  }

  function start() {
    window.clearTimeout(stopTimer);
    if (hasProgressApi()) {
      try {
        var progressApi = getProgressApi();
        if (progressApi.configure) progressApi.configure({minimum: 0.08, showSpinner: false, trickleSpeed: 180});
        if (progressApi.start) progressApi.start();
      } catch (_) {}
      setBusy(true);
      return;
    }
    if (hasPace()) {
      try {
        if (typeof window.Pace.restart === 'function') window.Pace.restart();
        else window.Pace.start();
      } catch (_) {}
      setBusy(true);
      return;
    }
    ensureFallback();
    if (!fallback) return;
    fallback.classList.remove('pace-inactive');
    fallback.classList.add('pace-active');
    setBusy(true);
    setProgress(Math.max(progress, 7));
    window.clearInterval(tickTimer);
    tickTimer = window.setInterval(function () {
      if (progress < 92) setProgress(progress + Math.max(0.75, (95 - progress) * 0.045));
    }, 140);
  }

  function stop() {
    if (active > 0) return;
    if (hasProgressApi()) {
      try {
        var progressApi = getProgressApi();
        if (progressApi.done) progressApi.done(true);
      } catch (_) {}
      setBusy(false);
      return;
    }
    if (hasPace()) {
      try { if (typeof window.Pace.stop === 'function') window.Pace.stop(); } catch (_) {}
      setBusy(false);
      return;
    }
    if (!fallback) return;
    window.clearInterval(tickTimer);
    setProgress(100);
    stopTimer = window.setTimeout(function () {
      if (!fallback) return;
      fallback.classList.remove('pace-active');
      fallback.classList.add('pace-inactive');
      setBusy(false);
      if (fallback.parentNode) fallback.parentNode.removeChild(fallback);
      fallback = null;
      bar = null;
      progress = 0;
    }, 240);
  }

  function trackPromise(promise) {
    active += 1;
    start();
    return Promise.resolve(promise).then(function (value) {
      active = Math.max(0, active - 1);
      window.setTimeout(stop, 150);
      return value;
    }, function (error) {
      active = Math.max(0, active - 1);
      window.setTimeout(stop, 150);
      throw error;
    });
  }

  window.NoesisProgress = {start: start, stop: stop, trackPromise: trackPromise};
  window.NoesisPace = Object.freeze({start: start, stop: stop, trackPromise: trackPromise});
})();
