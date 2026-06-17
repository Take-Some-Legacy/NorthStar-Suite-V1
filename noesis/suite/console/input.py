from __future__ import annotations

import os
import select
import sys
import time
from collections.abc import Callable

from ..constants import WIN
from .ansi import color_enabled


def interactive_menu_enabled() -> bool:
    """Return true when a real pseudo-console menu can safely own stdin/stdout."""

    forced = os.environ.get("NEWENGINE_CONSOLE_MENU", "").strip().lower()
    if forced in {"0", "false", "no", "off", "never", "plain"}:
        return False
    if os.environ.get("CI") or os.environ.get("NEWENGINE_PARENT_SCRIPT"):
        return False
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    return color_enabled()


def _translate_windows_key(ch: str) -> str:
    import msvcrt

    if ch in ("\x00", "\xe0"):
        code = msvcrt.getwch()
        return {
            "H": "up",
            "P": "down",
            "K": "left",
            "M": "right",
            "G": "home",
            "O": "end",
            "I": "page_up",
            "Q": "page_down",
        }.get(code, "")
    if ch in ("\r", "\n"):
        return "enter"
    if ch == " ":
        return "space"
    if ch == "\t":
        return "tab"
    if ch in ("\b", "\x7f"):
        return "backspace"
    if ch == "\x1b":
        return "escape"
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch


def _translate_posix_key(first: str) -> str:
    if first == "\x03":
        raise KeyboardInterrupt
    if first in ("\r", "\n"):
        return "enter"
    if first == " ":
        return "space"
    if first == "\t":
        return "tab"
    if first in ("\b", "\x7f"):
        return "backspace"
    if first == "\x1b":
        ready, _, _ = select.select([sys.stdin], [], [], 0.04)
        if not ready:
            return "escape"
        seq = sys.stdin.read(2)
        if seq == "[A":
            return "up"
        if seq == "[B":
            return "down"
        if seq == "[C":
            return "right"
        if seq == "[D":
            return "left"
        if seq == "[H":
            return "home"
        if seq == "[F":
            return "end"
        if seq == "[5":
            sys.stdin.read(1)
            return "page_up"
        if seq == "[6":
            sys.stdin.read(1)
            return "page_down"
        return "escape"
    return first


def read_key(on_idle: Callable[[], None] | None = None, *, idle_interval: float = 0.08) -> str:
    """Read one console key while allowing resize-aware redraw hooks.

    `msvcrt.getwch()` and raw POSIX reads block forever, so a terminal resize
    could leave the previous frame reflowed until the next key press.  The
    optional idle hook lets menus repaint when width/height changes while the
    user is not pressing anything.
    """

    if WIN:
        import msvcrt

        while True:
            if msvcrt.kbhit():
                return _translate_windows_key(msvcrt.getwch())
            if on_idle is not None:
                on_idle()
            time.sleep(max(0.02, idle_interval))

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], max(0.02, idle_interval))
            if ready:
                return _translate_posix_key(sys.stdin.read(1))
            if on_idle is not None:
                on_idle()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def move_cursor(cursor: int, delta: int, row_count: int) -> int:
    if row_count <= 0:
        return 0
    return max(0, min(row_count - 1, cursor + delta))


def toggle_choice(index: int, selected: set[int]) -> None:
    if index in selected:
        selected.remove(index)
    else:
        selected.add(index)
