from __future__ import annotations

import os
import re
from typing import Any

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
    "white": "\033[37m",
    "bright_white": "\033[97m",
}
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
LOG_LEVEL_COLORS = {
    "OK": "green",
    "INFO": "cyan",
    "WARN": "yellow",
    "ERROR": "red",
    "ERR": "red",
    "STATE": "blue",
    "HEALTH": "green",
    "HTTP": "cyan",
    "SLOW": "yellow",
}


def enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        flag = 0x0004
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | flag)
    except Exception:
        pass


def ansi_allowed() -> bool:
    return not bool(os.environ.get("NO_COLOR"))


def color(text: object, name: str) -> str:
    if not ansi_allowed():
        return str(text)
    return f"{ANSI.get(name, '')}{text}{ANSI['reset']}"


def style(text: object, *names: str) -> str:
    if not ansi_allowed():
        return str(text)
    prefix = "".join(ANSI.get(name, "") for name in names)
    return f"{prefix}{text}{ANSI['reset']}"


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


def truncate_ansi(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if visible_len(text) <= width:
        return text
    if width <= 1:
        return "…"[:width]
    out: list[str] = []
    visible = 0
    i = 0
    limit = width - 1
    while i < len(text) and visible < limit:
        match = ANSI_RE.match(text, i)
        if match:
            out.append(match.group(0))
            i = match.end()
            continue
        out.append(text[i])
        visible += 1
        i += 1
    out.append("…")
    if ansi_allowed():
        out.append(ANSI["reset"])
    return "".join(out)


def fit_ansi(text: str, width: int) -> str:
    fitted = truncate_ansi(text, width)
    return fitted + " " * max(0, width - visible_len(fitted))


def bracket(text: object, inner_color: str = "white", *, strong: bool = False) -> str:
    inner = style(text, inner_color, "bold") if strong else color(text, inner_color)
    return color("[", "gray") + inner + color("]", "gray")


def level_color(level: str) -> str:
    return LOG_LEVEL_COLORS.get(level.upper().strip(), "white")
