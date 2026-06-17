// NOESIS shared browser utilities.
(function (global) {
  'use strict';

  function $(id) { return document.getElementById(id); }

  function dashboardData() {
    return global.NOESIS_DASHBOARD || global.__NOESIS_RUNS__ || {};
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c];
    });
  }

  function setHtml(id, html) {
    var el = $(id);
    if (el) el.innerHTML = html;
  }

  function setText(id, value) {
    var el = $(id);
    if (el) el.textContent = value == null ? '' : String(value);
  }

  function show(el, yes) {
    if (el) el.hidden = !yes;
  }

  function copyText(text) {
    try {
      if (navigator.clipboard) navigator.clipboard.writeText(text || '');
    } catch (_) {}
  }

  function progressBridge() {
    return global.NoesisProgress || global.NoesisPace || null;
  }

  function trackRequest(promise) {
    var bridge = progressBridge();
    return bridge && typeof bridge.trackPromise === 'function' ? bridge.trackPromise(promise) : promise;
  }

  function jsonFetch(url, options) {
    options = options || {};
    options.headers = Object.assign({'Content-Type':'application/json'}, options.headers || {});
    return trackRequest(fetch(url, options)).then(function (response) {
      return response.json().then(function (payload) {
        payload.__httpStatus = response.status;
        return payload;
      });
    });
  }

  global.NoesisDom = Object.freeze({
    $: $,
    dashboardData: dashboardData,
    esc: esc,
    htmlEscape: esc,
    setHtml: setHtml,
    setText: setText,
    show: show,
    copyText: copyText,
    progressBridge: progressBridge,
    trackRequest: trackRequest,
    jsonFetch: jsonFetch
  });
})(window);
