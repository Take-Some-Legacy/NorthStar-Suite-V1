from __future__ import annotations

import os
import sys
from pathlib import Path

from ..console import colorize_script_line
from ..console_menu import ConsoleChoice, ConsoleMenuOption, interactive_menu_enabled, run_action_menu, run_multi_select_menu
from ..platforms import available_build_platforms, build_platform_from_args, is_build_platform_token, normalize_build_platform
from ..workspace_status import DetailPathProbe, PluginSyncStatusProbe, make_workspace_status_provider
from ..selection import exclusive_choice_kind, split_choice_tokens
from .manifest import discover_plugin_names


def has_explicit_build_type(args: list[str]) -> bool:
    return any(arg.lower() in {"dev", "debug", "release"} for arg in args)


def has_explicit_build_platform(args: list[str]) -> bool:
    for arg in args:
        low = arg.lower()
        if low in {"--platform", "--build-platform", "--target", "--rust-target"}:
            return True
        if low.startswith(("--platform=", "--build-platform=", "--target=", "--rust-target=")):
            return True
    return False


def prompt_for_build_platform(args: list[str]) -> list[str]:
    if has_explicit_build_platform(args):
        return args
    env_choice = os.environ.get("NEWENGINE_BUILD_PLATFORM") or os.environ.get("NEWENGINE_PLUGIN_BUILD_PLATFORM")
    if env_choice:
        return [*args, "--platform", normalize_build_platform(env_choice).id]
    if os.environ.get("NEWENGINE_PARENT_SCRIPT") or os.environ.get("CI") or not sys.stdin.isatty():
        return args

    platforms = available_build_platforms()
    if interactive_menu_enabled():
        result = run_action_menu(
            title="Select plugin build platform",
            choices=[
                ConsoleChoice(value=item.id, number=None, label=item.label, detail=item.detail)
                for item in platforms
            ],
            footer="↑/↓ choose platform  Enter continue  Esc current host",
        )
        if not result.cancelled and result.selected_value:
            return [*args, "--platform", str(result.selected_value)]
        return args

    print()
    print(colorize_script_line("[BUILD] Select plugin build platform:"))
    for item in platforms:
        print(colorize_script_line(f"[BUILD]   {item.id:<20} - {item.label}; {item.detail}"))
    while True:
        choice = input("[BUILD] Platform [current host]: ").strip().lower()
        if not choice:
            return args
        return [*args, "--platform", normalize_build_platform(choice).id]


def prompt_for_build_type(args: list[str]) -> list[str]:
    if has_explicit_build_type(args):
        return args
    env_choice = os.environ.get("NEWENGINE_BUILD_TYPE") or os.environ.get("NEWENGINE_PLUGIN_BUILD_TYPE")
    if env_choice and env_choice.lower() in {"dev", "debug", "release"}:
        return [*args, env_choice.lower()]
    if os.environ.get("NEWENGINE_PARENT_SCRIPT") or os.environ.get("CI") or not sys.stdin.isatty():
        return [*args, "dev"]

    platform = build_platform_from_args(args)
    ext = platform.library_ext
    if interactive_menu_enabled():
        result = run_action_menu(
            title="Select plugin build type",
            choices=[
                ConsoleChoice(value="dev", number=None, label="dev", detail=f"fast local iteration; installs *-dev{ext}"),
                ConsoleChoice(value="debug", number=None, label="debug", detail=f"Cargo debug profile; installs *-debug{ext}"),
                ConsoleChoice(value="release", number=None, label="release", detail=f"optimized build; installs *-release{ext}"),
            ],
            footer="↑/↓ choose build type  Enter continue  Esc default dev",
        )
        if not result.cancelled and result.selected_value:
            return [*args, str(result.selected_value)]
        return [*args, "dev"]

    print()
    print(colorize_script_line("[BUILD] Select plugin build type:"))
    print(colorize_script_line(f"[BUILD]   dev     - fast local iteration, installs *-dev{ext}"))
    print(colorize_script_line(f"[BUILD]   debug   - Cargo debug profile, installs *-debug{ext}"))
    print(colorize_script_line(f"[BUILD]   release - optimized build, installs *-release{ext}"))
    while True:
        choice = input("[BUILD] Type dev/debug/release [dev]: ").strip().lower()
        if not choice:
            choice = "dev"
        if choice in {"dev", "debug", "release"}:
            return [*args, choice]
        print(colorize_script_line("[WARN] Please enter dev, debug or release."))



def build_type_from_args(args: list[str]) -> str:
    for arg in args:
        low = arg.lower()
        if low in {"dev", "debug", "release"}:
            return low
    return "dev"

