from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path
from typing import Any

from ..console import ANSI_BRIGHT_CYAN, ANSI_BRIGHT_GREEN, ANSI_BRIGHT_YELLOW, ANSI_DIM, paint
from ..console_menu import ConsoleChoice, interactive_menu_enabled, run_action_menu
from ..logs import TeeLog, run_process
from ..import_pipeline import import_pipeline_command
from ..migration import apply_delete_list
from ..paths import rel
from .build import build_registered_tools, build_tool_descriptor, run_tool_validation
from .cache import scan_and_cache_tools
from .collect import collect_run_bundle
from .descriptors import discover_tools, expand_tool_args, target_exe, tool_by_id
from .doctor import run_workspace_doctor
from .dataset_lifecycle import dataset_lifecycle_cleanup
from .dataset_ingest_pipeline import dataset_ingest_pipeline
from .dataset_entry_value import dataset_entry_value_analysis
from .dataset_maturity import dataset_maturity_command
from .operator_memory import operator_memory_maintenance
from .invariants import run_p0_invariant_scan, run_p1_capability_conformance_scan, run_p2_schema_property_scan, run_p21_schema_runtime_scan, run_p3_editor_shell_scan, run_p4_import_pipeline_scan, run_p5_world_scene_save_load_scan, run_p6_gameplay_foundation_scan, run_p7_rendering_maturity_scan, run_p8_reference_module_completeness_scan
from .validation import validate_build_tools


@dataclass(frozen=True)
class DevToolAction:
    key: str
    label: str
    detail: str
    tone: str = ""


_DEV_TOOL_ACTIONS: tuple[DevToolAction, ...] = (
    DevToolAction("scan", "Scan tool descriptors", "refresh .takesome/tools/tool-registry cache", "info"),
    DevToolAction("list", "List registered tools", "show ids, kinds, roots and capabilities", "info"),
    DevToolAction("validate", "Validate tool registry", "check descriptor surface, build validators and P0 invariants", "good"),
    DevToolAction("invariants", "Run P0 invariant scan", "workspace drift, provider ids, hidden fallbacks, boundaries and large modules", "warn"),
    DevToolAction("conformance", "Run P1 conformance scan", "capability matrix, null providers, route diagnostics and provider-family harness", "good"),
    DevToolAction("schema", "Run P2 schema/property scan", "engine.schema, property DTOs, Inspector bridge, scripting bindings and transaction DTOs", "good"),
    DevToolAction("schema-runtime", "Run P2.1 schema runtime scan", "core-owned replaceable engine.schema provider route and execution harness", "good"),
    DevToolAction("editor-shell", "Run P3 editor shell scan", "Scene Tree, Inspector, Asset Browser, Import Queue, Output Log, Profiler/Diagnostics and Viewport Gizmos through engine.ui", "good"),
    DevToolAction("import-pipeline", "Run P4 import pipeline scan", "importer descriptors, runtime graph, cache keys and package-writer capability", "good"),
    DevToolAction("world-scene", "Run P5 world/scene/save-load scan", "streaming cells, prefab plans, snapshots and runtime apply-stage ownership", "good"),
    DevToolAction("gameplay", "Run P6 gameplay foundation scan", "animation, navigation, AI, tags/tasks and intent-only AI boundary", "good"),
    DevToolAction("rendering", "Run P7 rendering maturity scan", "render capabilities, material/shader graph, postfx/probes/VFX/terrain and debug overlays", "good"),
    DevToolAction("reference-completeness", "Run P8 reference module completeness scan", "reference archive coverage, workspace membership and Domains & Gateways parity map", "warn"),
    DevToolAction("reference-completeness-strict", "Run P8 strict reference parity scan", "treat declared dataSet/reference production gaps as blocking findings", "warn"),
    DevToolAction("dataset-lifecycle", "Run dataSet archive lifecycle", "materialize archive ingest objects, write manifests and delete .zip sources", "warn"),
    DevToolAction("dataset-entry-analysis", "Run dataSet Entry value analysis", "analyze materialized entries, score architecture value and write repair hints", "good"),
    DevToolAction("dataset-maturity", "Run dataSet maturity scan", "index-first architecture radar over dataset-index/browser-index/knowledge-registry", "good"),
    DevToolAction("dataset-maturity-strict", "Run strict dataSet maturity scan", "fail on missing gateway/capability/NullProvider/conformance/visible gaps", "warn"),
    DevToolAction("operator-memory", "Maintain operator memory", "prune stale generated task/knowledge/note/cache data and refresh current engine state", "good"),
    DevToolAction("import-ui-assets", "Compile UI import assets", "build generated runtime graph and pack .neui import descriptors", "good"),
    DevToolAction("doctor", "Run workspace doctor", "fast health check for workspace/script/tooling state", "good"),
    DevToolAction("doctor-full", "Run full workspace doctor", "detailed findings and diagnostics", "warn"),
    DevToolAction("collect-run", "Collect run bundle", "pack logs/configs into project-root run-bundle-*.zip", "info"),
    DevToolAction("build", "Build all native tools", "build every registered tool descriptor", "warn"),
    DevToolAction("build-safe", "Build safe native tools", "build descriptors marked safe_for_build/build_validation", "good"),
    DevToolAction("build-safe-validate", "Build safe tools and validate", "build safe tools, then run descriptor validation_args", "good"),
)


