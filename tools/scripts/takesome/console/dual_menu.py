from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TypeVar

from .ansi import color_enabled, paint, strip_ansi
from .frame import (
    HIDE_CURSOR,
    SHOW_CURSOR,
    box_lines,
    clear_full_frame,
    clear_previous,
    render_focus_header,
    replace_frame,
    style_selected,
    terminal_height,
    terminal_render_width,
    terminal_width,
)
from .input import move_cursor, read_key
from .rows import ConsoleActionMenuResult, ConsoleChoice, choice_marker, choice_marker_width
from .tags import colorize_script_line
from .theme import density, theme

T = TypeVar("T")


def run_dual_action_menu(
    *,
    title: str,
    primary_title: str,
    primary_choices: list[ConsoleChoice[T]],
    secondary_title: str,
    secondary_choices: list[ConsoleChoice[T]],
    footer: str = "Tab switch block  ↑/↓ move  Enter open/run  Backspace back  Esc quit",
    header_lines: Callable[[], list[str]] | None = None,
) -> ConsoleActionMenuResult[T]:
    """Render a two-zone action menu.

    The renderer is resize-safe: every frame recomputes terminal width/height,
    splits the available height between both zones, and clips each boxed table
    with explicit above/below indicators instead of letting long rows wrap and
    corrupt the border layout.
    """

    if not primary_choices and not secondary_choices:
        return ConsoleActionMenuResult(None, cancelled=True)

    focus_zone = "primary"
    if not primary_choices and secondary_choices:
        focus_zone = "secondary"
    primary_cursor = 0
    secondary_cursor = 0
    primary_offset = 0
    secondary_offset = 0
    rendered_lines = 0
    last_size = (terminal_width(), terminal_height())

    def focused_choices() -> list[ConsoleChoice[T]]:
        return secondary_choices if focus_zone == "secondary" else primary_choices

    def focused_cursor() -> int:
        return secondary_cursor if focus_zone == "secondary" else primary_cursor

    def set_focused_cursor(value: int) -> None:
        nonlocal primary_cursor, secondary_cursor
        if focus_zone == "secondary":
            secondary_cursor = value
        else:
            primary_cursor = value

    def max_rows_for_sections() -> tuple[int, int]:
        # Fixed lines: title, footer, two section headers, two box border pairs.
        available = max(2, terminal_height() - density().dual_reserved_lines)
        if not secondary_choices:
            return max(1, available), 0
        if not primary_choices:
            return 0, max(1, available)
        primary_share = max(1, (available * 2) // 3)
        secondary_share = max(1, available - primary_share)
        return primary_share, secondary_share

    def render_section(
        section_title: str,
        choices: list[ConsoleChoice[T]],
        *,
        focused: bool,
        cursor: int,
        offset: int,
        max_rows: int,
    ) -> tuple[list[str], int]:
        rows: list[str] = []
        marker_width = choice_marker_width(choices)
        max_rows = max(1, min(max_rows, max(1, len(choices)))) if choices else 1
        if not choices:
            rows.append(paint("no entries yet", theme().text_muted))
            return [render_focus_header(section_title, focused=focused), *box_lines("actions", rows, width=terminal_render_width())], 0

        if cursor < offset:
            offset = cursor
        if cursor >= offset + max_rows:
            offset = cursor - max_rows + 1
        offset = max(0, min(offset, max(0, len(choices) - max_rows)))

        if offset > 0:
            rows.append(paint(f"↑ {offset} item(s) above", theme().text_muted))
        for row_index, choice in enumerate(choices[offset : offset + max_rows], start=offset):
            num = f"{choice.number})" if choice.number is not None else "  "
            marker = choice_marker(choice, width=marker_width)
            plain_detail = strip_ansi(choice.detail)
            selected_suffix = f"  {plain_detail}" if plain_detail else ""
            suffix = f"  {choice.detail}" if choice.detail else ""
            plain = f"  {num:>4} {strip_ansi(marker)}{choice.label}{selected_suffix}"
            if focused and row_index == cursor:
                rows.append(style_selected(plain) if color_enabled() else ">" + plain[1:])
            else:
                label = paint(choice.label, theme().text_primary)
                rows.append(f"  {num:>4} {marker}{label}{suffix}")
        hidden_below = max(0, len(choices) - (offset + max_rows))
        if hidden_below:
            rows.append(paint(f"↓ {hidden_below} item(s) below", theme().text_muted))
        return [render_focus_header(section_title, focused=focused), *box_lines("actions", rows, width=terminal_render_width())], offset

    def render_lines() -> list[str]:
        nonlocal primary_offset, secondary_offset, primary_cursor, secondary_cursor
        if primary_choices:
            primary_cursor = max(0, min(primary_cursor, len(primary_choices) - 1))
        if secondary_choices:
            secondary_cursor = max(0, min(secondary_cursor, len(secondary_choices) - 1))
        primary_rows, secondary_rows = max_rows_for_sections()
        lines: list[str] = list(header_lines() or []) if header_lines is not None else []
        lines.append(colorize_script_line(f"[MENU] {title}"))
        lines.append(colorize_script_line(f"[MENU] {footer}"))
        rendered, primary_offset = render_section(
            primary_title,
            primary_choices,
            focused=focus_zone == "primary",
            cursor=primary_cursor,
            offset=primary_offset,
            max_rows=primary_rows,
        )
        lines.extend(rendered)
        if secondary_choices:
            rendered, secondary_offset = render_section(
                secondary_title,
                secondary_choices,
                focused=focus_zone == "secondary",
                cursor=secondary_cursor,
                offset=secondary_offset,
                max_rows=secondary_rows,
            )
            lines.extend(rendered)
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
            choices = focused_choices()
            cursor = focused_cursor()
            primary_rows, secondary_rows = max_rows_for_sections()
            page = secondary_rows if focus_zone == "secondary" else primary_rows
            if key == "tab":
                if focus_zone == "primary" and secondary_choices:
                    focus_zone = "secondary"
                else:
                    focus_zone = "primary" if primary_choices else "secondary"
            elif key == "up":
                set_focused_cursor(move_cursor(cursor, -1, len(choices)))
            elif key == "down":
                set_focused_cursor(move_cursor(cursor, 1, len(choices)))
            elif key == "home":
                set_focused_cursor(0)
            elif key == "end":
                set_focused_cursor(max(0, len(choices) - 1))
            elif key == "page_up":
                set_focused_cursor(move_cursor(cursor, -max(1, page), len(choices)))
            elif key == "page_down":
                set_focused_cursor(move_cursor(cursor, max(1, page), len(choices)))
            elif key == "enter":
                if choices:
                    selected_value = choices[focused_cursor()].value
                    if header_lines is not None:
                        clear_full_frame()
                    else:
                        clear_previous(rendered_lines)
                    return ConsoleActionMenuResult(selected_value, cancelled=False)
            elif key.isdigit():
                number = int(key)
                matched = False
                for zone, pool in (("primary", primary_choices), ("secondary", secondary_choices)):
                    for index, choice in enumerate(pool):
                        if choice.number == number:
                            focus_zone = zone
                            set_focused_cursor(index)
                            matched = True
                            break
                    if matched:
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
