from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from ..build_info import record_build_info
from ..cargo import (
    cargo_exe,
    candidate_built_dlls,
    cargo_target_dir,
    cleanup_old_stamps,
    cleanup_old_versions,
    fingerprint_workspace,
    select_runtime_crate,
    stamp_matches,
    stamp_path,
    write_stamp,
)
from ..logs import TeeLog, run_process
from ..paths import rel
from ..platforms import BuildPlatform, cargo_profile_dir, cargo_target_args, normalize_build_platform
from .install import cleanup_winit_platform_alias


LEGACY_INSTALL_STEM_ALIASES: dict[str, tuple[str, ...]] = {
    # Previous short/route/package names. Keeping these files beside the new
    # implementation-purpose DLLs can make discovery select an old ABI binary
    # with the same provider route and crash the process before Rust can report
    # a clean plugin error.
    "engine-ui-aurelia": ("aurelia", "engine.ui.aurelia", "engine-ui-aurelia"),
    "engine-render-vulkan": ("vulkan", "engine.render.vulkan", "engine-render-vulkan"),
    "engine-assets-starvault": ("starvault", "engine.assets.starvault", "engine-assets-starvault", "assetManager", "newengine-AssetManager"),
    "engine-input-compass": ("compass", "engine.input.compass", "engine-input-compass"),
    "engine-ecs-constellation": ("constellation", "engine.ecs.constellation", "engine-ecs-constellation"),
    "engine-physics-gravitas": ("gravitas", "engine.physics.gravitas", "engine-physics-gravitas"),
    "engine-logging-chronicle": ("chronicle", "engine.logging.chronicle", "engine-logging-chronicle"),
    "engine-profiler-starprofiler": ("starprofiler", "starProfiler", "engine.profiler.starprofiler", "engine-profiler-starprofiler"),
    "engine-platform-winit": ("winit", "platform-winit", "winit-platform-plugin", "engine.platform.winit", "engine-platform-winit"),
}


def cleanup_install_aliases(out_dir: Path, package_name: str, install_stem: str, keep: str, log: TeeLog, *, library_ext: str) -> None:
    aliases = set(LEGACY_INSTALL_STEM_ALIASES.get(package_name, ()))
    aliases.add(package_name)
    aliases.discard(install_stem)
    for alias in sorted(aliases, key=str.lower):
        cleanup_old_versions(out_dir, alias, keep, log, library_ext=library_ext)


def install_runtime_dll(root: Path, *, built_dll: Path, output_dll: Path, log: TeeLog) -> bool:
    """Install a DLL without leaking Python tracebacks on locked runtime files.

    Windows keeps loaded DLLs locked. That is an operational state, not a script
    crash: report it clearly and keep the console/log useful.
    """
    output_dll.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dll.with_name(f"{output_dll.name}.installing")
    try:
        if staging.exists():
            staging.unlink()
        shutil.copyfile(built_dll, staging)
        os.replace(staging, output_dll)
        return True
    except PermissionError as exc:
        log.emit(f"[ERROR] Runtime DLL is locked and cannot be replaced: {output_dll}")
        log.emit("[ERROR] Close the running game/editor/runtime that loaded this DLL, then run buildPlugins again.")
        log.emit(f"[ERROR] Windows reported: {exc}")
        try:
            if staging.exists():
                staging.unlink()
        except OSError:
            log.emit(f"[WARN] Could not remove staging DLL after failed install: {rel(root, staging)}")
        return False
    except OSError as exc:
        log.emit(f"[ERROR] Failed to install DLL {rel(root, built_dll)} -> {output_dll}: {exc}")
        try:
            if staging.exists():
                staging.unlink()
        except OSError:
            log.emit(f"[WARN] Could not remove staging DLL after failed install: {rel(root, staging)}")
        return False