def _action_detail(action: DevToolAction) -> str:
    tone = {
        "good": ANSI_BRIGHT_GREEN,
        "warn": ANSI_BRIGHT_YELLOW,
        "info": ANSI_BRIGHT_CYAN,
    }.get(action.tone, ANSI_DIM)
    return paint(action.detail, tone)


def _run_plain_tools_menu(repo_root: Path, log: TeeLog) -> int:
    log.emit("[MENU] Developer tools")
    for number, action in enumerate(_DEV_TOOL_ACTIONS, start=1):
        log.emit(f"  {number}) {action.label} - {action.detail}")
    try:
        raw = input("Select action number, or blank to cancel: ").strip()
    except EOFError:
        log.emit("[SKIP] Developer tools menu cancelled: no interactive input.")
        return 0
    if not raw:
        log.emit("[SKIP] Developer tools menu cancelled.")
        return 0
    try:
        index = int(raw) - 1
    except ValueError:
        log.emit(f"[ERROR] Invalid action number: {raw}")
        return 2
    if index < 0 or index >= len(_DEV_TOOL_ACTIONS):
        log.emit(f"[ERROR] Action number out of range: {raw}")
        return 2
    return _dispatch_dev_tool_action(repo_root, _DEV_TOOL_ACTIONS[index], log=log)


def _run_tools_menu(repo_root: Path, log: TeeLog) -> int:
    choices = [
        ConsoleChoice(
            value=action,
            number=index,
            label=action.label,
            detail=_action_detail(action),
        )
        for index, action in enumerate(_DEV_TOOL_ACTIONS, start=1)
    ]
    if not interactive_menu_enabled():
        return _run_plain_tools_menu(repo_root, log)
    result = run_action_menu(
        title="Developer tools",
        choices=choices,
        footer="↑/↓ move  Enter open  number focus  Esc quit",
    )
    if result.cancelled or result.selected_value is None:
        log.emit("[SKIP] Developer tools menu cancelled.")
        return 0
    return _dispatch_dev_tool_action(repo_root, result.selected_value, log=log)


