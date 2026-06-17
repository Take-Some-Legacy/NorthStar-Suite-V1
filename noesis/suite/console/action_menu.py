from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TypeVar

from .ansi import ANSI_BOLD, color_enabled, paint, strip_ansi
from .frame import (
    HIDE_CURSOR,
    SHOW_CURSOR,
    box_lines,
    clear_full_frame,
    clear_previous,
    render_focus_header,
    fit_row,
    replace_frame,
    style_action,
    style_selected,
    terminal_height,
    terminal_render_width,
    terminal_width,
)
from .input import move_cursor, read_key
from .rows import (
    ConsoleActionMenuResult,
    ConsoleChoice,
    ConsoleConfirmResult,
    ConsoleMenuOption,
    choice_marker,
    choice_marker_width,
)
from .tags import colorize_script_line
from .theme import density, theme

T = TypeVar("T")

def render_menu_options(
    options: list[ConsoleMenuOption],
    *,
    active_index: int = 0,
    focused: bool = False,
) -> list[str]:
    if not options:
        return []
    lines = [render_focus_header("[OPTIONS]", focused=focused)]
    for index, option in enumerate(options):
        current = theme()
        label = paint(option.label, current.text_heading) if color_enabled() else option.label
        detail = f"  {paint(option.detail, current.text_muted) if color_enabled() else option.detail}" if option.detail else ""
        row = f"  • {label}{detail}"
        if focused and index == active_index:
            plain = f"  • {option.label}{('  ' + strip_ansi(option.detail)) if option.detail else ''}"
            lines.append(style_selected(plain) if color_enabled() else ">" + plain[1:])
        else:
            lines.append(row)
    return lines

def run_confirm_button(
    *,
    title: str,
    body_lines: list[str],
    confirm_label: str = "CONFIRM",
    footer: str = "Tab option/button  Enter apply  Esc cancel",
) -> ConsoleConfirmResult:
    """Render a focused confirmation surface with one large central button."""

    rendered_lines = 0
    focus_zone = "button"
    cancel_option = ConsoleMenuOption("cancel", "", "Cancel", "return without running")

    def render_lines() -> list[str]:
        lines: list[str] = []
        lines.append(colorize_script_line(f"[MENU] {title}"))
        lines.append(colorize_script_line(f"[MENU] {footer}"))
        lines.extend(render_menu_options([cancel_option], active_index=0, focused=focus_zone == "options"))
        lines.append(render_focus_header("[SUMMARY]", focused=False))
        width = terminal_width()
        lines.extend(box_lines("review", body_lines or ["no details"], width=width))
        available = max(46, width - 4)
        label = f"  {confirm_label}  "
        centered = label.center(min(available, max(len(strip_ansi(label)) + 18, 58)))
        lines.append(style_action(centered, selected=focus_zone == "button"))
        return lines

    try:
        if color_enabled():
            sys.stdout.write(HIDE_CURSOR)
            sys.stdout.flush()
        while True:
            rendered_lines = replace_frame(rendered_lines, render_lines())
            key = read_key()
            if key == "tab":
                focus_zone = "options" if focus_zone == "button" else "button"
            elif key == "enter":
                clear_previous(rendered_lines)
                if focus_zone == "options":
                    return ConsoleConfirmResult(False, cancelled=True)
                return ConsoleConfirmResult(True, cancelled=False)
            elif key in {"escape", "backspace"}:
                clear_previous(rendered_lines)
                return ConsoleConfirmResult(False, cancelled=True)
    finally:
        if color_enabled():
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()

