from __future__ import annotations

import os
import re
import sys

from ..constants import WIN

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN = "\033[36m"
ANSI_BRIGHT_RED = "\033[91m"
ANSI_BRIGHT_GREEN = "\033[92m"
ANSI_BRIGHT_YELLOW = "\033[93m"
ANSI_BRIGHT_BLUE = "\033[94m"
ANSI_BRIGHT_MAGENTA = "\033[95m"
ANSI_BRIGHT_CYAN = "\033[96m"
ANSI_DARK_GRAY = "\033[90m"
ANSI_BRIGHT_WHITE = "\033[97m"
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

_COLOR_ENABLED_CACHE: bool | None = None


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _enable_windows_vt_for_stream(stream) -> bool:
    """Enable ANSI color support for a real Windows console stream."""
    if not WIN:
        return True
    try:
        import ctypes
        import msvcrt
    except Exception:
        return False
    try:
        fileno = stream.fileno()
    except Exception:
        return False
    try:
        handle = msvcrt.get_osfhandle(fileno)
    except OSError:
        return False
    kernel32 = ctypes.windll.kernel32
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    enable_virtual_terminal_processing = 0x0004
    if mode.value & enable_virtual_terminal_processing:
        return True
    new_mode = mode.value | enable_virtual_terminal_processing
    return bool(kernel32.SetConsoleMode(handle, new_mode))


def _color_mode_requested() -> str:
    forced = os.environ.get("NEWENGINE_COLOR", "").strip().lower()
    if forced in {"0", "false", "no", "off", "never", "plain"}:
        return "never"
    if forced in {"1", "true", "yes", "on", "always", "force", "ansi"}:
        return "always"
    return "auto"


def color_enabled() -> bool:
    global _COLOR_ENABLED_CACHE
    if _COLOR_ENABLED_CACHE is not None:
        return _COLOR_ENABLED_CACHE

    mode = _color_mode_requested()
    if mode == "never" or os.environ.get("NO_COLOR"):
        _COLOR_ENABLED_CACHE = False
        return _COLOR_ENABLED_CACHE
    if os.environ.get("CI") and mode != "always":
        _COLOR_ENABLED_CACHE = False
        return _COLOR_ENABLED_CACHE
    if mode == "auto" and not sys.stdout.isatty():
        _COLOR_ENABLED_CACHE = False
        return _COLOR_ENABLED_CACHE

    stdout_ok = _enable_windows_vt_for_stream(sys.stdout)
    _enable_windows_vt_for_stream(sys.stderr)
    _COLOR_ENABLED_CACHE = bool(stdout_ok or mode == "always")
    return _COLOR_ENABLED_CACHE


def paint(text: str, style: str) -> str:
    if not style or ANSI_RE.search(text):
        return text
    return f"{style}{text}{ANSI_RESET}"
