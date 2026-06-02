from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..archive import pack_source
from ..clean import clean_workspace, clear_cache
from ..game import run_game
from ..git_batch import git_batch_push_command
from ..importers import build_importers
from ..migration import sync_workspace_state
from ..plugin_build import build_codecs, build_plugins
from ..plugin_status import plugin_status_command
from ..tools import tools_command, validate_build_tools, run_p0_invariant_scan, run_p1_capability_conformance_scan, run_p2_schema_property_scan, run_p21_schema_runtime_scan, run_p3_editor_shell_scan, run_p4_import_pipeline_scan, run_p5_world_scene_save_load_scan, run_p6_gameplay_foundation_scan, run_p7_rendering_maturity_scan, run_p8_reference_module_completeness_scan
from ..workspace_registry import workspace_registry_command
from .actions import SuiteAction, SuiteCategory
from .operator_toolbelt import write_operator_toolbelt
from ..endless.recipes import fix_direct_provider_scan, full_cycle, loop
from .context import context_build_args, context_profile_args, select_suite_context
from .settings import select_suite_visual_settings
from .build_center import build_center
from .fs_plan import filesystem_plan, filesystem_status
from .fs_execute import fs_mkdir
from .long_tasks import bootstrap_long_tasks, long_tasks_status, record_long_task_iteration, seed_engine_research_backlog, run_long_task_verification, pin_long_task_success_to_github
from .missions import build_mission_actions
from .patches import apply_changed_files_patch, inspect_patch_zip, rollback_last_patch, verify_last_patch
from .recent import recent_actions, record_recent_action
from .status.plugin_health import (
    explain_plugin_state,
    force_rebuild_stale_plugins,
    plugin_health_matrix,
    rebuild_stale_plugins,
)


@dataclass(frozen=True)
class SuiteRegistry:
    """Authoritative descriptor registry for suite command discovery.

    The shell is allowed to ask the registry for command blocks, actions, recent
    actions, and bound execution. The shell must not keep a parallel `_TASKS`
    table or call command implementation functions directly.
    """

    categories: tuple[SuiteCategory, ...]
    actions_by_category: dict[str, tuple[SuiteAction, ...]]
    _actions_by_key: dict[str, SuiteAction] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        category_keys = [category.key for category in self.categories]
        duplicate_categories = _duplicates(category_keys)
        if duplicate_categories:
            raise ValueError(f"duplicate suite categories: {', '.join(duplicate_categories)}")

        valid_categories = set(category_keys)
        action_map: dict[str, SuiteAction] = {}
        for category_key, actions in self.actions_by_category.items():
            if category_key not in valid_categories:
                raise ValueError(f"suite action group references unknown category: {category_key}")
            for action in actions:
                if not action.key:
                    raise ValueError(f"suite action in category {category_key} has empty key")
                if not action.primary_tag:
                    raise ValueError(f"suite action {action.key} has empty primary_tag")
                if action.category != category_key:
                    raise ValueError(
                        f"suite action {action.key} is stored under {category_key} "
                        f"but declares category {action.category}"
                    )
                if action.key in action_map:
                    raise ValueError(f"duplicate suite action key: {action.key}")
                action_map[action.key] = action

        object.__setattr__(self, "_actions_by_key", action_map)

    def command_blocks(self) -> tuple[SuiteCategory, ...]:
        """Return visible command blocks for the main menu."""

        return self.categories

    def category_actions(self, category_key: str) -> tuple[SuiteAction, ...]:
        """Return actions belonging to one visible command block."""

        return self.actions_by_category.get(category_key, ())

    def actions(self) -> tuple[SuiteAction, ...]:
        """Return all actions in menu order."""

        result: list[SuiteAction] = []
        for category in self.categories:
            result.extend(self.category_actions(category.key))
        return tuple(result)

    def by_key(self) -> dict[str, SuiteAction]:
        """Return a read-style action map for compatibility with older callers."""

        return dict(self._actions_by_key)

    def action(self, key: str) -> SuiteAction | None:
        return self._actions_by_key.get(key)

    def recent(self, root: Path) -> tuple[SuiteAction, ...]:
        """Return recently executed actions resolved through current descriptors."""

        return tuple(recent_actions(root, self._actions_by_key))

    def record_recent(self, root: Path, action: SuiteAction, *, suite_version: str) -> None:
        record_recent_action(root, action, self._actions_by_key, suite_version=suite_version)

    def run(self, root: Path, action: SuiteAction) -> int:
        """Execute a bound suite action implementation."""

        return int(action.run(root))


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicate: list[str] = []
    for value in values:
        if value in seen and value not in duplicate:
            duplicate.append(value)
        seen.add(value)
    return duplicate


