// NOESIS dashboard cluster control plane renderer.
(function (global) {
  'use strict';

  var Dom = global.NoesisDom || {};
  var State = global.NoesisDashboardState;
  if (!State) return;

  var STORE_KEY = 'noesis.dashboard.cluster.settings.v1';
  var esc = Dom.esc || function (value) { return String(value == null ? '' : value); };
  var setHtml = Dom.setHtml || function (id, html) { var el = document.getElementById(id); if (el) el.innerHTML = html; };
  var copyText = Dom.copyText || function () {};

  function $(id) { return Dom.$ ? Dom.$(id) : document.getElementById(id); }
  function data() { return State.get().cluster || {}; }
  function cfg() { return data().config || {}; }
  function defaults() {
    var d = (cfg().diagnostics || {});
    var ui = (cfg().ui || {});
    return {
      profile: data().profile || 'single-host-first',
      timeoutSec: Number(d.timeoutSec || 1.5),
      includeStatus: d.includeStatus !== false,
      includeDisabled: !!d.includeDisabled,
      showDisabled: !!ui.showDisabled,
      viewMode: ui.viewMode || 'topology',
      peerFilter: ui.peerFilter || ''
    };
  }

  function loadSettings() {
    try {
      var parsed = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
      return Object.assign(defaults(), parsed || {});
    } catch (_) {
      return defaults();
    }
  }

  function saveSettings(settings) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(settings)); } catch (_) {}
  }

  function bool(value) { return value === true || value === 'true' || value === '1' || value === 'on'; }

  function command(settings) {
    var timeout = Number(settings.timeoutSec || 1.5);
    var out = 'python -m noesis bridge endpoint cluster-doctor --timeout ' + timeout + ' --json';
    if (!settings.includeStatus) out += ' --skip-status';
    if (settings.includeDisabled) out += ' --include-disabled';
    return out;
  }

  function kvRow(key, value) {
    return '<div><span>' + esc(key) + '</span><b>' + esc(value == null || value === '' ? 'unknown' : value) + '</b></div>';
  }

  function option(value, label, selected) {
    return '<option value="' + esc(value) + '"' + (value === selected ? ' selected' : '') + '>' + esc(label || value) + '</option>';
  }

  function profileOptions(settings) {
    var profiles = data().profiles || [];
    if (!profiles.length) profiles = [{id: settings.profile, title: settings.profile}];
    return profiles.map(function (profile) { return option(profile.id, profile.title || profile.id, settings.profile); }).join('');
  }

  function peerMatches(peer, settings) {
    if (!settings.showDisabled && peer.enabled === false) return false;
    var q = String(settings.peerFilter || '').toLowerCase().trim();
    if (!q) return true;
    return [peer.machineId, peer.role, peer.publicOrigin, peer.endpointUrl, (peer.tags || []).join(' ')].join(' ').toLowerCase().indexOf(q) >= 0;
  }

  function renderTopology(settings) {
    var cluster = data();
    var topology = cluster.topology || {};
    var local = cluster.local || {};
    setHtml('cluster-card', [
      kvRow('enabled', cluster.enabled),
      kvRow('cluster', topology.clusterId || local.clusterId),
      kvRow('machine', local.machineId),
      kvRow('role', local.role),
      kvRow('profile', settings.profile),
      kvRow('network', topology.networkMode || local.networkMode),
      kvRow('machines', topology.machineCount || 1),
      kvRow('endpoint', local.endpointUrl || local.endpointPath)
    ].join(''));
    var tag = $('cluster-mode-tag');
    if (tag) tag.textContent = (topology.peerCount || 0) ? 'federated' : 'single node';
  }

  function renderPeers(settings) {
    var peers = data().peers || [];
    var visible = peers.filter(function (peer) { return peerMatches(peer, settings); });
    if (!visible.length) {
      setHtml('cluster-peer-list', '<div class="cluster-empty">No peers visible for current filter.</div>');
      return;
    }
    setHtml('cluster-peer-list', visible.map(function (peer) {
      var status = peer.enabled === false ? 'disabled' : 'enabled';
      return '<div class="cluster-peer ' + esc(status) + '"><strong>' + esc(peer.machineId || 'peer') + '</strong><span>' + esc(peer.role || 'peer') + '</span><code>' + esc(peer.endpointUrl || peer.publicOrigin || '') + '</code></div>';
    }).join(''));
  }

  function renderSettings(settings) {
    setHtml('cluster-settings', [
      '<label>Profile<select id="cluster-profile">' + profileOptions(settings) + '</select></label>',
      '<label>Doctor timeout <input id="cluster-timeout" type="number" min="0.25" max="30" step="0.25" value="' + esc(settings.timeoutSec) + '"></label>',
      '<label>Peer filter <input id="cluster-peer-filter" type="search" value="' + esc(settings.peerFilter || '') + '" placeholder="machine, role, origin, tag"></label>',
      '<label>View mode<select id="cluster-view-mode">' + [option('topology', 'Topology', settings.viewMode), option('doctor', 'Doctor', settings.viewMode), option('peers', 'Peers', settings.viewMode), option('strict', 'Strict review', settings.viewMode)].join('') + '</select></label>',
      '<label class="cluster-check"><input id="cluster-include-status" type="checkbox"' + (settings.includeStatus ? ' checked' : '') + '> include /status probe</label>',
      '<label class="cluster-check"><input id="cluster-include-disabled" type="checkbox"' + (settings.includeDisabled ? ' checked' : '') + '> include disabled peers in doctor</label>',
      '<label class="cluster-check"><input id="cluster-show-disabled" type="checkbox"' + (settings.showDisabled ? ' checked' : '') + '> show disabled peers</label>'
    ].join(''));
  }

  function renderCommands(settings) {
    var commands = data().commands || {};
    var preview = $('cluster-command-preview');
    if (preview) preview.textContent = command(settings);
    setHtml('cluster-hints', [
      '<div><span>Runtime config</span><b>' + esc((cfg() || {}).runtimeConfig || 'config/noesis/runtime.v1.json') + '</b></div>',
      '<div><span>Doctor</span><b>' + esc(command(settings)) + '</b></div>',
      '<div><span>Binding</span><b>' + esc(commands.binding || 'python -m noesis bridge endpoint binding --json') + '</b></div>',
      '<div><span>Init host</span><b>' + esc(commands.initHost || '') + '</b></div>'
    ].join(''));
  }

  function currentSettingsFromDom() {
    var settings = loadSettings();
    if ($('cluster-profile')) settings.profile = $('cluster-profile').value;
    if ($('cluster-timeout')) settings.timeoutSec = Number($('cluster-timeout').value || settings.timeoutSec || 1.5);
    if ($('cluster-peer-filter')) settings.peerFilter = $('cluster-peer-filter').value || '';
    if ($('cluster-view-mode')) settings.viewMode = $('cluster-view-mode').value || 'topology';
    if ($('cluster-include-status')) settings.includeStatus = bool($('cluster-include-status').checked);
    if ($('cluster-include-disabled')) settings.includeDisabled = bool($('cluster-include-disabled').checked);
    if ($('cluster-show-disabled')) settings.showDisabled = bool($('cluster-show-disabled').checked);
    return settings;
  }

  function rerenderFromDom() {
    var settings = currentSettingsFromDom();
    saveSettings(settings);
    renderTopology(settings);
    renderPeers(settings);
    renderCommands(settings);
  }

  function bind() {
    var root = $('cluster-block');
    if (!root || root.dataset.clusterBound === '1') return;
    root.dataset.clusterBound = '1';
    root.addEventListener('input', rerenderFromDom);
    root.addEventListener('change', rerenderFromDom);
    var copyDoctor = $('cluster-copy-doctor');
    var copyBinding = $('cluster-copy-binding');
    var reset = $('cluster-reset-settings');
    if (copyDoctor) copyDoctor.addEventListener('click', function () { copyText(command(currentSettingsFromDom())); });
    if (copyBinding) copyBinding.addEventListener('click', function () { copyText(((data().commands || {}).binding) || 'python -m noesis bridge endpoint binding --json'); });
    if (reset) reset.addEventListener('click', function () { try { localStorage.removeItem(STORE_KEY); } catch (_) {} render(); });
  }

  function render() {
    var settings = loadSettings();
    renderTopology(settings);
    renderPeers(settings);
    renderSettings(settings);
    renderCommands(settings);
    bind();
  }

  global.NoesisDashboardCluster = Object.freeze({render: render, settings: loadSettings, command: command});
})(window);
