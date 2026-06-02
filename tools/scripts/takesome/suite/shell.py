from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..console import (
    color_enabled,
    colorize_script_line,
    console_emit,
    paint,
    render_tag,
    risk_style,
    strip_ansi,
)
from ..console.theme import density, theme
from ..console_menu import ConsoleChoice, interactive_menu_enabled, run_action_menu, run_dual_action_menu
from ..console.frame import ellipsize_middle, terminal_height, terminal_render_width, terminal_width
from ..migration import apply_delete_list
from ..paths import rel, suite_root
from ..progress import progress_update
from .actions import SuiteAction, SuiteCategory
from .context import SuiteContext, load_suite_context
from .env import ensure_script_env
from .progress_frame import SuiteStatusFrame
from .registry import SuiteRegistry, build_suite_registry
from .output import emit_actions_json, run_suite_action_structured
from .settings import apply_suite_settings, ensure_suite_settings, load_suite_settings

SUITE_VERSION = "0.6.0"


def _clear_screen() -> None:
    if os.environ.get("NEWENGINE_SUITE_NO_CLEAR"):
        return
    if not sys.stdout.isatty():
        return
    os.system("cls" if os.name == "nt" else "clear")


def _suite_title() -> str:
    return f"Take Some() Suite v{SUITE_VERSION}"


def _fit_visible(text: str, width: int) -> str:
    width = max(0, width)
    plain = strip_ansi(text)
    if width <= 0:
        return ""
    if len(plain) <= width:
        return text + " " * (width - len(plain))
    if width <= 1:
        return "…"[:width]
    return plain[: width - 1] + "…"


def _clip_plain(text: str, width: int) -> str:
    plain = strip_ansi(text)
    if width <= 0:
        return ""
    if len(plain) <= width:
        return plain
    if width == 1:
        return "…"
    return plain[: width - 1] + "…"


