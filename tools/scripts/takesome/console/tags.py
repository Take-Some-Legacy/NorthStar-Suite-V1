from __future__ import annotations

import re

from ..progress import progress_observe_line
from .ansi import (
    ANSI_BOLD,
    ANSI_BRIGHT_BLUE,
    ANSI_BRIGHT_CYAN,
    ANSI_BRIGHT_GREEN,
    ANSI_BRIGHT_MAGENTA,
    ANSI_BRIGHT_RED,
    ANSI_BRIGHT_WHITE,
    ANSI_BRIGHT_YELLOW,
    ANSI_CYAN,
    ANSI_DARK_GRAY,
    ANSI_DIM,
    ANSI_RE,
    color_enabled,
    paint,
    strip_ansi,
)
from .theme import theme

_CARGO_COMPILING_RE = re.compile(
    r"^(?P<indent>\s*)Compiling\s+(?P<name>[^\s]+)\s+v(?P<version>[0-9][^\s]*)\s+\((?P<path>.*)\)(?P<tail>.*)$"
)


def _paint_version(version: str) -> str:
    parts = []
    for index, piece in enumerate(version.split(".")):
        if index:
            parts.append(paint(".", ANSI_DARK_GRAY))
        parts.append(paint(piece, ANSI_BRIGHT_MAGENTA))
    return "".join(parts)


def _colorize_cargo_compiling_line(line: str) -> str | None:
    newline = "\n" if line.endswith("\n") else ""
    body = line[:-1] if newline else line
    match = _CARGO_COMPILING_RE.match(body)
    if not match:
        return None
    indent = match.group("indent")
    name = match.group("name")
    version = match.group("version")
    path = match.group("path")
    tail = match.group("tail")
    current = theme()
    rendered = (
        indent
        + paint("Compiling", current.status_info + ANSI_BOLD)
        + " "
        + paint(name, current.status_ok + ANSI_BOLD)
        + " "
        + paint("v", ANSI_DARK_GRAY)
        + _paint_version(version)
        + " "
        + paint("(", ANSI_DARK_GRAY)
        + paint(path, current.text_muted)
        + paint(")", ANSI_DARK_GRAY)
        + (paint(tail, current.text_primary) if tail else "")
    )
    return rendered + newline


def normalize_tag(tag: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(tag or "").strip()).strip("-._")


def tag_style(tag: str) -> str:
    normalized = normalize_tag(tag)
    current = theme()
    if not normalized:
        return current.status_info
    explicit = current.tag_palette.get(normalized) or current.tag_palette.get(normalized.upper())
    if explicit:
        return explicit
    checksum = sum((index + 1) * ord(ch) for index, ch in enumerate(normalized.upper()))
    palette = current.tag_fallback_palette or (current.status_info,)
    return palette[checksum % len(palette)] + ANSI_BOLD


def risk_style(risk: str) -> str:
    normalized = normalize_tag(risk).lower()
    current = theme()
    return current.risk_palette.get(normalized) or current.text_muted


def render_tag(tag: str, *, width: int = 0) -> str:
    normalized = normalize_tag(tag)
    if not normalized:
        return ""
    label = normalized.upper()
    if width > 0:
        label = label.ljust(width)
    if not color_enabled():
        return f"[{label}]"
    current = theme()
    return paint("[", current.border_muted) + paint(label, tag_style(normalized)) + paint("]", current.border_muted)


def colorize_script_line(message: str) -> str:
    if not color_enabled() or not message:
        return strip_ansi(message)
    if ANSI_RE.search(message):
        return message
    match = re.match(r"^(\s*)\[([^\]\r\n]+)\](.*)$", message)
    if not match:
        return message
    prefix, status, rest = match.groups()
    current = theme()
    status_style = tag_style(status)
    return (
        prefix
        + paint("[", current.border_muted)
        + paint(status, status_style)
        + paint("]", current.border_muted)
        + (paint(rest, current.text_primary) if rest else "")
    )


def colorize_stream_line(line: str) -> str:
    if not color_enabled():
        return strip_ansi(line)
    if not line:
        return line
    if ANSI_RE.search(line):
        return line
    stripped = line.lstrip()
    lower = stripped.lower()
    current = theme()
    if stripped.startswith("error[") or lower.startswith("error:"):
        return paint(line, current.status_error + ANSI_BOLD)
    if lower.startswith("warning:") or "warning:" in lower[:80]:
        return paint(line, current.status_warn)
    if stripped.startswith("Compiling "):
        colored = _colorize_cargo_compiling_line(line)
        return colored if colored is not None else paint(line, current.status_info)
    if stripped.startswith("Finished "):
        return paint(line, current.status_ok)
    if stripped.startswith("Running "):
        return paint(line, ANSI_BRIGHT_BLUE)
    return colorize_script_line(line.rstrip("\n")) + ("\n" if line.endswith("\n") else "")


def console_emit(message: str = "") -> None:
    progress_observe_line(message)
    print(colorize_script_line(message), flush=True)
