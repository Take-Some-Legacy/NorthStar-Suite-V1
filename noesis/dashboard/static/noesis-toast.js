// NOESIS toast bridge: Notyf first, local fallback second.
(function (global) {
  'use strict';

  var noesisNotyf = null;

  function cleanToastText(value) {
    return String(value == null ? '' : value).replace(/[<>]/g, '');
  }

  function notyfInstance() {
    if (noesisNotyf || !global.Notyf) return noesisNotyf;
    try {
      noesisNotyf = new global.Notyf({
        duration: 3200,
        dismissible: true,
        ripple: false,
        position: {x: 'right', y: 'top'},
        types: [
          {type: 'info', className: 'noesis-toast-info', icon: false},
          {type: 'warning', className: 'noesis-toast-warning', icon: false}
        ]
      });
    } catch (_) {
      noesisNotyf = null;
    }
    return noesisNotyf;
  }

  function fallbackToast(type, message) {
    var stack = document.querySelector('.noesis-toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'noesis-toast-stack';
      stack.setAttribute('aria-live', 'polite');
      (document.body || document.documentElement).appendChild(stack);
    }
    var item = document.createElement('div');
    item.className = 'noesis-toast noesis-toast-' + type;
    item.textContent = message;
    stack.appendChild(item);
    global.setTimeout(function () { item.classList.add('is-visible'); }, 10);
    global.setTimeout(function () {
      item.classList.remove('is-visible');
      global.setTimeout(function () {
        if (item.parentNode) item.parentNode.removeChild(item);
      }, 220);
    }, 3600);
  }

  function notify(type, message) {
    type = type || 'info';
    var clean = cleanToastText(message || 'NOESIS event');
    var instance = notyfInstance();
    if (instance) {
      try {
        if (type === 'success' && instance.success) return instance.success(clean);
        if (type === 'error' && instance.error) return instance.error(clean);
        if (instance.open) return instance.open({type: type, message: clean});
      } catch (_) {}
    }
    fallbackToast(type, clean);
  }

  global.NoesisToast = Object.freeze({notify: notify});
})(window);
