from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .filesystem import best_effort_remove_path
from .logs import TeeLog
from .console_menu import ConsoleChoice, ConsoleMenuOption, interactive_menu_enabled, run_multi_select_menu
from .workspace_status import DetailPathProbe, TargetDllProbe, TargetPresenceProbe, make_workspace_status_provider
from .migration import apply_delete_list
from .paths import rel, suite_path, suite_root
from .progress import progress_configure, progress_update
from .selection import exclusive_choice_kind, split_choice_tokens
from .tools.constants import LEGACY_TOOL_PATHS

ALL_TARGET_CHOICE = "0"
DYNAMIC_LIBRARY_EXTENSIONS = {".dll", ".so", ".dylib"}
DYNAMIC_LIBRARY_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules"}



@dataclass(frozen=True)
class CleanTarget:
    key: str
    label: str
    path: Path
    category: str
    workspace_dir: Path


def _append_target(items: list[CleanTarget], root: Path, *, key: str, label: str, path: Path, category: str, workspace_dir: Path | None = None) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return
    items.append(CleanTarget(key=key, label=label, path=path, category=category, workspace_dir=workspace_dir or path.parent))


def discover_clean_targets(root: Path) -> list[CleanTarget]:
    items: list[CleanTarget] = []
    _append_target(items, root, key="engine", label="Engine workspace", path=root / "NewEngine" / "neocore2" / "target", category="engine", workspace_dir=root / "NewEngine" / "neocore2")

    plugins_root = root / "Plugins"
    if plugins_root.exists():
        for child in sorted(plugins_root.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                _append_target(items, root, key=f"plugin:{child.name}", label=f"Plugin: {child.name}", path=child / "target", category="plugin", workspace_dir=child)
                if child.name == "AssetManager":
                    codecs_root = child / "codecs"
                    if codecs_root.exists():
                        for nested in sorted(codecs_root.iterdir(), key=lambda p: p.name.lower()):
                            if nested.is_dir():
                                _append_target(items, root, key=f"codec:{nested.name}", label=f"Codec: {nested.name}", path=nested / "target", category="codec", workspace_dir=nested)

    importers_root = root / "Importers"
    if importers_root.exists():
        for child in sorted(importers_root.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                _append_target(items, root, key=f"importer:{child.name}", label=f"Importer: {child.name}", path=child / "target", category="importer", workspace_dir=child)

    for tools_root in [root / "tools" / "northstar", root / "tools"]:
        if not tools_root.exists():
            continue
        for cargo in sorted(tools_root.rglob("Cargo.toml"), key=lambda p: p.as_posix().lower()):
            tool_root = cargo.parent
            legacy_dir_names = {Path(raw).name.lower() for raw in LEGACY_TOOL_PATHS}
            if any(part.lower() == "target" or part.lower() in legacy_dir_names for part in tool_root.parts):
                continue
            _append_target(items, root, key=f"tool:{tool_root.name}", label=f"Native tool: {tool_root.name}", path=tool_root / "target", category="tool", workspace_dir=tool_root)
    # Deduplicate when tools/northstar is found by the broader tools scan.
    unique: dict[str, CleanTarget] = {}
    for item in items:
        unique.setdefault(str(item.path.resolve()).lower(), item)
    return list(unique.values())


def _numbered_clean_targets(targets: list[CleanTarget]) -> list[tuple[int, CleanTarget]]:
    numbered: list[tuple[int, CleanTarget]] = []
    for number, target in enumerate(targets, start=1):
        numbered.append((number, target))
    return numbered


def _selected_target_from_token(token: str, targets: list[CleanTarget]) -> CleanTarget:
    low = token.lower()
    numbered = dict(_numbered_clean_targets(targets))
    if token.isdigit():
        index = int(token)
        if index in numbered:
            return numbered[index]
        raise ValueError(f"target selection index is out of range: {token}")
    for target in targets:
        aliases = {target.key.lower(), target.label.lower(), target.path.name.lower()}
        if low in aliases:
            return target
    matches = [target for target in targets if low in target.key.lower() or low in target.label.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(target.key for target in matches)
        raise ValueError(f"target selection is ambiguous: {token} -> {names}")
    raise ValueError(f"unknown target selection: {token}")


def _selected_targets_from_choice(choice: str, targets: list[CleanTarget]) -> list[CleanTarget]:
    tokens = split_choice_tokens(choice)
    if not tokens:
        return targets

    special = exclusive_choice_kind(
        tokens,
        all_tokens={ALL_TARGET_CHOICE, "all", "*"},
        none_tokens={"none", "skip", "no"},
        all_error="all/0 cannot be mixed with explicit clean targets",
        none_error="skip/none/no cannot be mixed with explicit clean targets",
    )
    if special == "all":
        return targets
    if special == "none":
        return []

    selected: list[CleanTarget] = []
    seen: set[str] = set()
    for token in tokens:
        target = _selected_target_from_token(token, targets)
        key = str(target.path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(target)
    return selected


def select_clean_targets(root: Path, targets: list[CleanTarget], log: TeeLog, *, cli_choice: str = "") -> list[CleanTarget]:
    if not targets:
        log.emit("[WARN] No target directories are discoverable.")
        return []
    if cli_choice:
        return _selected_targets_from_choice(cli_choice, targets)
    env_choice = os.environ.get("NEWENGINE_CLEAN_TARGET") or os.environ.get("NEWENGINE_TARGET_CLEAN")
    if env_choice:
        return _selected_targets_from_choice(env_choice, targets)
    if os.environ.get("CI") or not sys.stdin.isatty():
        return targets

    # The cleanup menu must list real cleanup targets, not theoretical Cargo
    # workspaces that do not currently have a `target/` directory. Missing rows
    # looked inactive and made the multi-select surface noisy. Explicit CLI/env
    # selection still resolves against the full discoverable target set above.
    visible_targets = [target for target in targets if target.path.exists() or target.path.is_symlink()]
    if not visible_targets:
        log.emit("[INFO] No existing target directories are available for interactive cleanup.")
        return []

    status_provider = make_workspace_status_provider(root, probes=(TargetPresenceProbe(), TargetDllProbe(), DetailPathProbe()))

    if interactive_menu_enabled():
        choices: list[ConsoleChoice[object]] = [
            ConsoleChoice(value=target, number=number, label=target.label)
            for number, target in _numbered_clean_targets(visible_targets)
        ]
        result = run_multi_select_menu(
            title="Select target directories to clean",
            choices=choices,
            action_label="Start cleanup",
            default_all=True,
            options=[
                ConsoleMenuOption("select_all", "A", "All", "check all cleanup targets"),
                ConsoleMenuOption("select_none", "N", "None", "clear selected targets"),
                ConsoleMenuOption("skip", "S", "Skip", "do not clean target directories"),
                ConsoleMenuOption("cancel", "Q", "Cancel", "close cleanup command"),
            ],
            footer="Tab options/list  ↑/↓ move  Space toggle  Enter start/apply  number toggle  Backspace/Esc cancel",
            row_status_provider=status_provider,
        )
        if result.special == "skip":
            return []
        if result.special == "cancel":
            raise ValueError("Cleanup cancelled by user")
        return [value for value in result.selected_values if isinstance(value, CleanTarget)]

    log.emit("")
    log.emit("[CLEAN] Select target directory cleanup scope:")
    log.emit("[CLEAN]   0) all target directories")
    for number, target in _numbered_clean_targets(visible_targets):
        row = ConsoleChoice(value=target, number=number, label=target.label)
        log.emit(f"[CLEAN]   {number}) {target.label}  {status_provider(row)}")
    log.emit("[CLEAN]   comma-list is supported, example: 1,3,8")
    while True:
        choice = input("[CLEAN] What target directory should be cleaned? [0/all, comma-list allowed]: ").strip()
        try:
            return _selected_targets_from_choice(choice or ALL_TARGET_CHOICE, visible_targets)
        except ValueError as exc:
            log.emit(f"[WARN] {exc}")


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _iter_dynamic_libraries(root: Path, directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(directory):
        current = Path(dirpath)
        dirnames[:] = [name for name in dirnames if name.lower() not in DYNAMIC_LIBRARY_SKIP_DIRS]
        for filename in filenames:
            path = current / filename
            if path.suffix.lower() not in DYNAMIC_LIBRARY_EXTENSIONS:
                continue
            if not _is_inside(path, root):
                continue
            found.append(path)
    found.sort(key=lambda p: p.as_posix().lower())
    return found


def _iter_direct_dynamic_libraries(root: Path, directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in DYNAMIC_LIBRARY_EXTENSIONS:
            continue
        if not _is_inside(path, root):
            continue
        found.append(path)
    return found


def _runtime_plugin_binary_roots(root: Path) -> list[Path]:
    plugin_dir = root / "NewEngine" / "neocore2" / "plugins"
    if not plugin_dir.exists():
        return []
    return [plugin_dir]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _target_scoped_dynamic_libraries(root: Path, target: CleanTarget) -> list[Path]:
    """Return dynamic libraries owned by one clean target only.

    Target cleanup must never recursively inspect the whole workspace owner. For
    the engine target the owner is `NewEngine/neocore2`, and a recursive scan
    there includes `NewEngine/neocore2/plugins` — the runtime-installed plugin
    directory. Those binaries are cleaned only by the explicit full cleanup path.

    We still clean direct workspace-level cdylib leftovers because MSVC/linker
    output can escape the Cargo target directory, but this scan is intentionally
    non-recursive.
    """
    return _dedupe_paths([
        *_iter_dynamic_libraries(root, target.path),
        *_iter_direct_dynamic_libraries(root, target.workspace_dir),
    ])


SUITE_CACHE_ROOTS: tuple[str, ...] = (
    "buildInfo",
    "buildLog",
    "logs",
    "reports",
    "profiler",
    "tools",
    "git",
    "workspace",
    "build-artifacts",
    "build-state",
    "trash",
)


def clear_cache(root: Path, args: argparse.Namespace | None = None) -> int:
    """Clear generated Take Some suite state without deleting the env shim.

    Project root is the source/workspace root. Suite root is one level below it:
    `<project-root>/.takesome`. This command cleans generated cache/report/log
    state from the suite root, but preserves `.takesome/script-env.cmd` so the
    installed Script Env remains usable after cleanup.
    """
    apply_delete_list(root)
    log = TeeLog()
    suite = suite_root(root)
    suite.mkdir(parents=True, exist_ok=True)
    log.emit(f"[INFO] Clearing Take Some suite cache: {rel(root, suite)}")
    log.emit(f"[INFO] Project root: {root}")

    removed_count = 0
    skipped_count = 0
    warning_count = 0

    def remove_path(path: Path) -> None:
        nonlocal removed_count, skipped_count, warning_count
        label = rel(root, path)
        if path.name.lower() == "script-env.cmd":
            skipped_count += 1
            log.emit(f"[SKIP] Preserved Script Env: {label}")
            return
        if not path.exists() and not path.is_symlink():
            skipped_count += 1
            log.emit(f"[SKIP] {label}")
            return
        log.emit(f"[CLEAR] {label}")
        result = best_effort_remove_path(root, path, quarantine_on_failure=False)
        if result.status == "deleted":
            removed_count += 1
            suffix = f" ({result.message})" if result.message else ""
            log.emit(f"[OK] Cleared {label}{suffix}")
        elif result.status == "missing":
            skipped_count += 1
            log.emit(f"[SKIP] {label}")
        else:
            skipped_count += 1
            warning_count += 1
            log.emit(f"[WARN] Could not clear {label}: {result.message}; skipped and continuing")

    cleanup_paths = [suite_path(root, name) for name in SUITE_CACHE_ROOTS]
    # Clean loose suite-level log/report/temp files while preserving the env shim.
    for child in sorted(suite.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir():
            continue
        if child.name.lower() == "script-env.cmd":
            continue
        if child.suffix.lower() in {".log", ".tmp", ".temp", ".zip", ".json", ".md"}:
            cleanup_paths.append(child)

    progress_configure(total=max(1, len(cleanup_paths)), current=0, unit="path", phase="suite cache cleanup plan resolved")
    for index, path in enumerate(cleanup_paths, start=1):
        progress_update(current=index - 1, phase=f"clearing {rel(root, path)}")
        remove_path(path)
        progress_update(current=index, phase=f"finished {rel(root, path)}")

    log.emit(f"[INFO] Suite cache summary: cleaned={removed_count} skipped={skipped_count} warnings={warning_count}")
    if warning_count:
        log.emit("[WARN] Suite cache cleanup completed with warnings")
        return 1
    log.emit("[OK] Suite cache cleanup completed")
    return 0


def clean_workspace(root: Path, args: argparse.Namespace) -> int:
    apply_delete_list(root)
    log = TeeLog()
    log.emit(f"[INFO] Cleaning North Star workspace: {root}")

    removed_count = 0
    skipped_count = 0
    warning_count = 0
    dynamic_library_count = 0

    def remove_path(path: Path) -> str:
        nonlocal removed_count, skipped_count, warning_count
        label = rel(root, path)
        if not path.exists() and not path.is_symlink():
            skipped_count += 1
            log.emit(f"[SKIP] {label}")
            return "missing"
        log.emit(f"[CLEAN] {label}")
        result = best_effort_remove_path(root, path, quarantine_on_failure=False)
        if result.status == "deleted":
            removed_count += 1
            suffix = f" ({result.message})" if result.message else ""
            log.emit(f"[OK] Cleaned {label}{suffix}")
        elif result.status == "missing":
            skipped_count += 1
            log.emit(f"[SKIP] {label}")
        else:
            skipped_count += 1
            warning_count += 1
            log.emit(f"[WARN] Could not clean {label}: {result.message}; skipped and continuing")
        return result.status

    def clean_dynamic_library_artifacts(artifacts: list[Path], *, label: str, reason: str) -> None:
        nonlocal dynamic_library_count
        artifacts = _dedupe_paths(artifacts)
        if not artifacts:
            return
        log.emit(f"[INFO] Dynamic library cleanup for {label}: {len(artifacts)} file(s), reason={reason}")
        before = removed_count
        for artifact in artifacts:
            remove_path(artifact)
        dynamic_library_count += max(0, removed_count - before)

    def clean_dynamic_libraries(directory: Path, *, reason: str) -> None:
        clean_dynamic_library_artifacts(
            _iter_dynamic_libraries(root, directory),
            label=rel(root, directory),
            reason=reason,
        )

    targets = discover_clean_targets(root)
    try:
        selected_targets = select_clean_targets(root, targets, log, cli_choice=str(getattr(args, "target_scope", "") or ""))
    except ValueError as exc:
        log.emit(f"[ERROR] {exc}")
        return 2
    if selected_targets:
        suffix = "y" if len(selected_targets) == 1 else "ies"
        log.emit(f"[INFO] Target cleanup selection: {len(selected_targets)} director{suffix}")
    else:
        log.emit("[INFO] Target cleanup selection: skipped")
    if selected_targets:
        progress_configure(total=max(1, len(selected_targets)), current=0, unit="target", phase="workspace cleanup plan resolved")
    for index, target in enumerate(selected_targets, start=1):
        progress_update(current=index - 1, phase=f"cleaning {target.label}")
        remove_path(target.path)
        clean_dynamic_library_artifacts(
            _target_scoped_dynamic_libraries(root, target),
            label=target.label,
            reason=f"target:{target.key}",
        )
        progress_update(current=index, phase=f"finished {target.label}")

    if not bool(getattr(args, "full", False)):
        log.emit("[INFO] Full workspace cleanup skipped; target cleanup only. Use --full to clean logs/cache/build-state/runtime binaries.")
        log.emit(f"[INFO] Cleanup summary: cleaned={removed_count} skipped={skipped_count} warnings={warning_count} dylibs={dynamic_library_count}")
        log.emit("[OK] Target cleanup completed")
        return 0

    log.emit("[INFO] Full workspace cleanup enabled: logs/cache/build-state/runtime plugin binaries may be removed.")
    full_paths: list[Path] = []
    if not args.keep_logs:
        full_paths.extend([
            root / "NewEngine" / "neocore2" / "logs",
            suite_path(root, "logs"),
            suite_path(root, "buildLog"),
            suite_path(root, "buildInfo"),
        ])
        full_paths.extend(sorted(root.glob("lastbuild*.log")))
    if not args.keep_cache:
        full_paths.extend([root / "NewEngine" / "neocore2" / "cache", suite_path(root, "tools")])
    full_paths.append(suite_path(root, "build-state"))
    if full_paths:
        progress_configure(total=max(1, len(full_paths)), current=0, unit="path", phase="full cleanup plan resolved")
    for index, path in enumerate(full_paths, start=1):
        progress_update(current=index - 1, phase=f"cleaning {rel(root, path)}")
        remove_path(path)
        progress_update(current=index, phase=f"finished {rel(root, path)}")
    if not args.keep_plugin_binaries:
        binary_roots = _runtime_plugin_binary_roots(root)
        progress_configure(total=max(1, len(binary_roots)), current=0, unit="binary-root", phase="runtime binary cleanup plan resolved")
        for index, binary_root in enumerate(binary_roots, start=1):
            progress_update(current=index - 1, phase=f"cleaning runtime binaries {rel(root, binary_root)}")
            clean_dynamic_libraries(binary_root, reason="runtime-plugin-binaries")
            progress_update(current=index, phase=f"finished runtime binaries {rel(root, binary_root)}")
    log.emit(f"[INFO] Cleanup summary: cleaned={removed_count} skipped={skipped_count} warnings={warning_count} dylibs={dynamic_library_count}")
    log.emit("[OK] Workspace cleanup completed")
    return 0
