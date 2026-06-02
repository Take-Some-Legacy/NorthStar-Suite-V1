from __future__ import annotations

from pathlib import Path

from ..logs import TeeLog
from .cache import scan_and_cache_tools
from .constants import LEGACY_TOOL_IDENTITIES, LEGACY_TOOL_PATHS
from .descriptors import discover_tools
from .legacy_scan import validate_source_for_legacy_tool_identities
from .invariants import run_p0_invariant_scan, run_p1_capability_conformance_scan, run_p2_schema_property_scan, run_p21_schema_runtime_scan, run_p3_editor_shell_scan, run_p4_import_pipeline_scan, run_p5_world_scene_save_load_scan, run_p6_gameplay_foundation_scan, run_p7_rendering_maturity_scan, run_p8_reference_module_completeness_scan, run_p9_dataset_maturity_scan


def _normalized_delete_text(repo_root: Path) -> str:
    delete_list = repo_root / "DELETE_FILES.txt"
    return delete_list.read_text(encoding="utf-8", errors="replace").lower().replace("\\", "/") if delete_list.exists() else ""


def validate_native_tool_surface(repo_root: Path, *, log: TeeLog) -> int:
    code = 0
    delete_text = _normalized_delete_text(repo_root)
    for raw in LEGACY_TOOL_PATHS:
        path = repo_root / raw
        if path.exists():
            if raw.lower().replace("\\", "/") in delete_text:
                log.emit(f"[WARN] Legacy tool path still exists but is scheduled for deletion: {raw}")
            else:
                log.emit(f"[WARN] Legacy tool path still exists and will be ignored by the native registry: {raw}")
    tools, warnings = discover_tools(repo_root)
    if warnings:
        for warning in warnings:
            log.emit(f"[ERROR] Tool descriptor warning: {warning}")
        code = 1
    if not tools:
        log.emit("[ERROR] No native tool descriptors found under tools/.")
        code = 1
    build_validators = [t for t in tools if t.build_validation]
    if not build_validators:
        log.emit("[ERROR] No native build validation tool is registered.")
        code = 1
    for tool in tools:
        if tool.kind == "rust-cli" and (tool.cargo_manifest is None or not tool.cargo_manifest.exists()):
            log.emit(f"[ERROR] Rust tool manifest missing for {tool.id}: {tool.cargo_manifest}")
            code = 1
        if tool.kind == "binary" and tool.safe_for_build:
            log.emit(f"[ERROR] Binary-only tool cannot be safe_for_build: {tool.id}")
            code = 1
        if tool.build_validation and not tool.validation_args and not tool.default_args:
            log.emit(f"[WARN] Build validation tool has no validation_args/default_args; fallback doctor will be used: {tool.id}")
        lowered_identity = tool.id.lower().replace(".", "").replace("-", "").replace("_", "")
        if lowered_identity in LEGACY_TOOL_IDENTITIES or any(lowered_identity.endswith(identity) for identity in LEGACY_TOOL_IDENTITIES):
            log.emit(f"[ERROR] Tool id resurrects legacy identity: {tool.id}")
            code = 1
    if code == 0:
        log.emit(f"[OK] Native tool surface valid: {len(tools)} descriptor(s), {len(build_validators)} build validator(s).")
    return code


def validate_build_tools(repo_root: Path, *, log: TeeLog | None = None) -> int:
    """Run the plugin-build preflight without blocking on roadmap diagnostics.

    This is intentionally narrower than architecture maturity scans. It blocks
    broken native tool descriptors and Doctor checks marked ERROR/blocking;
    roadmap/P0 warnings stay visible but do not stop dev plugin rebuilds.
    """

    own_log = log or TeeLog()
    own_log.emit("[CHECK] Build preflight: native tool surface + blocking Workspace Doctor diagnostics")
    tool_code = validate_native_tool_surface(repo_root, log=own_log)
    legacy_code = validate_legacy_tool_identity_absent(repo_root, log=own_log)

    from .doctor import run_workspace_doctor

    doctor_code = run_workspace_doctor(repo_root, full=True, log=own_log)

    if tool_code or legacy_code or doctor_code:
        own_log.emit("[ERROR] Build preflight found blocking diagnostics.")
        own_log.emit("[NEXT] Run tools.doctor.full, fix checks marked ERROR/blocking, then run workspace.clean.full and build.plugins.force.dev.")
    else:
        own_log.emit("[OK] Build preflight passed; non-blocking Doctor warnings do not stop plugin rebuild.")
    return tool_code or legacy_code or doctor_code
