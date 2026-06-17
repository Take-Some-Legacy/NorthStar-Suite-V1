from __future__ import annotations

import sys
from typing import Callable, TypeVar

from .ansi import (
    ANSI_BOLD,
    color_enabled,
    paint,
    strip_ansi,
)
from .frame import (
    HIDE_CURSOR,
    SHOW_CURSOR,
    box_lines,
    clear_previous,
    frame_line_limit,
    render_focus_header,
    replace_frame,
    style_action,
    style_selected,
    terminal_width,
)
from .input import move_cursor, read_key, toggle_choice
from .rows import ConsoleChoice, ConsoleMenuOption, ConsoleMultiSelectResult, choice_marker, choice_marker_width
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
        key = f"{option.key} " if option.key else ""
        current = theme()
        key_text = paint(key, current.border_muted) if color_enabled() else key
        label = paint(option.label, current.text_heading) if color_enabled() else option.label
        detail = f"  {paint(option.detail, current.text_muted) if color_enabled() else option.detail}" if option.detail else ""
        row = f"  • {key_text}{label}{detail}"
        if focused and index == active_index:
            plain = f"  • {key}{option.label}{('  ' + strip_ansi(option.detail)) if option.detail else ''}"
            lines.append(style_selected(plain) if color_enabled() else ">" + plain[1:])
        else:
            lines.append(row)
    return lines


def default_multi_select_options(*, include_skip: bool = False) -> list[ConsoleMenuOption]:
    options = [
        ConsoleMenuOption("select_all", "A", "Select all", "checks every selectable entry"),
        ConsoleMenuOption("select_none", "N", "Select none", "clears selectable entries"),
    ]
    if include_skip:
        options.append(ConsoleMenuOption("skip", "S", "Skip", "continue without selected entries"))
    options.append(ConsoleMenuOption("cancel", "Q", "Cancel", "close this command"))
    return options



