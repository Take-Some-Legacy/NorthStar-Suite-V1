// NOESIS dashboard scroll-aware navigation.
(function (global) {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }

  var nav = $('dashboard-nav');
  var main = document.querySelector('main');
  if (!nav || !main) return;

  var current = $('nav-current-section');
  var progress = $('nav-scroll-progress');
  var prev = $('nav-prev-section');
  var next = $('nav-next-section');
  var entries = [];
  var activeIndex = -1;
  var scheduled = false;

  function isVisible(el) {
    return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  }

  function buttonLabel(button) {
    return button.getAttribute('data-nav-label') || (button.childNodes[0] ? button.childNodes[0].textContent.trim() : button.textContent.trim());
  }

  function refreshEntries() {
    entries = Array.prototype.slice.call(nav.querySelectorAll('[data-jump]')).map(function (button) {
      var id = button.getAttribute('data-jump');
      return { id: id, label: buttonLabel(button), button: button, target: $(id) };
    }).filter(function (entry) { return !!entry.target; });
    return entries;
  }

  function visibleEntries() {
    if (!entries.length) refreshEntries();
    return entries.filter(function (entry) { return isVisible(entry.target); });
  }

  function updateProgress() {
    if (!progress) return;
    var max = Math.max(1, main.scrollHeight - main.clientHeight);
    var pct = clamp((main.scrollTop / max) * 100, 0, 100);
    progress.style.width = pct.toFixed(1) + '%';
  }

  function setActive(entry) {
    if (!entry) return;
    var index = entries.indexOf(entry);
    if (index === activeIndex) { updateProgress(); return; }
    activeIndex = index;
    entries.forEach(function (item) {
      var active = item === entry;
      item.button.classList.toggle('active', active);
      item.button.setAttribute('aria-current', active ? 'page' : 'false');
    });
    if (current) current.textContent = entry.label;
    document.body.dataset.dashboardSection = entry.id;
    try { entry.button.scrollIntoView({block: 'nearest'}); } catch (_) {}
    updateProgress();
  }

  function pickActive() {
    var list = visibleEntries();
    if (!list.length) return null;
    var rootRect = main.getBoundingClientRect();
    var line = rootRect.top + Math.min(170, Math.max(90, rootRect.height * 0.22));
    var currentCandidate = null;
    var belowCandidate = null;
    var closest = null;
    var closestDistance = Infinity;

    list.forEach(function (entry) {
      var rect = entry.target.getBoundingClientRect();
      var distance = Math.abs(rect.top - line);
      if (distance < closestDistance) { closestDistance = distance; closest = entry; }
      if (rect.top <= line && rect.bottom > line) { currentCandidate = entry; return; }
      if (!belowCandidate && rect.top > line) belowCandidate = entry;
      if (rect.top <= line) currentCandidate = entry;
    });

    return currentCandidate || belowCandidate || closest || list[0];
  }

  function update() {
    scheduled = false;
    setActive(pickActive());
  }

  function schedule() {
    updateProgress();
    if (scheduled) return;
    scheduled = true;
    global.requestAnimationFrame(update);
  }

  function scrollToEntry(entry) {
    if (!entry || !entry.target) return;
    document.body.classList.remove('nav-open');
    try { entry.target.scrollIntoView({behavior: 'smooth', block: 'start'}); }
    catch (_) { entry.target.scrollIntoView(); }
    setActive(entry);
  }

  function move(delta) {
    var list = visibleEntries();
    if (!list.length) return;
    var currentEntry = activeIndex >= 0 ? entries[activeIndex] : pickActive();
    var visibleIndex = Math.max(0, list.indexOf(currentEntry));
    scrollToEntry(list[clamp(visibleIndex + delta, 0, list.length - 1)]);
  }

  nav.querySelectorAll('[data-jump]').forEach(function (button) {
    button.addEventListener('click', function () {
      var entry = entries.filter(function (item) { return item.button === button; })[0];
      if (entry) setActive(entry);
    });
  });

  if (prev) prev.addEventListener('click', function () { move(-1); });
  if (next) next.addEventListener('click', function () { move(1); });

  main.dataset.scrollSpyReady = '1';
  refreshEntries();
  main.addEventListener('scroll', schedule, {passive: true});
  global.addEventListener('resize', function () { refreshEntries(); schedule(); }, {passive: true});
  global.setTimeout(function () { refreshEntries(); update(); }, 0);
  global.setTimeout(function () { refreshEntries(); update(); }, 400);

  global.NoesisDashboardNavigation = Object.freeze({
    refresh: function () { refreshEntries(); update(); },
    next: function () { move(1); },
    previous: function () { move(-1); }
  });
})(window);