def _dispatch_dev_tool_action(repo_root: Path, action: DevToolAction, *, log: TeeLog) -> int:
    if action.key == "scan":
        return scan_and_cache_tools(repo_root, log=log)
    if action.key == "list":
        return _list_tools(repo_root, log=log)
    if action.key == "doctor":
        return run_workspace_doctor(repo_root, full=False, log=log)
    if action.key == "doctor-full":
        return run_workspace_doctor(repo_root, full=True, log=log)
    if action.key == "validate":
        return validate_build_tools(repo_root, log=log)
    if action.key == "invariants":
        return run_p0_invariant_scan(repo_root, strict_large_files=False, strict_boundaries=False, log=log)
    if action.key == "conformance":
        return run_p1_capability_conformance_scan(repo_root, log=log)
    if action.key == "schema":
        return run_p2_schema_property_scan(repo_root, log=log)
    if action.key == "schema-runtime":
        return run_p21_schema_runtime_scan(repo_root, log=log)
    if action.key == "editor-shell":
        return run_p3_editor_shell_scan(repo_root, log=log)
    if action.key == "import-pipeline":
        return run_p4_import_pipeline_scan(repo_root, log=log)
    if action.key == "world-scene":
        return run_p5_world_scene_save_load_scan(repo_root, log=log)
    if action.key == "gameplay":
        return run_p6_gameplay_foundation_scan(repo_root, log=log)
    if action.key == "rendering":
        return run_p7_rendering_maturity_scan(repo_root, log=log)
    if action.key == "reference-completeness":
        return run_p8_reference_module_completeness_scan(repo_root, log=log)
    if action.key == "reference-completeness-strict":
        return run_p8_reference_module_completeness_scan(repo_root, strict_reference_parity=True, log=log)
    if action.key == "dataset-ingest":
        return dataset_ingest_pipeline(repo_root, log=log)
    if action.key == "dataset-lifecycle":
        return dataset_lifecycle_cleanup(repo_root, log=log)
    if action.key == "dataset-entry-analysis":
        return dataset_entry_value_analysis(repo_root, log=log)
    if action.key == "dataset-maturity":
        return dataset_maturity_command(repo_root, SimpleNamespace(strict=False, no_write=False), log=log)
    if action.key == "dataset-maturity-strict":
        return dataset_maturity_command(repo_root, SimpleNamespace(strict=True, no_write=False), log=log)
    if action.key == "operator-memory":
        return operator_memory_maintenance(repo_root, dry_run=False, log=log)
    if action.key == "import-ui-assets":
        return import_pipeline_command(repo_root, SimpleNamespace(check=False, skip_neui=False, changed_source=[], write_invalidation_plan=False))
    if action.key == "collect-run":
        return collect_run_bundle(repo_root, log=log)
    if action.key == "build":
        return _build_tools(repo_root, tool_id="", release=False, safe=False, validate_after_build=False, log=log)
    if action.key == "build-safe":
        return _build_tools(repo_root, tool_id="", release=False, safe=True, validate_after_build=False, log=log)
    if action.key == "build-safe-validate":
        return _build_tools(repo_root, tool_id="", release=False, safe=True, validate_after_build=True, log=log)
    log.emit(f"[ERROR] Unknown developer tool action: {action.key}")
    return 2


def _list_tools(repo_root: Path, *, log: TeeLog) -> int:
    tools, warnings = discover_tools(repo_root)
    scan_and_cache_tools(repo_root, log=log)
    for tool in tools:
        caps = ", ".join(tool.capabilities) or "-"
        log.emit(f"[TOOL] {tool.id} kind={tool.kind} root={rel(repo_root, tool.root)} caps={caps}")
    return 0 if not warnings else 1


def _build_tools(
    repo_root: Path,
    *,
    tool_id: str,
    release: bool,
    safe: bool,
    validate_after_build: bool,
    log: TeeLog,
) -> int:
    tools, warnings = discover_tools(repo_root)
    if warnings:
        for warning in warnings:
            log.emit(f"[ERROR] {warning}")
        return 1
    selected = tool_id or ""
    if selected:
        tool = tool_by_id(repo_root, selected)
        if tool is None:
            log.emit(f"[ERROR] Unknown tool id: {selected}")
            return 2
        rc = build_tool_descriptor(repo_root, tool, release=release, log=log)
        if rc != 0:
            return rc
        return run_tool_validation(repo_root, tool, release=release, log=log) if validate_after_build else 0
    return build_registered_tools(
        repo_root,
        release=release,
        only_safe=safe,
        validate=validate_after_build,
        log=log,
    )


def _run_tool(repo_root: Path, ns: Any, *, log: TeeLog) -> int:
    tool = tool_by_id(repo_root, ns.tool_id)
    if tool is None:
        log.emit(f"[ERROR] Unknown tool id: {ns.tool_id}")
        return 2
    runnable_kinds = {"rust-cli", "external-cli", "vendor-cli"}
    if tool.kind not in runnable_kinds:
        log.emit(f"[ERROR] Tool is not runnable by this launcher: {tool.id} kind={tool.kind}")
        return 2
    exe = target_exe(tool, bool(ns.release))
    if not exe.exists():
        if tool.kind == "rust-cli":
            rc = build_tool_descriptor(repo_root, tool, release=bool(ns.release), log=log)
            if rc != 0:
                return rc
        else:
            log.emit(f"[ERROR] Tool executable is missing: {tool.id} expected={rel(repo_root, exe)}")
            log.emit("[INFO] Copy the executable payload into the tool package bin/ directory described by tool.json.")
            return 1
    forwarded = list(ns.tool_args or [])
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        forwarded = list(tool.default_args)
    forwarded = expand_tool_args(repo_root, tool, forwarded)
    return run_process([str(exe), *forwarded], cwd=repo_root, log=log)


