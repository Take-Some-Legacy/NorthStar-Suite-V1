from __future__ import annotations

import datetime as dt
import os
import sys
import threading
from typing import Any

_EMIT_LOCK = threading.Lock()

ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
}

LEVEL_COLORS = {
    "OK": "green",
    "INFO": "cyan",
    "STATE": "blue",
    "HTTP": "blue",
    "HEALTH": "green",
    "TOOL": "magenta",
    "WARN": "yellow",
    "SLOW": "yellow",
    "ERROR": "red",
}

FIELD_ORDER = (
    "id",
    "request_id",
    "method",
    "path",
    "route",
    "status",
    "response_status",
    "elapsed_ms",
    "bytes",
    "raw_bytes",
    "rpc_method",
    "rpc_id",
    "rpc_batch",
    "tool",
    "tool_count",
    "endpoint",
    "url",
    "host",
    "port",
    "tools",
    "write",
    "error",
    "error_details",
    "result",
    "args",
)

KEY_COLORS = {
    "id": "magenta",
    "request_id": "magenta",
    "method": "cyan",
    "path": "cyan",
    "route": "blue",
    "status": "green",
    "response_status": "green",
    "elapsed_ms": "yellow",
    "bytes": "yellow",
    "raw_bytes": "yellow",
    "rpc_method": "magenta",
    "rpc_id": "magenta",
    "tool": "magenta",
    "endpoint": "cyan",
    "url": "cyan",
    "error": "red",
    "error_details": "red",
    "result": "white",
    "args": "white",
}


def _enable_windows_ansi() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        flag = 0x0004
        ok = False
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | flag)
                ok = True
        return ok
    except Exception:
        return False


_ANSI_READY = _enable_windows_ansi()


def color(text: Any, name: str) -> str:
    value = str(text)
    if os.environ.get("NO_COLOR") or not _ANSI_READY:
        return value
    return f"{ANSI.get(name, '')}{value}{ANSI['reset']}"


def _ordered_fields(fields: dict[str, Any]) -> list[tuple[str, Any]]:
    seen: set[str] = set()
    ordered: list[tuple[str, Any]] = []
    for key in FIELD_ORDER:
        if key in fields:
            ordered.append((key, fields[key]))
            seen.add(key)
    for key in sorted(k for k in fields.keys() if k not in seen):
        ordered.append((key, fields[key]))
    return ordered


def _field_value(key: str, value: Any) -> str:
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, float):
        text = f"{value:.3f}"
    else:
        text = str(value)
    return text.replace("\r", "\\r").replace("\n", "\\n")


def emit(level: str, message: str, **fields: Any) -> None:
    now = dt.datetime.now().strftime("%H:%M:%S")
    level_u = level.upper().strip() or "INFO"
    level_color = LEVEL_COLORS.get(level_u, "white")
    level_label = level_u[:6].ljust(6)
    msg_color = level_color if level_u in {"ERROR", "WARN", "SLOW"} else "white"
    pieces = [
        color("[", "gray") + color(now, "dim") + color("]", "gray"),
        color("[", "gray") + color(level_label, level_color) + color("]", "gray"),
        color(str(message), msg_color),
    ]
    for key, value in _ordered_fields(fields):
        if value is None:
            continue
        value_color = KEY_COLORS.get(key, "white")
        pieces.append(color(str(key), "gray") + color("=", "dim") + color(_field_value(key, value), value_color))
    with _EMIT_LOCK:
        print(" ".join(pieces), file=sys.stderr, flush=True)


def tool_ok(payload: Any) -> bool:
    if isinstance(payload, dict):
        return bool(payload.get("ok", True)) and not payload.get("error")
    return True