def sync_workspace(root: Path, *, display_name: str, workspace_dir: Path, out_dir: Path, kind: str, build_type: str, force: bool, log: TeeLog, records: list[dict] | None = None, target_log: Path | None = None, platform: BuildPlatform | None = None) -> int:
    if target_log is not None:
        with log.scoped_file(target_log):
            log.emit(f"[LOG] per-target build log for {display_name}")
            return sync_workspace(
                root,
                display_name=display_name,
                workspace_dir=workspace_dir,
                out_dir=out_dir,
                kind=kind,
                build_type=build_type,
                force=force,
                log=log,
                records=records,
                target_log=None,
                platform=platform,
            )

    started = time.perf_counter()
    platform = platform or normalize_build_platform(None)
    try:
        meta = select_runtime_crate(workspace_dir)
    except Exception as exc:
        severity = "WARN" if kind == "codec-worker" else "ERROR"
        log.emit(f"[{severity}] Failed to read package metadata for {display_name}: {exc}")
        code = 0 if kind == "codec-worker" else 1
        record_build_info(
            records,
            display_name=display_name,
            kind=kind,
            package_name="<metadata-unavailable>",
            version="",
            build_type=build_type,
            platform=platform.id,
            rust_target=platform.rust_target or "",
            status="skipped" if code == 0 else "failed",
            validity="invalid",
            validity_reason=str(exc),
            workspace=rel(root, workspace_dir),
            manifest=rel(root, workspace_dir / "Cargo.toml"),
            expected_path="",
            installed_path="",
            built_from="",
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return code

    install_stem = meta.runtime_install_stem
    canonical_dll = f"{install_stem}-{meta.version}-{build_type}{platform.library_ext}"
    output_dll = out_dir / canonical_dll
    target_profile = cargo_profile_dir(build_type, platform)
    cargo_args = [cargo_exe() or "cargo", "build", "--manifest-path", str(meta.cargo_toml), *cargo_target_args(platform)]
    if build_type == "release":
        cargo_args.append("--release")

    log.emit("")
    log.emit(f"[INFO] Plugin package: {meta.package_name} {meta.version}")
    if install_stem != meta.package_name:
        log.emit(f"[INFO] Runtime provider route/install identity: {install_stem}")
    log.emit(f"[INFO] Plugin package manifest: {meta.cargo_toml}")
    log.emit(f"[INFO] Syncing {display_name} as {canonical_dll}")
    log.emit(f"[INFO] Workspace: {rel(root, workspace_dir)}")
    log.emit(f"[CHECK] Inspecting build inputs for {display_name}")

    initial_fp = fingerprint_workspace(workspace_dir)
    spath = stamp_path(root, kind, display_name, canonical_dll, platform_id=platform.id)
    log.emit(f"[STATE] Build stamp: {rel(root, spath)}")
    needs_rebuild = force or not stamp_matches(spath, fingerprint=initial_fp, output_dll=output_dll, build_type=build_type, package_name=meta.package_name, version=meta.version, platform_id=platform.id, rust_target=platform.rust_target or "")
    if force:
        log.emit(f"[STALE] {display_name}: forced by NEWENGINE_FORCE_PLUGIN_REBUILD=1 / --force")
    elif not needs_rebuild:
        cleanup_old_versions(out_dir, install_stem, canonical_dll, log, library_ext=platform.library_ext)
        cleanup_install_aliases(out_dir, meta.package_name, install_stem, canonical_dll, log, library_ext=platform.library_ext)
        cleanup_old_stamps(root, kind, display_name, spath, log, platform_id=platform.id)
        if platform.host and display_name.lower() == "winit-platform-plugin":
            cleanup_winit_platform_alias(root, log)
        log.emit(f"[SKIP] {display_name} is up-to-date")
        record_build_info(
            records,
            display_name=display_name,
            kind=kind,
            package_name=meta.package_name,
            version=meta.version,
            build_type=build_type,
            platform=platform.id,
            rust_target=platform.rust_target or "",
            status="skipped",
            validity="valid" if output_dll.exists() else "invalid",
            validity_reason="stamp matched installed artifact" if output_dll.exists() else "stamp matched but installed artifact is missing",
            workspace=rel(root, workspace_dir),
            manifest=rel(root, meta.cargo_toml),
            expected_path=rel(root, output_dll),
            installed_path=rel(root, output_dll) if output_dll.exists() else "",
            built_from="",
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return 0
    log.emit(f"[BUILD] {display_name} is missing or stale")

    env = os.environ.copy()
    env["NEWENGINE_PLUGIN_BUILD_TYPE"] = build_type
    env["NORTHSTAR_PLUGIN_INSTALL_NAME"] = install_stem
    env["NEWENGINE_BUILD_PLATFORM"] = platform.id
    env["NEWENGINE_PLUGIN_BUILD_PLATFORM"] = platform.id
    if platform.rust_target:
        env["NEWENGINE_RUST_TARGET"] = platform.rust_target
    env.setdefault("CARGO_TERM_COLOR", "never")
    code = run_process(cargo_args, cwd=workspace_dir, log=log, env=env)
    if code != 0:
        log.emit(f"[ERROR] Build failed for {display_name} with exit code {code}")
        record_build_info(
            records,
            display_name=display_name,
            kind=kind,
            package_name=meta.package_name,
            version=meta.version,
            build_type=build_type,
            platform=platform.id,
            rust_target=platform.rust_target or "",
            status="failed",
            validity="invalid",
            validity_reason=f"cargo build exited with {code}",
            workspace=rel(root, workspace_dir),
            manifest=rel(root, meta.cargo_toml),
            expected_path=rel(root, output_dll),
            installed_path="",
            built_from="",
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return code

    target_dir = cargo_target_dir(meta, workspace_dir, log)
    build_script_output_stem = f"{meta.package_name}-{meta.version}-{build_type}"
    install_script_output_stem = f"{install_stem}-{meta.version}-{build_type}"
    exact_names = [canonical_dll]
    if build_type == "dev":
        exact_names.append(f"{install_stem}-{meta.version}-debug{platform.library_ext}")
        exact_names.append(f"{meta.package_name}-{meta.version}-debug{platform.library_ext}")
    built_candidates = candidate_built_dlls(
        target_dir,
        target_profile,
        [meta.cargo_output_stem, build_script_output_stem, install_script_output_stem],
        exact_names=exact_names,
        extra_dirs=[workspace_dir, meta.crate_dir],
        library_ext=platform.library_ext,
    )
    if not built_candidates:
        log.emit(f"[ERROR] Built DLL not found for {display_name} under {target_dir / target_profile}")
        log.emit(f"[ERROR] Cargo lib name expected: {meta.cargo_output_stem}{platform.library_ext}")
        log.emit(f"[ERROR] Plugin build-script name expected: {canonical_dll}")
        log.emit(f"[ERROR] Package install name expected: {canonical_dll}")
        if install_stem != meta.package_name:
            log.emit(f"[ERROR] Provider route/install stem expected: {install_stem}")
        record_build_info(
            records,
            display_name=display_name,
            kind=kind,
            package_name=meta.package_name,
            version=meta.version,
            build_type=build_type,
            platform=platform.id,
            rust_target=platform.rust_target or "",
            status="failed",
            validity="invalid",
            validity_reason="cargo succeeded but expected DLL was not found",
            workspace=rel(root, workspace_dir),
            manifest=rel(root, meta.cargo_toml),
            expected_path=rel(root, output_dll),
            installed_path="",
            built_from="",
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return 1
    built_dll = built_candidates[0]
    log.emit(f"[INSTALL] Copying {rel(root, built_dll)} -> {output_dll}")
    if not install_runtime_dll(root, built_dll=built_dll, output_dll=output_dll, log=log):
        record_build_info(
            records,
            display_name=display_name,
            kind=kind,
            package_name=meta.package_name,
            version=meta.version,
            build_type=build_type,
            platform=platform.id,
            rust_target=platform.rust_target or "",
            status="failed",
            validity="invalid",
            validity_reason="install failed; runtime DLL is likely locked by a running process",
            workspace=rel(root, workspace_dir),
            manifest=rel(root, meta.cargo_toml),
            expected_path=rel(root, output_dll),
            installed_path=rel(root, output_dll) if output_dll.exists() else "",
            built_from=rel(root, built_dll),
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )
        return 1
    final_fp = fingerprint_workspace(workspace_dir)
    if final_fp != initial_fp:
        log.emit("[STATE] Build inputs changed during Cargo build; stamp uses post-build fingerprint")
    write_stamp(spath, fingerprint=final_fp, output_dll=output_dll, build_type=build_type, package_name=meta.package_name, version=meta.version, kind=kind, display_name=display_name, platform_id=platform.id, rust_target=platform.rust_target or "")
    log.emit(f"[OK] Build stamp updated: {rel(root, spath)}")
    cleanup_old_versions(out_dir, install_stem, canonical_dll, log, library_ext=platform.library_ext)
    cleanup_install_aliases(out_dir, meta.package_name, install_stem, canonical_dll, log, library_ext=platform.library_ext)
    cleanup_old_stamps(root, kind, display_name, spath, log, platform_id=platform.id)
    if platform.host and display_name.lower() == "winit-platform-plugin":
        cleanup_winit_platform_alias(root, log)
    log.emit(f"[OK] Installed {output_dll}")
    record_build_info(
        records,
        display_name=display_name,
        kind=kind,
        package_name=meta.package_name,
        version=meta.version,
        build_type=build_type,
        platform=platform.id,
        rust_target=platform.rust_target or "",
        status="built",
        validity="valid" if output_dll.exists() else "invalid",
        validity_reason="installed artifact exists" if output_dll.exists() else "install copy did not produce artifact",
        workspace=rel(root, workspace_dir),
        manifest=rel(root, meta.cargo_toml),
        expected_path=rel(root, output_dll),
        installed_path=rel(root, output_dll) if output_dll.exists() else "",
        built_from=rel(root, built_dll),
        elapsed_ms=round((time.perf_counter() - started) * 1000.0, 3),
    )
    return 0
