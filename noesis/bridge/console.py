from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
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

_BLOCK_FIELDS = {"args", "result", "error_details", "stderr", "stdout", "content", "payload"}
_INLINE_MAX = 96
_BLOCK_WRAP = 160
_LOG_TEXT_PREVIEW = 180
_LOG_LIST_LIMIT = 16
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


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
    text = _strip_ansi(text)
    return text.replace("\r", "\\r").replace("\n", "\\n")


def emit(level: str, message: str, **fields: Any) -> None:
    now = dt.datetime.now().strftime("%H:%M:%S")
    level_u = level.upper().strip() or "INFO"
    level_color = LEVEL_COLORS.get(level_u, "white")
    level_label = level_u[:6].ljust(6)
    msg_color = level_color if level_u in {"ERROR", "WARN", "SLOW"} else "white"

    inline_fields: list[tuple[str, Any]] = []
    block_fields: list[tuple[str, Any]] = []
    for key, value in _ordered_fields(fields):
        if value is None:
            continue
        if _should_block(key, value):
            block_fields.append((key, value))
        else:
            inline_fields.append((key, value))

    pieces = [
        color("[", "gray") + color(now, "dim") + color("]", "gray"),
        color("[", "gray") + color(level_label, level_color) + color("]", "gray"),
        color(str(message), msg_color),
    ]
    for key, value in inline_fields:
        value_color = KEY_COLORS.get(key, "white")
        pieces.append(color(str(key), "gray") + color("=", "dim") + color(_field_value(key, value), value_color))

    with _EMIT_LOCK:
        print(" ".join(pieces), file=sys.stderr, flush=True)
        for index, (key, value) in enumerate(block_fields):
            is_last = index == len(block_fields) - 1
            _emit_block(key, value, is_last=is_last)


def _should_block(key: str, value: Any) -> bool:
    if key in _BLOCK_FIELDS:
        return True
    if isinstance(value, (dict, list, tuple)):
        return True
    text = str(value)
    return "\n" in text or "\r" in text or len(text) > _INLINE_MAX


def _emit_block(key: str, value: Any, *, is_last: bool) -> None:
    key_color = KEY_COLORS.get(key, "white")
    branch = "└─" if is_last else "├─"
    pipe = "  " if is_last else "│ "
    header = color("  " + branch, "gray") + " " + color(str(key), key_color)
    content_prefix = "  " + pipe + "  "
    print(header, file=sys.stderr, flush=True)
    for line in _format_block_value(key, value).splitlines() or ["<empty>"]:
        print(color(content_prefix, "gray") + line, file=sys.stderr, flush=True)


def _format_block_value(key: str, value: Any) -> str:
    value = _compact_log_value(value, field=key)
    if isinstance(value, str):
        raw = _strip_ansi(value).strip()
        parsed = _parse_json(raw)
        if parsed is not None:
            return _render_json_value(_compact_log_value(parsed, field=key))
        return _wrap_long_lines(raw, width=_BLOCK_WRAP)
    try:
        return _render_json_value(value)
    except Exception:
        return _wrap_long_lines(_strip_ansi(str(value)), width=_BLOCK_WRAP)


def _compact_log_value(value: Any, *, field: str = "") -> Any:
    if os.environ.get("NORTHSTAR_BRIDGE_LOG_FULL_FIELDS", "").strip().lower() in {"1", "true", "yes", "on", "force"}:
        return value
    if isinstance(value, str):
        return _compact_string(value)
    if isinstance(value, dict):
        return {str(key): _compact_log_value(item, field=str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        items = list(value)
        compact = [_compact_log_value(item, field=field) for item in items[:_LOG_LIST_LIMIT]]
        if len(items) > _LOG_LIST_LIMIT:
            compact.append({"truncated_items": len(items) - _LOG_LIST_LIMIT})
        return compact
    return value


def _compact_string(value: str) -> Any:
    clean = _strip_ansi(value)
    line_count = clean.count("\n") + 1 if clean else 0
    if len(clean) <= _LOG_TEXT_PREVIEW and line_count <= 3:
        return clean
    digest = hashlib.sha256(clean.encode("utf-8", errors="replace")).hexdigest()[:8]
    preview = clean.replace("\r", "").replace("\n", "\n")[:_LOG_TEXT_PREVIEW]
    if len(clean) > _LOG_TEXT_PREVIEW:
        preview += "…"
    return {
        "type": "text_preview",
        "chars": len(clean),
        "lines": line_count,
        "sha8": digest,
        "preview": preview,
    }


def _render_json_value(value: Any, *, depth: int = 0) -> str:
    return "\n".join(_render_json_lines(value, depth=depth))


def _render_json_lines(value: Any, *, depth: int) -> list[str]:
    indent = "  " * depth
    next_indent = "  " * (depth + 1)
    if isinstance(value, dict):
        if not value:
            return [color("{}", "gray")]
        lines = [color("{", "gray")]
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            comma = color(",", "dim") if index < len(items) - 1 else ""
            rendered = _render_json_lines(item, depth=depth + 1)
            key_text = color(json.dumps(str(key), ensure_ascii=False), "cyan") + color(":", "dim") + " "
            if len(rendered) == 1:
                lines.append(next_indent + key_text + rendered[0] + comma)
            else:
                lines.append(next_indent + key_text + rendered[0])
                lines.extend(rendered[1:-1])
                lines.append(rendered[-1] + comma)
        lines.append(indent + color("}", "gray"))
        return lines
    if isinstance(value, (list, tuple)):
        if not value:
            return [color("[]", "gray")]
        lines = [color("[", "gray")]
        items = list(value)
        for index, item in enumerate(items):
            comma = color(",", "dim") if index < len(items) - 1 else ""
            rendered = _render_json_lines(item, depth=depth + 1)
            if len(rendered) == 1:
                lines.append(next_indent + rendered[0] + comma)
            else:
                lines.append(next_indent + rendered[0])
                lines.extend(rendered[1:-1])
                lines.append(rendered[-1] + comma)
        lines.append(indent + color("]", "gray"))
        return lines
    return [color(_json_scalar(value), _json_scalar_color(value))]


def _json_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _json_scalar_color(value: Any) -> str:
    if value is None:
        return "gray"
    if isinstance(value, bool):
        return "magenta"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "yellow"
    return "green"


def _parse_json(text: str) -> Any | None:
    if not text or text[0] not in "[{\"":
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _wrap_long_lines(text: str, *, width: int) -> str:
    out: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if len(line) <= width:
            out.append(line)
            continue
        current = line
        while len(current) > width:
            out.append(current[:width] + " ↩")
            current = "    " + current[width:]
        out.append(current)
    return "\n".join(out)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)