def run_action_menu(
    *,
    title: str,
    choices: list[ConsoleChoice[T]],
    footer: str = "↑/↓ move  Enter open  Esc quit",
    row_status_provider: Callable[[ConsoleChoice[T]], str] | None = None,
    header_lines: Callable[[], list[str]] | None = None,
) -> ConsoleActionMenuResult[T]:
    """Render a single-action menu.

    This is for command surfaces such as devTools: rows are actions, not a
    batch selection. There are no checkboxes and no bottom action button; Enter
    executes the currently highlighted row. Numeric keys only move the cursor to
    the matching visible action, so execution is always explicit through Enter.
    """

    if not choices:
        return ConsoleActionMenuResult(None, cancelled=True)

    cursor = 0
    rendered_lines = 0
    last_size = (terminal_width(), terminal_height())
    offset = 0
    status_cache: dict[int, str] = {}
    marker_width = choice_marker_width(choices)

    def detail_for(row_index: int, choice: ConsoleChoice[T]) -> str:
        if row_status_provider is None:
            return choice.detail
        if row_index not in status_cache:
            status_cache[row_index] = row_status_provider(choice)
        return status_cache[row_index]

    def max_visible_rows() -> int:
        return max(1, min(len(choices), terminal_height() - density().action_reserved_lines))

    def render_lines() -> list[str]:
        nonlocal offset
        max_rows = max_visible_rows()
        if cursor < offset:
            offset = cursor
        if cursor >= offset + max_rows:
            offset = cursor - max_rows + 1
        offset = max(0, min(offset, max(0, len(choices) - max_rows)))

        visible_choices = choices[offset : offset + max_rows]
        lines: list[str] = list(header_lines() or []) if header_lines is not None else []
        lines.append(colorize_script_line(f"[MENU] {title}"))
        lines.append(colorize_script_line(f"[MENU] {footer}"))
        if offset > 0:
            lines.append(paint(f"      ↑ {offset} action(s) above", theme().text_muted))
        for row_index, choice in enumerate(visible_choices, start=offset):
            num = f"{choice.number})" if choice.number is not None else "  "
            marker = choice_marker(choice, width=marker_width)
            detail = detail_for(row_index, choice)
            plain_detail = strip_ansi(detail)
            selected_suffix = f"  {plain_detail}" if plain_detail else ""
            suffix = f"  {detail}" if detail else ""
            plain = f"  {num:>4} {strip_ansi(marker)}{choice.label}{selected_suffix}"
            if row_index == cursor:
                if color_enabled():
                    lines.append(style_selected(fit_row(plain)))
                else:
                    lines.append(">" + fit_row(plain)[1:])
            else:
                label = paint(choice.label, theme().text_primary)
                lines.append(fit_row(f"  {num:>4} {marker}{label}{suffix}"))
        hidden_below = max(0, len(choices) - (offset + max_rows))
        if hidden_below:
            lines.append(paint(f"      ↓ {hidden_below} action(s) below", theme().text_muted))
        return lines

    def render_current() -> None:
        nonlocal rendered_lines, last_size
        rendered_lines = replace_frame(rendered_lines, render_lines(), full_screen=header_lines is not None)
        last_size = (terminal_width(), terminal_height())

    def repaint_if_resized() -> None:
        if (terminal_width(), terminal_height()) != last_size:
            render_current()

    try:
        if color_enabled():
            sys.stdout.write(HIDE_CURSOR)
            sys.stdout.flush()
        while True:
            render_current()
            key = read_key(on_idle=repaint_if_resized)
            low_key = key.lower() if len(key) == 1 else key
            if key == "up":
                cursor = move_cursor(cursor, -1, len(choices))
            elif key == "down":
                cursor = move_cursor(cursor, 1, len(choices))
            elif key == "home":
                cursor = 0
            elif key == "end":
                cursor = len(choices) - 1
            elif key == "page_up":
                cursor = move_cursor(cursor, -max_visible_rows(), len(choices))
            elif key == "page_down":
                cursor = move_cursor(cursor, max_visible_rows(), len(choices))
            elif key == "enter":
                selected_value = choices[cursor].value
                if header_lines is not None:
                    clear_full_frame()
                else:
                    clear_previous(rendered_lines)
                return ConsoleActionMenuResult(selected_value, cancelled=False)
            elif key.isdigit():
                number = int(key)
                for index, choice in enumerate(choices):
                    if choice.number == number:
                        cursor = index
                        break
            elif key in {"escape", "backspace"} or low_key == "q":
                if header_lines is not None:
                    clear_full_frame()
                else:
                    clear_previous(rendered_lines)
                return ConsoleActionMenuResult(None, cancelled=True)
    finally:
        if color_enabled():
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()