def _latest_file(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def _last_build_label(root: Path) -> str:
    candidates = [root / "lastbuild.log", root / "lastbuild-all.log"]
    latest = _latest_file(candidates)
    if latest is None:
        return "none"
    try:
        text = latest.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        text = ""
    status = "failed" if "[ERROR]" in text or "error:" in text.lower() else "available"
    return f"{status} · {rel(root, latest)}"


def _last_build_err_label(root: Path) -> str:
    latest = _latest_file(list(root.glob("buildERR-*.log")))
    if latest is None:
        return "none"
    return rel(root, latest)


def _panel(title: str, rows: list[tuple[str, str]], *, width: int) -> list[str]:
    inner = max(20, width - 2)
    title_text = f" {title} "
    if len(strip_ansi(title_text)) >= inner:
        title_text = ""
    top = "╠" + (title_text if title_text else "") + "═" * max(0, inner - len(strip_ansi(title_text))) + "╣"
    lines = [top]
    if not rows:
        return lines
    max_key = max([len(k) for k, _ in rows] + [6])
    key_width = min(max_key, max(6, min(18, inner // 3)))
    for key, value in rows:
        shown_key = _clip_plain(key, key_width)
        if inner < 54:
            body_plain = f"{shown_key}: {value}"
            body = paint(shown_key, theme().text_heading) + paint(": ", theme().text_muted) + value if color_enabled() else body_plain
        else:
            body_plain = f"{shown_key:<{key_width}} : {value}"
            body = (
                paint(f"{shown_key:<{key_width}}", theme().text_heading)
                + paint(" : ", theme().text_muted)
                + value
                if color_enabled()
                else body_plain
            )
        lines.append("║ " + _fit_visible(body, inner - 2) + " ║")
    return lines


def _path_label(root: Path, value: Path, *, width: int) -> str:
    if width >= 104:
        return str(value)
    if value == root:
        return value.name
    if value.is_relative_to(root):
        candidate = rel(root, value)
    else:
        candidate = str(value)
    if width < 72:
        return ellipsize_middle(candidate, max(10, width // 2))
    return candidate


def _banner(root: Path, context: SuiteContext | None = None) -> list[str]:
    context = context or load_suite_context(root)
    settings = load_suite_settings(root)
    apply_suite_settings(settings)
    width = max(32, min(density().banner_max_width, terminal_render_width(118)))
    height = terminal_height(32)
    inner = width - 2
    title = f" {_suite_title()} — North Star Engine Command Center "
    title = _clip_plain(title, max(8, inner))
    top = "╔" + title + "═" * max(0, inner - len(strip_ansi(title))) + "╗"
    bottom = "╚" + "═" * inner + "╝"
    cockpit_rows = [
        ("Active profile", context.profile),
        ("Active platform", context.platform.id),
        ("Context source", context.source),
        ("Visual theme", settings.theme),
        ("Density", settings.density),
        ("Last build", _last_build_label(root)),
        ("Last build err", _last_build_err_label(root)),
    ]
    path_rows = [
        ("Project root", _path_label(root, root, width=width)),
        ("Suite root", _path_label(root, suite_root(root), width=width)),
        ("Engine root", _path_label(root, root / "NewEngine" / "neocore2", width=width)),
    ]
    density_mode = density().path_mode
    lines = [top, *_panel("COCKPIT", cockpit_rows, width=width)]
    # Paths are operator preferences now, not hardcoded chrome. Density controls
    # how much detail survives on short terminals.
    if settings.show_paths:
        if density_mode == "wide" and height >= 18:
            lines.extend(_panel("PATHS", path_rows, width=width))
        elif density_mode == "compact" and height >= 20:
            lines.extend(_panel("PATHS", [("Root", _path_label(root, root, width=width)), ("Engine", _path_label(root, root / "NewEngine" / "neocore2", width=width))], width=width))
        elif height >= 24:
            lines.extend(_panel("PATHS", path_rows, width=width))
        elif height >= 18:
            lines.extend(_panel("PATHS", [("Project", _path_label(root, root, width=width)), ("Engine", _path_label(root, root / "NewEngine" / "neocore2", width=width))], width=width))
    lines.append(bottom)
    if color_enabled():
        rendered: list[str] = []
        for line in lines:
            if line.startswith(("╔", "╠", "╚")):
                rendered.append(paint(line, theme().border_primary))
            elif line.startswith("║"):
                rendered.append(line)
            else:
                rendered.append(line)
        return rendered
    return lines

def _print_banner(root: Path, context: SuiteContext | None = None) -> None:
    for line in _banner(root, context):
        print(line)
    print(colorize_script_line("[MENU] Tab recent/groups  ↑/↓ move  Enter open/run  number focus  Backspace/Esc back"))


def _wait_return_to_menu() -> None:
    if os.environ.get("CI") or not sys.stdin.isatty() or os.environ.get("NEWENGINE_SUITE_NO_WAIT"):
        return
    try:
        print()
        input(colorize_script_line("[MENU] Press Enter to return to the suite main menu..."))
    except EOFError:
        return


def _choice_detail(text: str, tone: str = "") -> str:
    if not color_enabled():
        return text
    current = theme()
    style = {
        "good": current.status_ok,
        "warn": current.status_warn,
        "bad": current.status_error,
        "info": current.status_info,
    }.get(tone, current.text_muted)
    return paint(text, style)


def _action_detail(action: SuiteAction) -> str:
    detail = action.operator_detail()
    if not color_enabled():
        return detail
    pieces = [piece.strip() for piece in detail.split(" · ")]
    rendered: list[str] = []
    for piece in pieces:
        if piece == action.risk_label:
            rendered.append(paint(piece, risk_style(action.risk_level)))
        else:
            rendered.append(paint(piece, theme().text_muted))
    return paint(" · ", theme().border_muted).join(rendered)


def _action_choice(action: SuiteAction, *, number: int | None) -> ConsoleChoice[SuiteAction]:
    # Primary tag is the structural command type. Detail is intentionally chips,
    # not another tag pile: domain · profile · risk.
    return ConsoleChoice(
        value=action,
        number=number,
        label=action.label,
        detail=_action_detail(action),
        marker=action.primary_tag,
    )


def _select_main(root: Path, registry: SuiteRegistry) -> SuiteCategory | SuiteAction | None:
    primary_choices: list[ConsoleChoice[SuiteCategory | SuiteAction]] = [
        ConsoleChoice(value=category, number=index, label=category.label, detail=_choice_detail(category.detail, "info"), marker=category.marker)
        for index, category in enumerate(registry.command_blocks(), start=1)
    ]
    recent = registry.recent(root) if load_suite_settings(root).show_recent else []
    recent_choices: list[ConsoleChoice[SuiteCategory | SuiteAction]] = [
        _action_choice(action, number=None) for action in recent
    ]

    if interactive_menu_enabled():
        result = run_dual_action_menu(
            title=f"{_suite_title()} — Command center",
            primary_title="COMMAND BLOCKS",
            primary_choices=primary_choices,
            secondary_title="RECENT ACTIONS",
            secondary_choices=recent_choices,
            footer="Tab blocks/recent  ↑/↓ move  Enter open/run  number focus  Backspace/Esc quit",
            header_lines=lambda: _banner(root),
        )
        if result.cancelled or result.selected_value is None:
            return None
        value = result.selected_value
        if isinstance(value, (SuiteCategory, SuiteAction)):
            return value
        return None

    print(colorize_script_line(f"[MENU] {_suite_title()} — Main menu"))
    for index, category in enumerate(registry.command_blocks(), start=1):
        print(f"  {index}) [{category.marker}] {category.label} - {category.detail}")
    if recent:
        print("\nRecent Actions:")
        for index, action in enumerate(recent, start=1):
            print(f"  r{index}) [{action.primary_tag}] {action.label} - {action.operator_detail()}")
    raw = input("Select group/action (q to exit): ").strip()
    if raw.lower() in {"", "q", "quit", "exit"}:
        return None
    low = raw.lower()
    if low.startswith("r") and low[1:].isdigit():
        index = int(low[1:]) - 1
        if 0 <= index < len(recent):
            return recent[index]
    for index, category in enumerate(registry.command_blocks(), start=1):
        if raw == str(index):
            return category
    console_emit(f"[WARN] Unknown group/action: {raw}")
    return None


def _select_action(root: Path, registry: SuiteRegistry, category: SuiteCategory) -> SuiteAction | None:
    actions = registry.category_actions(category.key)
    choices: list[ConsoleChoice[SuiteAction | str]] = [
        _action_choice(action, number=index) for index, action in enumerate(actions, start=1)
    ]
    if interactive_menu_enabled():
        result = run_action_menu(
            title=f"{_suite_title()} — {category.label}",
            choices=choices,
            footer="↑/↓ move  Enter run  number focus  Backspace/Esc back",
            header_lines=lambda: _banner(root),
        )
        if result.cancelled or result.selected_value is None:
            return None
        return result.selected_value if isinstance(result.selected_value, SuiteAction) else None

    print(colorize_script_line(f"[MENU] {category.label}"))
    for index, action in enumerate(actions, start=1):
        print(f"  {index}) [{action.primary_tag}] {action.label} - {action.operator_detail()}")
    raw = input("Select action (blank/q to go back): ").strip()
    if raw.lower() in {"", "q", "quit", "back"}:
        return None
    for index, action in enumerate(actions, start=1):
        if raw == str(index):
            return action
    console_emit(f"[WARN] Unknown action: {raw}")
    return None


def _run_action(root: Path, registry: SuiteRegistry, action: SuiteAction) -> int:
    context = load_suite_context(root)
    _clear_screen()
    _print_banner(root, context)
    console_emit(f"[INFO] Starting action: {render_tag(action.primary_tag)} {action.label}")
    console_emit(f"[INFO] {action.detail}")
    console_emit(f"[STATE] {action.operator_detail()}")
    task_log_top = len(_banner(root, context)) + 5
    with SuiteStatusFrame(action, scroll_top=task_log_top) as status:
        progress_update(current=0, total=action.progress_total, unit=action.progress_unit, phase="starting")
        previous_env = {key: os.environ.get(key) for key in context.with_env()}
        os.environ.update(context.with_env())
        try:
            rc = registry.run(root, action)
        except KeyboardInterrupt:
            console_emit("[WARN] Action interrupted by user.")
            rc = 130
        except Exception as exc:
            console_emit(f"[ERROR] Action crashed: {type(exc).__name__}: {exc}")
            rc = 1
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        status.finish("completed" if rc == 0 else f"failed rc={rc}", failed=(rc != 0))
        if rc == 0:
            console_emit("[OK] Action completed. Returning to suite menu.")
        else:
            console_emit(f"[ERROR] Action completed with exit code {rc}. Returning to suite menu.")
        _wait_return_to_menu()
    return rc


def list_actions(registry: SuiteRegistry | None = None, *, root: Path | None = None) -> int:
    if registry is None:
        if root is None:
            root = Path.cwd()
        registry = build_suite_registry(root)

    for category in registry.command_blocks():
        print(f"[{category.key}] {category.label}")
        for action in registry.category_actions(category.key):
            print(f"  {action.key:<32} [{action.primary_tag:<7}] {action.label} :: {action.operator_detail()} :: {action.detail}")
    return 0


def run_action_by_key(root: Path, key: str, registry: SuiteRegistry | None = None) -> int:
    ensure_suite_settings(root)
    registry = registry or build_suite_registry(root)
    action = registry.action(key)
    if action is None:
        console_emit(f"[ERROR] Unknown suite action: {key}")
        console_emit("[INFO] Use: takesome.py suite --list-actions")
        return 2
    rc = _run_action(root, registry, action)
    registry.record_recent(root, action, suite_version=SUITE_VERSION)
    return rc


def _suite_command_unstructured(root: Path, args: argparse.Namespace) -> int:
    registry = build_suite_registry(root)
    if getattr(args, "list_actions", False):
        return list_actions(root=root)
    rc = ensure_script_env(root, suite_version=SUITE_VERSION)
    if rc != 0:
        return rc
    ensure_suite_settings(root)
    apply_delete_list(root)
    if getattr(args, "run", ""):
        return run_action_by_key(root, args.run, registry)

    last_rc = 0
    try:
        while True:
            _clear_screen()
            if not interactive_menu_enabled():
                _print_banner(root)
            selection = _select_main(root, registry)
            if selection is None:
                console_emit("[OK] Suite closed by user.")
                return last_rc
            if isinstance(selection, SuiteAction):
                action = selection
            else:
                _clear_screen()
                if not interactive_menu_enabled():
                    _print_banner(root)
                action = _select_action(root, registry, selection)
                if action is None:
                    continue
            last_rc = _run_action(root, registry, action)
            registry.record_recent(root, action, suite_version=SUITE_VERSION)
    except KeyboardInterrupt:
        print()
        console_emit("[OK] Suite closed by user.")
        return last_rc


def suite_command(root: Path, args: argparse.Namespace) -> int:
    """Structured-output aware Suite command entrypoint.

    Plain console behavior is preserved by delegating to the original implementation.
    Machine clients opt into SuiteOutputEnvelope with --json.
    """

    if bool(getattr(args, "json", False)):
        if bool(getattr(args, "list_actions", False)):
            return emit_actions_json(
                root,
                SUITE_VERSION,
                lambda: build_suite_registry(root),
                output_dir=str(getattr(args, "output_dir", "") or ""),
            )
        if str(getattr(args, "run", "") or "").strip():
            return run_suite_action_structured(
                root,
                args,
                SUITE_VERSION,
                lambda: build_suite_registry(root),
                ensure_env=None,
                apply_delete=apply_delete_list,
            )
    return _suite_command_unstructured(root, args)
