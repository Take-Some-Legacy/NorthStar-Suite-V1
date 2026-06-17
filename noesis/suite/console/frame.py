from __future__ import annotations

import shutil
import sys

from .ansi import (
    ANSI_BOLD,
    ANSI_RESET,
    color_enabled,
    paint,
    strip_ansi,
)
from .tags import colorize_script_line
from .theme import density, theme

HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR_LINE = "\033[2K"
CURSOR_HOME = "\033[H"
CLEAR_SCREEN = "\033[2J"
CLEAR_TO_END = "\033[J"


def style_selected(text: str) -> str:
    if not color_enabled():
        return text
    current = theme()
    return f"{current.selected_bg}{current.selected_fg}{text}{ANSI_RESET}"


def style_action(text: str, *, selected: bool) -> str:
    if not color_enabled():
        return f"> {text}" if selected else f"  {text}"
    current = theme()
    if selected:
        return f"{current.action_bg}{current.action_fg}{ANSI_BOLD} {text} {ANSI_RESET}"
    return paint(f" {text} ", current.status_ok + ANSI_BOLD)


MIN_TERMINAL_WIDTH = 44
MIN_TERMINAL_HEIGHT = 10


def terminal_width(default: int = 110, *, min_width: int = MIN_TERMINAL_WIDTH) -> int:
    try:
        return max(min_width, shutil.get_terminal_size((default, 28)).columns)
    except OSError:
        return max(min_width, default)


def terminal_render_width(default: int = 110, *, min_width: int = 32) -> int:
    # Keep one spare column. On Windows terminals, writing to the last column can
    # set auto-wrap and corrupt border layouts after a resize. Unlike
    # terminal_width(), this uses the real current width because render lines
    # must never exceed the resized console even if it is narrower than our
    # preferred UX minimum.
    try:
        columns = shutil.get_terminal_size((default, 28)).columns
    except OSError:
        columns = default
    return max(min_width, columns - 1)


def terminal_height(default: int = 28, *, min_height: int = MIN_TERMINAL_HEIGHT) -> int:
    try:
        return max(min_height, shutil.get_terminal_size((100, default)).lines)
    except OSError:
        return max(min_height, default)


def frame_line_limit(reserved: int = 3) -> int:
    return max(5, terminal_height() - max(1, reserved))


def clip_frame_lines(lines: list[str]) -> list[str]:
    limit = frame_line_limit()
    if len(lines) <= limit:
        return lines
    warning = colorize_script_line("[WARN] Terminal is too small; list is clipped. Resize the window or use ↑/↓/Tab.")
    if limit <= 1:
        return [warning]
    return lines[: limit - 1] + [warning]


def clear_previous(rendered_lines: int) -> None:
    rendered_lines = min(max(0, rendered_lines), frame_line_limit())
    if rendered_lines <= 0:
        return
    sys.stdout.write(f"\033[{rendered_lines}F")
    sys.stdout.flush()
    for _ in range(rendered_lines):
        sys.stdout.write(CLEAR_LINE + "\n")
    sys.stdout.write(f"\033[{rendered_lines}F")
    sys.stdout.flush()


def clear_full_frame() -> None:
    sys.stdout.write(CLEAR_SCREEN + CURSOR_HOME)
    sys.stdout.flush()


def _normalize_frame_lines(lines: list[str], *, reserve_last_line: bool = True) -> list[str]:
    width = terminal_render_width()
    height = terminal_height()
    limit = max(1, height - (1 if reserve_last_line else 0))
    normalized = [fit_visible(line, width) for line in lines[:limit]]
    if len(lines) > limit and normalized:
        normalized[-1] = fit_visible(colorize_script_line("[WARN] Terminal is too small; resize to see all rows."), width)
    return normalized


def replace_frame(previous_lines: int, lines: list[str], *, full_screen: bool = False) -> int:
    if full_screen:
        lines = _normalize_frame_lines(lines)
        sys.stdout.write(CURSOR_HOME + CLEAR_TO_END)
        # Do not append a final newline. Ending on the last visible column/row can
        # force terminal scroll and leave old bordered frames behind after resize.
        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()
        return len(lines)

    lines = clip_frame_lines(_normalize_frame_lines(lines, reserve_last_line=True))
    previous_lines = min(max(0, previous_lines), frame_line_limit())
    if previous_lines > 0:
        sys.stdout.write(f"\033[{previous_lines}F")
    visible_count = max(previous_lines, len(lines))
    out: list[str] = []
    for index in range(visible_count):
        out.append(CLEAR_LINE)
        if index < len(lines):
            out.append(lines[index])
        out.append("\n")
    sys.stdout.write("".join(out))
    sys.stdout.flush()
    return visible_count


def fit_visible(text: str, width: int) -> str:
    width = max(0, int(width or 0))
    plain = strip_ansi(text)
    if width <= 0:
        return ""
    if len(plain) <= width:
        return text + (" " * (width - len(plain)))
    if width == 1:
        return "…"
    return plain[: max(0, width - 1)] + "…"


def ellipsize_middle(text: str, width: int) -> str:
    width = max(0, int(width or 0))
    plain = strip_ansi(text)
    if width <= 0:
        return ""
    if len(plain) <= width:
        return text
    if width <= 3:
        return "…"[:width]
    left = max(1, (width - 1) // 2)
    right = max(1, width - 1 - left)
    return plain[:left] + "…" + plain[-right:]


def fit_row(text: str, *, padding: int = 1) -> str:
    return fit_visible(text, max(1, terminal_render_width() - max(0, padding)))


def render_section_header(label: str) -> str:
    if color_enabled():
        return paint(label, theme().status_info + ANSI_BOLD)
    return label


def render_focus_header(label: str, *, focused: bool) -> str:
    suffix = "  <FOCUS>" if focused else ""
    if focused and color_enabled():
        return paint(label + suffix, theme().status_info + ANSI_BOLD)
    return render_section_header(label + suffix)


def box_lines(title: str, rows: list[str], *, width: int) -> list[str]:
    # Always derive the real box width from the current terminal width.  This
    # keeps old callers that pass cached widths safe after a terminal resize.
    outer_width = min(max(24, int(width or 0)), terminal_render_width())
    inner_width = max(8, outer_width - 4)
    title_text = f" {title} " if title else ""
    if len(strip_ansi(title_text)) >= inner_width:
        title_text = ""
    current = theme()
    visible_title = paint(title_text, current.border_primary) if title_text and color_enabled() else title_text
    top = "┌" + visible_title + ("─" * max(0, inner_width - len(strip_ansi(title_text)))) + "┐"
    bottom = "└" + ("─" * inner_width) + "┘"
    if color_enabled():
        top = (
            paint("┌", current.border_muted)
            + visible_title
            + paint("─" * max(0, inner_width - len(strip_ansi(title_text))), current.border_muted)
            + paint("┐", current.border_muted)
        )
        bottom = paint(bottom, current.border_muted)
    result = [top]
    safe_rows = rows or [paint("no entries", current.text_muted) if color_enabled() else "no entries"]
    for row in safe_rows:
        if color_enabled():
            result.append(paint("│ ", current.border_muted) + fit_visible(row, inner_width - 2) + paint(" │", current.border_muted))
        else:
            result.append("│ " + fit_visible(row, inner_width - 2) + " │")
    result.append(bottom)
    return result