def run_multi_select_menu(
    *,
    title: str,
    choices: list[ConsoleChoice[T]],
    action_label: str = "Next",
    footer: str = "Tab options/list  ↑/↓ move  Space toggle/apply  Enter next/apply  Esc cancel",
    options: list[ConsoleMenuOption] | None = None,
    default_all: bool = False,
    default_checked: bool = True,
    row_status_provider: Callable[[ConsoleChoice[T]], str] | None = None,
    # Legacy parameters are kept so older callers fail gracefully if missed.
    special_indices: dict[int, str] | None = None,
    default_special: str = "",
    exclusive_specials: set[str] | None = None,
) -> ConsoleMultiSelectResult[T]:
    """Render a boxed multi-select menu and return selected artifact values.

    Focus is split into two explicit zones:
    - OPTIONS: command actions such as All/None/Skip/Cancel, without checkboxes;
    - SELECTABLE ENTRIES: real artifacts/repositories/plugins with checkboxes.

    Tab switches between the two zones. This prevents menu actions from looking
    like selected artifacts and keeps the cursor visible even in long lists.
    """

    if not choices:
        return ConsoleMultiSelectResult([])

    # Compatibility bridge for old callers that still pass a synthetic "all"
    # row. New callers should pass artifact entries only and use `options`.
    legacy_special_indices = special_indices or {}
    if legacy_special_indices:
        artifact_choices: list[ConsoleChoice[T]] = []
        for index, choice in enumerate(choices):
            if index not in legacy_special_indices:
                artifact_choices.append(choice)
        choices = artifact_choices
        if default_special == "all":
            default_all = True
        if any(name in {"skip", "none"} for name in legacy_special_indices.values()):
            options = options or default_multi_select_options(include_skip=True)

    if options is None:
        options = default_multi_select_options()
    marker_width = choice_marker_width(choices)

    selected = {index for index, choice in enumerate(choices) if choice.checked}
    if default_all or (default_checked and not selected and default_special == "all"):
        selected = set(range(len(choices)))

    focus_zone = "entries"
    option_cursor = 0
    entry_cursor = 0
    rendered_lines = 0
    offset = 0
    status_cache: dict[int, str] = {}
    def detail_for(row_index: int, choice: ConsoleChoice[T]) -> str:
        if row_status_provider is None:
            return choice.detail
        if row_index not in status_cache:
            status_cache[row_index] = row_status_provider(choice)
        return status_cache[row_index]

    def apply_option(action: str) -> str:
        if action in {"select_all", "all"}:
            selected.clear()
            selected.update(range(len(choices)))
            return ""
        if action in {"select_none", "none", "clear"}:
            selected.clear()
            return ""
        if action in {"skip", "back", "cancel", "quit", "exit", "force", "reveal", "diagnostics"}:
            return action
        return ""

    def activate_option_hotkey(key: str) -> str:
        lowered = key.lower()
        for option in options:
            if option.key and option.key.lower() == lowered:
                return apply_option(option.action)
        return ""

    def activate_current_option() -> str:
        if not options:
            return ""
        safe_index = max(0, min(option_cursor, len(options) - 1))
        return apply_option(options[safe_index].action)

    def max_visible_entry_rows() -> int:
        # Fixed frame lines: title, footer, options block, selectable header,
        # box borders, central action, and one spare line to avoid terminal scroll.
        option_lines = 1 + len(options) if options else 0
        fixed = density().multiselect_reserved_lines + option_lines
        # Reserve room for possible "above/below" indicators inside the box.
        room = frame_line_limit() - fixed - 2
        return max(1, min(len(choices), room))

    def render_choice_line(row_index: int, choice: ConsoleChoice[T]) -> str:
        checked = row_index in selected
        num = f"{choice.number})" if choice.number is not None else "  "
        marker = choice_marker(choice, width=marker_width)
        detail = detail_for(row_index, choice)
        plain_detail = strip_ansi(detail)
        selected_suffix = f"  {plain_detail}" if plain_detail else ""
        suffix = f"  {detail}" if detail else ""
        plain = f"{num:>4} [{'x' if checked else ' '}] {strip_ansi(marker)}{choice.label}{selected_suffix}"
        if focus_zone == "entries" and row_index == entry_cursor:
            if color_enabled():
                return style_selected(plain)
            return ">" + plain[1:]
        current = theme()
        checkbox = paint("[x]", current.status_ok + ANSI_BOLD) if checked else paint("[ ]", current.border_muted)
        label = paint(choice.label, current.text_primary) if checked else choice.label
        return f"{num:>4} {checkbox} {marker}{label}{suffix}"

    def render_lines() -> list[str]:
        nonlocal offset, entry_cursor, option_cursor
        entry_cursor = max(0, min(entry_cursor, len(choices) - 1))
        option_cursor = max(0, min(option_cursor, max(0, len(options) - 1)))
        max_rows = max_visible_entry_rows()
        if entry_cursor < offset:
            offset = entry_cursor
        if entry_cursor >= offset + max_rows:
            offset = entry_cursor - max_rows + 1
        offset = max(0, min(offset, max(0, len(choices) - max_rows)))

        visible_choices = choices[offset : offset + max_rows]
        lines: list[str] = []
        lines.append(colorize_script_line(f"[MENU] {title}"))
        lines.append(colorize_script_line(f"[MENU] {footer}"))
        lines.extend(render_menu_options(options, active_index=option_cursor, focused=focus_zone == "options"))
        lines.append(render_focus_header("[SELECTABLE ENTRIES]", focused=focus_zone == "entries"))

        boxed_rows: list[str] = []
        if offset > 0:
            boxed_rows.append(paint(f"↑ {offset} item(s) above", theme().text_muted))
        for row_index, choice in enumerate(visible_choices, start=offset):
            boxed_rows.append(render_choice_line(row_index, choice))
        hidden_below = max(0, len(choices) - (offset + max_rows))
        if hidden_below:
            boxed_rows.append(paint(f"↓ {hidden_below} item(s) below", theme().text_muted))
        if not boxed_rows:
            boxed_rows.append(paint("no selectable entries", theme().text_muted))
        lines.extend(box_lines("artifacts", boxed_rows, width=terminal_width()))

        count = len(selected)
        summary = f"{count}/{len(choices)} selected"
        button_text = f"{action_label}  ({summary})"
        available = max(40, terminal_width() - 4)
        centered = button_text.center(min(available, max(len(strip_ansi(button_text)) + 8, 48)))
        lines.append(style_action(centered, selected=focus_zone == "entries"))
        return lines

    special_result = ""
    try:
        if color_enabled():
            sys.stdout.write(HIDE_CURSOR)
            sys.stdout.flush()
        while True:
            rendered_lines = replace_frame(rendered_lines, render_lines())
            key = read_key()
            low_key = key.lower() if len(key) == 1 else key
            if key == "tab":
                focus_zone = "options" if focus_zone == "entries" and options else "entries"
            elif key == "up":
                if focus_zone == "options":
                    option_cursor = move_cursor(option_cursor, -1, len(options))
                else:
                    entry_cursor = move_cursor(entry_cursor, -1, len(choices))
            elif key == "down":
                if focus_zone == "options":
                    option_cursor = move_cursor(option_cursor, 1, len(options))
                else:
                    entry_cursor = move_cursor(entry_cursor, 1, len(choices))
            elif key == "home":
                if focus_zone == "options":
                    option_cursor = 0
                else:
                    entry_cursor = 0
            elif key == "end":
                if focus_zone == "options":
                    option_cursor = max(0, len(options) - 1)
                else:
                    entry_cursor = len(choices) - 1
            elif key == "page_up":
                if focus_zone == "entries":
                    entry_cursor = move_cursor(entry_cursor, -max_visible_entry_rows(), len(choices))
                else:
                    option_cursor = 0
            elif key == "page_down":
                if focus_zone == "entries":
                    entry_cursor = move_cursor(entry_cursor, max_visible_entry_rows(), len(choices))
                else:
                    option_cursor = max(0, len(options) - 1)
            elif key == "space":
                if focus_zone == "options":
                    action = activate_current_option()
                    if action:
                        special_result = action
                        break
                else:
                    toggle_choice(entry_cursor, selected)
            elif key == "enter":
                if focus_zone == "options":
                    action = activate_current_option()
                    if action:
                        special_result = action
                        break
                else:
                    break
            elif key.isdigit():
                number = int(key)
                for index, choice in enumerate(choices):
                    if choice.number == number:
                        focus_zone = "entries"
                        entry_cursor = index
                        toggle_choice(index, selected)
                        break
            elif len(low_key) == 1:
                action = activate_option_hotkey(low_key)
                if action:
                    special_result = action
                    break
            elif key in {"escape", "backspace"}:
                special_result = "cancel"
                break
        clear_previous(rendered_lines)
    finally:
        if color_enabled():
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()

    values = [choice.value for index, choice in enumerate(choices) if index in selected]
    return ConsoleMultiSelectResult(values, special=special_result)
