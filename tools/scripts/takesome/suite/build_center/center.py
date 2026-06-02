from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from ...archive import pack_source
from ...clean import discover_clean_targets
from ...console import console_emit
from ...console_menu import ConsoleChoice, ConsoleMenuOption, interactive_menu_enabled, run_action_menu, run_multi_select_menu
from ...filesystem import best_effort_remove_path
from ...game import run_game
from ...importers import build_importers
from ...paths import rel
from ...plugin_build import build_plugins
from ...plugin_status import collect_plugin_status, plugin_status_command
from ...tools import tools_command
from ..context import load_suite_context
from ...cargo.process import cargo_exe


@dataclass(frozen=True)
class BuildCenterTarget:
    key: str
    label: str
    detail: str
    marker: str
    checked: bool = False


@dataclass(frozen=True)
class BuildCenterMode:
    key: str
    label: str
    detail: str


@dataclass(frozen=True)
class BuildCenterAfter:
    key: str
    label: str
    detail: str
    marker: str
    checked: bool = False


_TARGETS = (
    BuildCenterTarget("plugins", "Plugins", "runtime plugin providers", "BUILD", True),
    BuildCenterTarget("codecs", "Codecs", "AssetManager codec workers", "CODEC", True),
    BuildCenterTarget("importers", "Importers", "source/import pipeline tools", "IMPORT", False),
    BuildCenterTarget("game", "Game app", "game-ready-fps cargo app", "RUN", False),
    BuildCenterTarget("tools", "Tools", "safe native Take Some tools", "TOOLS", False),
)

_MODES = (
    BuildCenterMode("stale", "Stale only", "rebuild only targets that status providers mark stale"),
    BuildCenterMode("force", "Force rebuild", "ignore stamps and rebuild selected target groups"),
    BuildCenterMode("clean", "Clean rebuild", "remove selected target dirs first, then force rebuild"),
)

_AFTER = (
    BuildCenterAfter("plugin_status", "Plugin status", "write/show plugin status after build", "STATUS", True),
    BuildCenterAfter("run_game", "Run game", "launch game-ready-fps after successful build", "RUN", False),
    BuildCenterAfter("pack_source", "Pack source", "write clean source snapshot after successful build", "PACK", False),
)


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _select_targets() -> list[str]:
    if not interactive_menu_enabled():
        return [target.key for target in _TARGETS if target.checked]
    choices = [
        ConsoleChoice(value=target.key, number=index, label=target.label, detail=target.detail, checked=target.checked, marker=target.marker)
        for index, target in enumerate(_TARGETS, start=1)
    ]
    result = run_multi_select_menu(
        title="Build Center — targets",
        choices=choices,
        action_label="Select build targets",
        footer="A all  N none  Space toggle  Enter next  Esc cancel",
        options=[
            ConsoleMenuOption("select_all", "A", "All", "check all build target groups"),
            ConsoleMenuOption("select_none", "N", "None", "clear target groups"),
            ConsoleMenuOption("cancel", "Q", "Cancel", "return to Suite"),
        ],
        default_checked=False,
    )
    if result.special in {"cancel", "quit", "back"}:
        return []
    return [str(value) for value in result.selected_values]


def _select_mode() -> str:
    if not interactive_menu_enabled():
        return "stale"
    choices = [
        ConsoleChoice(value=mode.key, number=index, label=mode.label, detail=mode.detail, marker="BUILD")
        for index, mode in enumerate(_MODES, start=1)
    ]
    result = run_action_menu(
        title="Build Center — mode",
        choices=choices,
        footer="↑/↓ move  Enter select  number focus  Esc cancel",
    )
    if result.cancelled or result.selected_value is None:
        return ""
    return str(result.selected_value)


def _select_after() -> list[str]:
    if not interactive_menu_enabled():
        return [item.key for item in _AFTER if item.checked]
    choices = [
        ConsoleChoice(value=item.key, number=index, label=item.label, detail=item.detail, checked=item.checked, marker=item.marker)
        for index, item in enumerate(_AFTER, start=1)
    ]
    result = run_multi_select_menu(
        title="Build Center — after build",
        choices=choices,
        action_label="Start Build Center",
        footer="A all  N none  Space toggle  Enter start  Esc cancel",
        options=[
            ConsoleMenuOption("select_all", "A", "All", "check all post-build actions"),
            ConsoleMenuOption("select_none", "N", "None", "clear post-build actions"),
            ConsoleMenuOption("cancel", "Q", "Cancel", "return to Suite"),
        ],
        default_checked=False,
    )
    if result.special in {"cancel", "quit", "back"}:
        return []
    return [str(value) for value in result.selected_values]


def _status_targets(root: Path, *, profile: str, platform_id: str, include_plugins: bool, include_codecs: bool, force: bool = False) -> list[str]:
    status = collect_plugin_status(root, build_type=profile, platform_id=platform_id, force=force)
    targets: list[str] = []
    seen: set[str] = set()
    for record in status.get("records", []):
        kind = str(record.get("kind", ""))
        if kind == "plugin" and not include_plugins:
            continue
        if kind == "codec-worker" and not include_codecs:
            continue
        if not force and not record.get("needs_rebuild"):
            continue
        if record.get("status_key") in {"disabled", "missing_source"}:
            continue
        name = str(record.get("name", ""))
        if not name:
            continue
        low = name.lower()
        if low in seen:
            continue
        seen.add(low)
        targets.append(name)
    return targets