def tools_command(repo_root: Path, ns: Any) -> int:
    action = ns.tools_action
    if action in {"menu", "scan", "list", "doctor", "validate", "invariants", "conformance", "schema", "schema-runtime", "editor-shell", "import-pipeline", "world-scene", "gameplay", "rendering", "reference-completeness", "reference-completeness-strict", "dataset-ingest", "dataset-lifecycle", "dataset-entry-analysis", "dataset-maturity", "dataset-maturity-strict", "operator-memory", "import-ui-assets", "build", "run", "collect-run"}:
        apply_delete_list(repo_root)
    log = TeeLog()
    if action == "menu":
        return _run_tools_menu(repo_root, log)
    if action == "scan":
        return scan_and_cache_tools(repo_root, log=log)
    if action == "list":
        return _list_tools(repo_root, log=log)
    if action == "doctor":
        return run_workspace_doctor(repo_root, full=bool(getattr(ns, "full", False)), log=log)
    if action == "validate":
        return validate_build_tools(repo_root, log=log)
    if action == "invariants":
        return run_p0_invariant_scan(
            repo_root,
            strict_large_files=bool(getattr(ns, "strict_large_files", False)),
            strict_boundaries=bool(getattr(ns, "strict_boundaries", False)),
            fail_tracked_large_debt=bool(getattr(ns, "fail_tracked_large_debt", False)),
            log=log,
        )
    if action == "conformance":
        return run_p1_capability_conformance_scan(repo_root, log=log)
    if action == "schema":
        return run_p2_schema_property_scan(repo_root, log=log)
    if action == "schema-runtime":
        return run_p21_schema_runtime_scan(repo_root, log=log)
    if action == "editor-shell":
        return run_p3_editor_shell_scan(repo_root, log=log)
    if action == "import-pipeline":
        return run_p4_import_pipeline_scan(repo_root, log=log)
    if action == "world-scene":
        return run_p5_world_scene_save_load_scan(repo_root, log=log)
    if action == "gameplay":
        return run_p6_gameplay_foundation_scan(repo_root, log=log)
    if action == "rendering":
        return run_p7_rendering_maturity_scan(repo_root, log=log)
    if action == "reference-completeness":
        return run_p8_reference_module_completeness_scan(repo_root, log=log)
    if action == "reference-completeness-strict":
        return run_p8_reference_module_completeness_scan(repo_root, strict_reference_parity=True, log=log)
    if action == "dataset-ingest":
        return dataset_ingest_pipeline(repo_root, log=log)
    if action == "dataset-lifecycle":
        return dataset_lifecycle_cleanup(repo_root, log=log)
    if action == "dataset-entry-analysis":
        return dataset_entry_value_analysis(repo_root, log=log)
    if action == "dataset-maturity":
        return dataset_maturity_command(repo_root, SimpleNamespace(strict=False, no_write=False), log=log)
    if action == "dataset-maturity-strict":
        return dataset_maturity_command(repo_root, SimpleNamespace(strict=True, no_write=False), log=log)
    if action == "operator-memory":
        return operator_memory_maintenance(repo_root, dry_run=False, log=log)
    if action == "import-ui-assets":
        return import_pipeline_command(
            repo_root,
            SimpleNamespace(
                check=bool(getattr(ns, "check", False)),
                skip_neui=bool(getattr(ns, "skip_neui", False)),
                changed_source=list(getattr(ns, "changed_source", []) or []),
                write_invalidation_plan=bool(getattr(ns, "write_invalidation_plan", False)),
            ),
        )
    if action == "collect-run":
        return collect_run_bundle(repo_root, log=log)
    if action == "build":
        return _build_tools(
            repo_root,
            tool_id=getattr(ns, "tool_id", "") or "",
            release=bool(ns.release),
            safe=bool(getattr(ns, "safe", False)),
            validate_after_build=bool(getattr(ns, "validate_after_build", False)),
            log=log,
        )
    if action == "run":
        return _run_tool(repo_root, ns, log=log)
    log.emit(f"[ERROR] Unknown tools action: {action}")
    return 2