def _ns(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _build_plugins(args: Iterable[str] | None = None):
    return lambda root: build_plugins(root, list(args or []))


def _run_game(args: Iterable[str] | None = None):
    return lambda root: run_game(root, list(args or []))


def _build_importers(args: Iterable[str] | None = None):
    return lambda root: build_importers(root, list(args or []))


def _tools_action(action: str, **kwargs: object):
    return lambda root: tools_command(root, _ns(tools_action=action, **kwargs))


def _ai_bridge_status(root: Path) -> int:
    bridge = root / "tools" / "scripts" / "northstar_ai_bridge.py"
    if not bridge.exists():
        print(f"[ERROR] AI bridge entrypoint not found: {bridge}")
        return 2
    return subprocess.call(
        [sys.executable, str(bridge), "--root", str(root), "--hello"],
        cwd=str(root),
    )


def _git_batch(root: Path) -> int:
    return git_batch_push_command(
        root,
        _ns(
            message_pos="",
            message="",
            dry_run=False,
            no_push=False,
            allow_empty=False,
            remote="origin",
            max_depth=4,
            only=None,
        ),
    )


def _workspace_registry(root: Path) -> int:
    return workspace_registry_command(root, _ns(output=""))


def _pack_source(root: Path) -> int:
    return pack_source(root, _ns(output="", exclude_dir=None, exclude_ext=None, exclude_file=None, verbose=False))


def _clean_workspace(root: Path) -> int:
    return clean_workspace(root, _ns(full=False, keep_logs=False, keep_cache=False, keep_plugin_binaries=False, target_scope=""))


def _clean_workspace_full(root: Path) -> int:
    # Full cleanup is used by agents/bridge and must never open an interactive selector.
    return clean_workspace(root, _ns(full=True, keep_logs=False, keep_cache=False, keep_plugin_binaries=False, target_scope="all"))


def _clear_cache(root: Path) -> int:
    return clear_cache(root, _ns())


def _plugin_status(args: Iterable[str] | None = None):
    return lambda root: plugin_status_command(root, list(args or []))


def _build_codecs(args: Iterable[str] | None = None):
    return lambda root: build_codecs(root, list(args or []))



def _context_build_plugins(root: Path) -> int:
    return build_plugins(root, context_build_args(root))


def _context_plugin_status(root: Path) -> int:
    return plugin_status_command(root, context_build_args(root))


def _context_build_codecs(root: Path) -> int:
    return build_codecs(root, context_build_args(root))


def _context_build_importers(root: Path) -> int:
    return build_importers(root, context_profile_args(root))


def _context_run_game(root: Path) -> int:
    return run_game(root, context_profile_args(root))

def build_builtin_registry() -> SuiteRegistry:
    categories = (
        SuiteCategory("profile", "Profile", "active build/run profile and platform", "PROFILE"),
        SuiteCategory("missions", "Missions", "production workflow chains", "MISSION"),
        SuiteCategory("long_tasks", "Long Tasks", "multi-iteration implementation and research backlog", "LONG"),
        SuiteCategory("building", "Building", "plugins, importers, runtime launch", "BUILD"),
        SuiteCategory("patching", "Patch workflow", "inspect, apply, verify and rollback changed-files patches", "PATCH"),
        SuiteCategory("maintenance", "Maintenance", "health matrix, stale rebuilds, production diagnostics", "STATUS"),
        SuiteCategory("cleaning", "Cache & cleaning", "suite cache, workspace cleanup, sync", "CLEAN"),
        SuiteCategory("git", "Git", "batch commit/push and workspace registry", "GIT"),
        SuiteCategory("devtools", "Dev tools", "doctor, registry, collect-run, source bundle", "TOOLS"),
    )

    profile = (
        SuiteAction("profile.select", "Select active profile/platform", "choose global defaults used by Build/Status/Run commands", select_suite_context, "PROFILE", "profile", "suite", "writes_cache"),
        SuiteAction("profile.visual", "Visual settings", "theme, density, cockpit paths and recent-actions preferences", select_suite_visual_settings, "PROFILE", "profile", "suite", "writes_cache"),
    )

    long_tasks = (
        SuiteAction("long.bootstrap", "Bootstrap long tasks", "create persistent implementation/research task board and doctrine", bootstrap_long_tasks, "LONG", "long_tasks", "suite", "writes_task_state", "active", 4, "artifact"),
        SuiteAction("long.status", "Long task status", "show multi-iteration task board status and next candidates", long_tasks_status, "LONG", "long_tasks", "suite", "diagnostics", "active", 1, "step"),
        SuiteAction("long.iteration", "Record next long-task iteration", "select current candidates and create an iteration evidence note", record_long_task_iteration, "LONG", "long_tasks", "suite", "writes_task_state", "active", 3, "task"),
        SuiteAction("long.research.seed", "Seed engine research backlog", "add research tasks for engine architecture and rendering/asset studies", seed_engine_research_backlog, "LONG", "long_tasks", "research", "writes_task_state", "active", 1, "step"),
        SuiteAction("long.verify", "Verify long-task iteration", "dataset check, build, runtime/diagnostic analysis, profiling and MD/JSON timing report", run_long_task_verification, "LONG", "long_tasks", "suite", "runs_process", "active", 8, "stage"),
        SuiteAction("long.github.pin", "Pin verified long-task success", "commit and push only after successful long-task verification gate", pin_long_task_success_to_github, "LONG", "long_tasks", "git", "git_push", "active", 3, "gate"),
    )


    patching = (
        SuiteAction("patch.inspect", "Inspect patch zip", "inspect root changed-files patch zip without modifying workspace", inspect_patch_zip, "PATCH", "patching", "source", "diagnostics"),
        SuiteAction("patch.apply", "Apply changed-files patch", "backup touched files, apply selected patch zip, run Suite self-test", apply_changed_files_patch, "PATCH", "patching", "source", "destructive_cleanup"),
        SuiteAction("patch.verify", "Verify last patch", "validate last applied patch and run Suite self-test", verify_last_patch, "PATCH", "patching", "source", "diagnostics"),
        SuiteAction("patch.rollback", "Rollback last patch", "restore touched files from .takesome/patch-backups", rollback_last_patch, "PATCH", "patching", "source", "destructive_cleanup"),
    )

    maintenance = (
        SuiteAction("status.plugin_matrix", "Plugin health matrix", "inspect plugin/codec readiness and optionally rebuild selected targets", plugin_health_matrix, "STATUS", "maintenance", "plugins", "diagnostics", "active"),
        SuiteAction("build.plugins.stale", "Rebuild stale plugins", "build only stale plugin/codec targets for active profile/platform", rebuild_stale_plugins, "BUILD", "maintenance", "plugins", "writes_runtime_plugins", "active"),
        SuiteAction("diag.plugin_state", "Explain plugin state", "print plugin/codec status reasons, artifacts and stamps", explain_plugin_state, "DIAG", "maintenance", "plugins", "diagnostics", "active"),
    )

    building = (
        SuiteAction("build.center", "Build Center", "choose targets, mode and post-build actions from one production surface", build_center, "BUILD", "building", "workspace", "writes_runtime_plugins", "active", 5, "phase"),
        SuiteAction("build.plugins", "Build plugins", "build/sync plugins using active profile and platform", _context_build_plugins, "BUILD", "building", "plugins", "writes_runtime_plugins", "active"),
        SuiteAction("build.plugins.dev", "Build plugins: dev", "build/sync runtime plugins in dev profile", _build_plugins(["dev"]), "BUILD", "building", "plugins", "writes_runtime_plugins", "dev"),
        SuiteAction("build.plugins.release", "Build plugins: release", "build/sync runtime plugins in release profile", _build_plugins(["release"]), "BUILD", "building", "plugins", "writes_runtime_plugins", "release"),
        SuiteAction("build.plugins.force.dev", "Force rebuild plugins: dev", "ignore stamps and rebuild dev plugin targets", _build_plugins(["dev", "--force"]), "BUILD", "building", "plugins", "force_rebuild", "dev"),
        SuiteAction("build.status", "Plugin status", "show stale/up-to-date plugin matrix for active profile/platform", _context_plugin_status, "STATUS", "building", "plugins", "diagnostics", "active"),
        SuiteAction("build.codecs", "Build codecs", "build AssetManager codec workers using active profile/platform", _context_build_codecs, "CODEC", "building", "codecs", "writes_runtime_codecs", "active"),
        SuiteAction("build.importers", "Build importers", "build importer toolchain using active profile", _context_build_importers, "IMPORT", "building", "importers", "writes_tools", "active"),
        SuiteAction("runtime.run", "Run game-ready-fps", "use active profile, sync plugins, build app, launch runtime demo", _context_run_game, "RUN", "building", "runtime", "runs_process", "active", 3, "phase"),
    )

    cleaning = (
        SuiteAction("cache.clear", "Clear suite cache", "clean .takesome generated logs/reports/cache, preserve script-env.cmd", _clear_cache, "CACHE", "cleaning", "suite", "writes_cache", progress_total=11, progress_unit="path"),
        SuiteAction("workspace.clean", "Clean workspace targets", "interactive target cleanup", _clean_workspace, "CLEAN", "cleaning", "workspace", "destructive_cleanup"),
        SuiteAction("workspace.clean.full", "Full workspace cleanup", "non-interactive cleanup of all targets plus logs/cache/build-state/runtime binaries", _clean_workspace_full, "CLEAN", "cleaning", "workspace", "destructive_cleanup"),
        SuiteAction("workspace.sync", "Sync workspace state", "apply DELETE_FILES.txt and patch/migration hooks", sync_workspace_state, "SYNC", "cleaning", "workspace", "migration"),
    )

    git = (
        SuiteAction("git.batch", "Git batch commit/push", "discover repos and run guided batch commit/push", _git_batch, "GIT", "git", "repositories", "mutates_git"),
        SuiteAction("git.registry", "Workspace registry", "write workspace registry JSON/MD into .takesome/workspace", _workspace_registry, "DOC", "git", "workspace", "writes_reports"),
    )

    devtools = (
        SuiteAction("tools.menu", "Developer tools menu", "open detailed tools menu", _tools_action("menu"), "TOOLS", "devtools", "tools", "readonly"),
        SuiteAction("ai.bridge.status", "AI bridge status", "print northstar-ai-bridge local status and launch guidance", _ai_bridge_status, "AI", "devtools", "suite", "diagnostics"),
        SuiteAction("tools.scan", "Scan tools", "refresh .takesome/tools/tool-registry.json", _tools_action("scan"), "SYNC", "devtools", "tools", "writes_cache"),
        SuiteAction("tools.validate", "Validate tool registry", "descriptor and build-validator checks", _tools_action("validate"), "DIAG", "devtools", "tools", "diagnostics"),
        SuiteAction("tools.doctor", "Workspace doctor", "fast suite/workspace health check", _tools_action("doctor", full=False), "DOC", "devtools", "workspace", "diagnostics"),
        SuiteAction("tools.doctor.full", "Full workspace doctor", "deep diagnostics and findings", _tools_action("doctor", full=True), "DOC", "devtools", "workspace", "diagnostics"),
        SuiteAction("diag.invariants", "P0 invariant scan", "workspace drift, provider ids, hidden fallbacks, boundaries and large modules", run_p0_invariant_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.conformance", "P1 capability/conformance scan", "capability matrix, route diagnostics, null providers and provider-family harness", run_p1_capability_conformance_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.schema", "P2 schema/property scan", "engine.schema, property DTOs, Inspector bridge, scripting bindings and transaction DTOs", run_p2_schema_property_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.schema.runtime", "P2.1 schema runtime scan", "core-owned replaceable engine.schema provider route and execution harness", run_p21_schema_runtime_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.editor.shell", "P3 editor shell scan", "Scene Tree, Inspector, Asset Browser, Import Queue, Output Log, Profiler/Diagnostics and Viewport Gizmos through engine.ui", run_p3_editor_shell_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.import.pipeline", "P4 import pipeline scan", "importer descriptors, runtime graph, deterministic cache keys and package writer capability", run_p4_import_pipeline_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.world.scene", "P5 world/scene/save-load scan", "streaming cells, prefab/archetype plans, snapshots and runtime apply-stage mutation", run_p5_world_scene_save_load_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.gameplay", "P6 gameplay foundation scan", "engine.animation/navigation/ai/tags/tasks and intent-only AI boundary", run_p6_gameplay_foundation_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.rendering", "P7 rendering maturity scan", "render feature capabilities, material/shader graph, postfx/probes/VFX/terrain and debug overlays", run_p7_rendering_maturity_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.reference.completeness", "P8 reference module completeness scan", "reference archive coverage, workspace membership and Domains & Gateways parity map", run_p8_reference_module_completeness_scan, "DIAG", "devtools", "architecture", "diagnostics"),
        SuiteAction("diag.dataset.ingest", "Dataset ingest pipeline", "detect new root archives, materialize, semantic-split, classify value/applicability and cache knowledge particles", _tools_action("dataset-ingest"), "DIAG", "devtools", "dataset", "diagnostics", output_schema="northstar.dataset.ingest_pipeline.v1"),
        SuiteAction("diag.dataset.lifecycle", "Dataset archive lifecycle", "materialize archive ingest objects into dataSet/extracted and delete .zip sources", _tools_action("dataset-lifecycle"), "DIAG", "devtools", "dataset", "diagnostics", output_schema="northstar.dataset.archive_lifecycle.v1"),
        SuiteAction("diag.dataset.entry_value", "Dataset Entry value analysis", "score materialized dataSet entries and map them to engine domains/capabilities/repair queues", _tools_action("dataset-entry-analysis"), "DIAG", "devtools", "dataset", "diagnostics", output_schema="northstar.dataset.entry_value_index.v1"),
        SuiteAction("diag.dataset.maturity", "Dataset maturity scan", "index-first architecture radar over dataset-index/browser-index/knowledge-registry", _tools_action("dataset-maturity"), "DIAG", "devtools", "dataset", "diagnostics", output_schema="northstar.dataset.maturity_scan.v1"),
        SuiteAction("diag.dataset.maturity.strict", "Strict Dataset maturity scan", "fail on missing gateway/capability/NullProvider/conformance/visible production gaps", _tools_action("dataset-maturity-strict"), "DIAG", "devtools", "dataset", "diagnostics", output_schema="northstar.dataset.maturity_scan.v1"),
        SuiteAction("diag.operator.memory", "Maintain operator memory", "prune stale generated task/knowledge/note/cache data and refresh current engine state", _tools_action("operator-memory"), "DIAG", "devtools", "operator-memory", "writes_cache", output_schema="northstar.operator.memory_maintenance.v1"),
        SuiteAction("import.ui.assets", "Compile UI import assets", "generate runtime asset graph and pack .neui descriptors", _tools_action("import-ui-assets", check=False, skip_neui=False), "IMPORT", "devtools", "assets", "writes_assets"),
        SuiteAction("import.ui.assets.check", "Check UI import assets", "validate runtime asset graph and .neui descriptors without writing", _tools_action("import-ui-assets", check=True, skip_neui=False), "DIAG", "devtools", "assets", "diagnostics"),
        SuiteAction("tools.collect", "Collect run report", "write run-bundle-*.zip into project root", _tools_action("collect-run"), "DIAG", "devtools", "runtime", "writes_reports"),
        SuiteAction("tools.build.safe", "Build safe native tools", "build safe descriptors only", _tools_action("build", tool_id="", release=False, safe=True, validate_after_build=False), "BUILD", "devtools", "tools", "writes_tools"),
        SuiteAction("tools.build.safe.validate", "Build safe tools + validate", "build safe descriptors and run validation_args", _tools_action("build", tool_id="", release=False, safe=True, validate_after_build=True), "BUILD", "devtools", "tools", "writes_tools"),
        SuiteAction("tools.validate.build", "Validate build pipeline", "validate registered build tools before plugin sync", validate_build_tools, "DIAG", "devtools", "build pipeline", "diagnostics"),
        SuiteAction("endless.fix.direct-provider-scan", "Fix direct provider scanner precision", "ignore legal provider ids in capability/conformance/test descriptors", fix_direct_provider_scan, "FIX", "devtools", "endless stream", "writes_source", output_schema="northstar.endless.recipe.v1"),
        SuiteAction("endless.full-cycle", "Run Endless Stream full cycle", "run local Endless Stream cycle through registered Suite action", full_cycle, "RUN", "devtools", "endless stream", "writes_reports", output_schema="northstar.endless.full_cycle.v1"),
        SuiteAction("endless.loop", "Run Endless Stream loop", "run unbounded local Endless Stream cycles until STOP signal, interrupt or failure", loop, "RUN", "devtools", "endless stream", "writes_reports", output_schema="northstar.endless.loop.v1"),
        SuiteAction("filesystem.status", "Filesystem operator status", "show controlled filesystem operator policy and default plan path", filesystem_status, "DIAG", "devtools", "filesystem", "diagnostics", output_schema="northstar.filesystem.status.v1"),
        SuiteAction("filesystem.plan", "Validate filesystem plan", "validate .takesome/filesystem/operations.json without executing operations", filesystem_plan, "PLAN", "devtools", "filesystem", "diagnostics", output_schema="northstar.filesystem.plan.v1"),
        SuiteAction("filesystem.mkdir", "Create filesystem workspace", "create .takesome/filesystem/workspace controlled directory", fs_mkdir, "MKDIR", "devtools", "filesystem", "writes_files", output_schema="northstar.filesystem.mkdir.v1"),
        SuiteAction("tools.operator.toolbelt", "Pin operator toolbelt", "write the simple bounded toolbelt for chat/Suite work", write_operator_toolbelt, "DIAG", "devtools", "operator tooling", "writes_reports", output_schema="northstar.suite.operator_toolbelt.v1"),
        SuiteAction("source.pack", "Pack source snapshot", "create clean source archive", _pack_source, "PACK", "devtools", "source", "writes_zip"),
    )

    base_actions = (*profile, *long_tasks, *maintenance, *building, *patching, *cleaning, *git, *devtools)
    missions = build_mission_actions({action.key: action for action in base_actions})

    return SuiteRegistry(
        categories=categories,
        actions_by_category={
            "profile": profile,
            "missions": missions,
            "long_tasks": long_tasks,
            "building": building,
            "patching": patching,
            "maintenance": maintenance,
            "cleaning": cleaning,
            "git": git,
            "devtools": devtools,
        },
    )