def _clean_selected_target_dirs(root: Path, selected: set[str]) -> int:
    category_map = {
        "plugins": {"plugin"},
        "codecs": {"codec"},
        "importers": {"importer"},
        "tools": {"tool"},
        "game": {"engine"},
    }
    wanted_categories: set[str] = set()
    for key in selected:
        wanted_categories.update(category_map.get(key, set()))
    if not wanted_categories:
        return 0
    targets = [target for target in discover_clean_targets(root) if target.category in wanted_categories]
    if not targets:
        console_emit("[CLEAN] Build Center clean rebuild: no matching target directories found.")
        return 0
    console_emit(f"[CLEAN] Build Center removing {len(targets)} target director{'y' if len(targets) == 1 else 'ies'}.")
    warnings = 0
    for target in targets:
        result = best_effort_remove_path(root, target.path, quarantine_on_failure=True)
        if result.status in {"deleted", "quarantined"}:
            console_emit(f"[DELETE] {rel(root, target.path)}")
        elif result.status == "missing":
            console_emit(f"[SKIP] missing {rel(root, target.path)}")
        else:
            warnings += 1
            console_emit(f"[WARN] Could not clean {rel(root, target.path)}: {result.message}")
    return 1 if warnings else 0


def _build_plugins_and_codecs(root: Path, *, profile: str, platform_id: str, selected: set[str], mode: str) -> int:
    include_plugins = "plugins" in selected
    include_codecs = "codecs" in selected
    if not include_plugins and not include_codecs:
        return 0
    force = mode in {"force", "clean"}
    targets = _status_targets(root, profile=profile, platform_id=platform_id, include_plugins=include_plugins, include_codecs=include_codecs, force=force)
    if not targets and mode == "stale":
        console_emit("[OK] Build Center: no stale plugin/codec targets.")
        return 0
    args: list[str] = []
    if targets:
        args.append(",".join(targets))
    args.append(profile)
    args.extend(["--platform", platform_id])
    if force:
        args.append("--force")
    console_emit(f"[BUILD] Build Center plugin/codecs args: {' '.join(args)}")
    return build_plugins(root, args, pause=False)


def _build_game_app(root: Path, *, profile: str) -> int:
    # Build-only path for the game app: runGame owns sync+launch, but Build Center
    # needs a non-launching game target. Reuse the same Cargo manifest contract.
    manifest = root / "NewEngine" / "neocore2" / "apps" / "game-ready-fps" / "Cargo.toml"
    if not manifest.exists():
        console_emit(f"[ERROR] game-ready-fps manifest not found: {rel(root, manifest)}")
        return 2
    cargo = cargo_exe() or ("cargo.exe" if os.name == "nt" else "cargo")
    cargo_profile = "release" if profile == "release" else "dev"
    cmd = [
        cargo,
        "build",
        "--color=always",
        "--message-format=json-diagnostic-rendered-ansi",
        "--bin",
        "game-ready-fps",
        "--profile",
        cargo_profile,
        "--manifest-path",
        str(manifest),
    ]
    console_emit(f"[BUILD] Build Center game app: {' '.join(cmd)}")
    import subprocess

    try:
        result = subprocess.run(cmd, cwd=root)
    except FileNotFoundError:
        console_emit("[ERROR] cargo was not found; cannot build game-ready-fps")
        return 127
    return int(result.returncode)


def _build_tools(root: Path) -> int:
    return tools_command(root, _ns(tools_action="build", tool_id="", release=False, safe=True, validate_after_build=False))


def _run_after(root: Path, *, profile: str, after: set[str]) -> int:
    if "plugin_status" in after:
        code = plugin_status_command(root, [profile])
        if code != 0:
            return code
    if "run_game" in after:
        code = run_game(root, [profile])
        if code != 0:
            return code
    if "pack_source" in after:
        code = pack_source(root, _ns(output="", exclude_dir=None, exclude_ext=None, exclude_file=None, verbose=False))
        if code != 0:
            return code
    return 0


def build_center(root: Path) -> int:
    context = load_suite_context(root)
    console_emit("[BUILD] Build Center")
    console_emit(f"[STATE] Profile: {context.profile}")
    console_emit(f"[STATE] Platform: {context.platform.id}")

    selected = set(_select_targets())
    if not selected:
        console_emit("[BUILD] Build Center cancelled: no targets selected.")
        return 0
    mode = _select_mode()
    if not mode:
        console_emit("[BUILD] Build Center cancelled: no mode selected.")
        return 0
    after = set(_select_after())

    console_emit(f"[STATE] Targets: {', '.join(sorted(selected))}")
    console_emit(f"[STATE] Mode: {mode}")
    console_emit(f"[STATE] After build: {', '.join(sorted(after)) if after else 'none'}")

    if mode == "clean":
        clean_code = _clean_selected_target_dirs(root, selected)
        if clean_code != 0:
            return clean_code

    code = _build_plugins_and_codecs(root, profile=context.profile, platform_id=context.platform.id, selected=selected, mode=mode)
    if code != 0:
        return code

    if "importers" in selected:
        code = build_importers(root, [context.profile])
        if code != 0:
            return code

    if "game" in selected:
        code = _build_game_app(root, profile=context.profile)
        if code != 0:
            return code

    if "tools" in selected:
        code = _build_tools(root)
        if code != 0:
            return code

    return _run_after(root, profile=context.profile, after=after)