def explicit_plugin_target_present(args: list[str]) -> bool:
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        low = arg.strip().strip('"').strip("'").lower()
        if low in {"--platform", "--build-platform", "--target", "--rust-target"}:
            skip_next = True
            continue
        if low in {"--force", "-f", "dev", "debug", "release", "help", "--help", "-h"}:
            continue
        if is_build_platform_token(low):
            continue
        if low.startswith(("--platform=", "--build-platform=", "--target=", "--rust-target=")):
            continue
        return True
    return False


def resolve_plugin_choice(choice: str, plugins: list[str]) -> str | None:
    selected = resolve_plugin_choices(choice, plugins)
    if selected is None:
        return None
    if len(selected) != 1:
        raise ValueError("Plugin selection expects one target; use comma-list only where multi-selection is supported")
    return selected[0]


def _resolve_one_plugin_choice(token: str, plugins: list[str]) -> str:
    low = token.lower()
    if token.isdigit():
        index = int(token)
        if 1 <= index <= len(plugins):
            return plugins[index - 1]
        raise ValueError(f"Plugin selection index is out of range: {token}")
    for name in plugins:
        if name.lower() == low:
            return name
    raise ValueError(f"Unknown plugin target: {token}")


def resolve_plugin_choices(choice: str, plugins: list[str]) -> list[str] | None:
    tokens = split_choice_tokens(choice)
    if not tokens:
        return None
    special = exclusive_choice_kind(
        tokens,
        all_tokens={"0", "all", "*"},
        all_error="all/0 cannot be mixed with explicit plugin targets",
    )
    if special == "all":
        return None

    selected: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        name = _resolve_one_plugin_choice(token, plugins)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(name)
    return selected


def prompt_for_plugin_target(root: Path, args: list[str]) -> list[str]:
    if explicit_plugin_target_present(args):
        return args
    plugins = discover_plugin_names(root)
    if not plugins:
        return args

    env_choice = os.environ.get("NEWENGINE_PLUGIN_TARGET") or os.environ.get("NEWENGINE_BUILD_TARGET")
    if env_choice:
        selected = resolve_plugin_choices(env_choice, plugins)
        return [*args, ",".join(selected)] if selected else args

    if os.environ.get("NEWENGINE_PARENT_SCRIPT") or os.environ.get("CI") or not sys.stdin.isatty():
        return args

    build_type = build_type_from_args(args)
    platform_id = build_platform_from_args(args).id
    # Build target rows should describe buildability, not look like dead cleanup
    # artifacts. Showing `target: missing` for never-built plugins made valid
    # plugins appear inactive. Keep the build menu focused on sync status +
    # source path, and give every plugin a stable numeric row.
    status_provider = make_workspace_status_provider(
        root,
        probes=(PluginSyncStatusProbe(build_type, platform_id), DetailPathProbe()),
        build_type=build_type,
        platform_id=platform_id,
    )

    if interactive_menu_enabled():
        choices: list[ConsoleChoice[str]] = [
            ConsoleChoice(value=name, number=index, label=name)
            for index, name in enumerate(plugins, start=1)
        ]
        result = run_multi_select_menu(
            title="Select plugin targets",
            choices=choices,
            action_label="Start plugin sync",
            default_all=True,
            options=[
                ConsoleMenuOption("select_all", "A", "All", "check all plugin targets"),
                ConsoleMenuOption("select_none", "N", "None", "clear selected plugin targets"),
                ConsoleMenuOption("cancel", "Q", "Cancel", "close plugin sync"),
            ],
            footer="Tab options/list  ↑/↓ move  Space toggle  Enter start/apply  number toggle  Backspace/Esc cancel",
            row_status_provider=status_provider,
        )
        if result.special == "cancel":
            return args
        selected = [value for value in result.selected_values if value]
        if len(selected) == len(plugins) or not selected:
            return args
        return [*args, ",".join(selected)]

    print()
    print(colorize_script_line("[BUILD] Select plugin target:"))
    print(colorize_script_line("[BUILD]   all plugins is the default"))
    for index, name in enumerate(plugins, start=1):
        row = ConsoleChoice(value=name, number=index, label=name)
        print(colorize_script_line(f"[BUILD]   {name}  {status_provider(row)}"))
    print(colorize_script_line("[BUILD]   comma-list by plugin name is supported, example: AssetManager,ProfilerPlugin"))
    while True:
        choice = input("[BUILD] What should be built? [all or comma-list by name]: ").strip()
        try:
            selected = resolve_plugin_choices(choice, plugins)
        except ValueError as exc:
            print(colorize_script_line(f"[WARN] {exc}"))
            continue
        return [*args, ",".join(selected)] if selected else args
