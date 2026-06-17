from __future__ import annotations

from pathlib import Path

from ..build_info import build_log_dir, write_plugin_target_log_archive
from ..cargo import codec_enabled, read_text
from ..console import colorize_script_line
from ..logs import TeeLog, pause_on_error
from ..incidents import emit_incident_console_lines, write_incident_bundle
from ..migration import apply_delete_list
from ..paths import engine_core_root, now_stamp, plugins_root, rel, utc_iso
from ..progress import progress_configure, progress_update
from ..selection import exclusive_choice_kind, split_choice_tokens, unique_casefolded
from ..tools import validate_build_tools
from .args import normalize_plugin_entry_args, parse_build_plugin_args
from .install import cleanup_deprecated_artifacts
from .interactive import prompt_for_build_platform, prompt_for_build_type, prompt_for_plugin_target
from .manifest import discover_plugin_names, ensure_dirs, manifest, root_last_build_log_name
from .reports import write_report_block
from .sync import sync_workspace
from ..platforms import normalize_build_platform, platform_artifact_root
from ..plugin_status import collect_plugin_status, write_plugin_status_report




def _split_build_selection(raw: str | None) -> list[str] | None:
    tokens = split_choice_tokens(raw)
    if not tokens:
        return None
    special = exclusive_choice_kind(
        tokens,
        all_tokens={"0", "all", "*"},
        all_error="all/0 cannot be mixed with explicit build targets",
    )
    if special == "all":
        return None
    return unique_casefolded(tokens)


def _resolve_build_targets(raw: str | None, *, plugins: list[str], codec_workers: list[str], root: Path) -> list[str] | None:
    tokens = _split_build_selection(raw)
    if tokens is None:
        return None

    resolved: list[str] = []
    seen: set[str] = set()
    plugins_by_lower = {p.lower(): p for p in plugins}
    codec_workers_by_lower = {w.lower(): w for w in codec_workers}

    for token in tokens:
        low = token.lower()
        if token.isdigit():
            index = int(token)
            if not 1 <= index <= len(plugins):
                raise ValueError(f"Plugin selection index is out of range: {token}")
            name = plugins[index - 1]
        elif low in plugins_by_lower:
            name = plugins_by_lower[low]
        elif low in codec_workers_by_lower:
            name = codec_workers_by_lower[low]
        elif (plugins_root(root) / "AssetManager" / "codecs" / token / "Cargo.toml").exists():
            name = token
        else:
            name = token
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(name)
    return resolved


def _safe_build_error_name(name: str | None) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(name or "build").strip())
    return safe.strip("-._") or "build"


def _build_error_log_path(root: Path, name: str | None) -> Path:
    return root / f"buildERR-{_safe_build_error_name(name)}.log"


def _attach_build_error_log(root: Path, log: TeeLog, *, failed_name: str | None, code: int) -> Path:
    path = _build_error_log_path(root, failed_name)
    log.add_copy_target(path)
    log.emit(f"[ERROR] Build error mirror: {rel(root, path)}")
    log.emit(f"[ERROR] Failed build target: {_safe_build_error_name(failed_name)} exit_code={code}")
    return path

def build_plugins(root: Path, args: list[str], *, pause: bool = True) -> int:
    apply_delete_list(root)
    args = prompt_for_build_platform(args)
    args = prompt_for_build_type(args)
    try:
        args = prompt_for_plugin_target(root, args)
        parsed = parse_build_plugin_args(args)
        selected = parsed.selected
        build_type = parsed.build_type
        platform = parsed.platform
        force = parsed.force
    except ValueError as exc:
        print(colorize_script_line(f"[ERROR] {exc}"))
        return 2
    if selected == "__help__":
        print(colorize_script_line("[INFO] Usage: suite.bat -> Building -> Build plugins, or takesome.py build-plugins [PluginName|PluginA,PluginB|1,3] [--platform windows-x64-msvc|linux-x64-gnu|macos-arm64] [dev|debug|release] [--force]"))
        print(colorize_script_line("[INFO] Without PluginName, interactive shells show build type and plugin target menus. Use comma-list by name for multiple targets, e.g. AssetManager,ProfilerPlugin."))
        return 0

    ensure_dirs(root)
    run_stamp = now_stamp()
    started_utc = utc_iso()
    records: list[dict] = []
    build_root = build_log_dir(root)
    current_log = build_root / f"plugin-sync-{run_stamp}.log"
    latest_log = build_root / "plugin-sync-latest.log"
    root_last_log = root / root_last_build_log_name(selected)
    target_log_dir = build_root / f"plugin-sync-{run_stamp}-items"
    target_log_paths: list[Path] = []
    failed_build_name: str | None = None
    error_log_path: Path | None = None
    finished_utc = ""

    def target_log_path(kind: str, name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in name.strip())
        safe = safe.strip("-._") or "target"
        path = target_log_dir / f"{kind}-{safe}.log"
        target_log_paths.append(path)
        return path

    code = 0
    with TeeLog(current_log, latest_log, root_last_log) as log:
        try:
            log.emit("[LOG] North Star / Take Some plugin build log")
            log.emit(f"[LOG] started_utc={started_utc}")
            log.emit(f"[LOG] cwd={root}")
            log.emit("[LOG] script=python -m noesis suite build-plugins")
            log.emit(f"[LOG] args={' '.join(args)}")
            log.emit("[LOG] stream=live stdout+stderr")
            log.emit(f"[INFO] Plugin build log: {rel(root, current_log)}")
            log.emit(f"[INFO] BuildLog root: {rel(root, build_root)}")
            log.emit(f"[INFO] Root last build log: {rel(root, root_last_log)}")

            engine_root = engine_core_root(root)
            if not (engine_root / "Cargo.toml").exists():
                log.emit(f"[ERROR] NewEngine root not found: {engine_root}")
                code = 1
                failed_build_name = "suite-preflight"
            else:
                cleanup_deprecated_artifacts(root, log)
                log.emit("[CHECK] Native tool registry validation only; plugin build does not compile tools")
                tool_validation_code = validate_build_tools(root, log=log)
                if tool_validation_code != 0:
                    code = tool_validation_code
                    failed_build_name = "tool-registry-validation"
                else:
                    m = manifest(root)
                    plugins = discover_plugin_names(root)
                    codec_workers = list(m.get("codecWorkers", []))
                    plugins_by_lower = {p.lower(): p for p in plugins}
                    codec_workers_by_lower = {w.lower(): w for w in codec_workers}
                    from ..platforms import platform_artifact_root
                    plugin_out = platform_artifact_root(root, platform)
                    log.emit(f"[INFO] Build platform: {platform.id} ({platform.label})")
                    log.emit(f"[INFO] Rust target: {platform.rust_target or 'host default'}")
                    log.emit(f"[INFO] Artifact extension: {platform.library_ext}")

                    def sync_codec(name: str) -> int:
                        nonlocal failed_build_name
                        workspace = plugins_root(root) / "AssetManager" / "codecs" / name
                        if not (workspace / "Cargo.toml").exists():
                            log.emit(f"[WARN] AssetManager codec worker source not found, keeping existing binaries: {name}")
                            return 0
                        text = read_text(workspace / "Cargo.toml")
                        if not codec_enabled(text):
                            log.emit(f"[SKIP] {name} is marked package.metadata.newengine.codec.enabled=false")
                            return 0
                        rc = sync_workspace(root, display_name=name, workspace_dir=workspace, out_dir=plugin_out / "codecs", kind="codec-worker", build_type=build_type, platform=platform, force=force, log=log, records=records, target_log=target_log_path("codec", name))
                        if rc != 0:
                            failed_build_name = name
                        return rc

                    def sync_asset_codecs() -> int:
                        nonlocal failed_build_name
                        log.emit("[INFO] AssetManager selected: syncing required codec workers")
                        for worker in codec_workers:
                            rc = sync_codec(worker)
                            if rc != 0:
                                failed_build_name = failed_build_name or worker
                                return rc
                        return 0

                    def sync_plugin(name: str) -> int:
                        nonlocal failed_build_name
                        workspace = plugins_root(root) / name
                        if not (workspace / "Cargo.toml").exists():
                            log.emit(f"[ERROR] Plugin workspace not found: {rel(root, workspace)}")
                            failed_build_name = name
                            return 1
                        rc = sync_workspace(root, display_name=name, workspace_dir=workspace, out_dir=plugin_out, kind="plugin", build_type=build_type, platform=platform, force=force, log=log, records=records, target_log=target_log_path("plugin", name))
                        if rc != 0:
                            failed_build_name = name
                        if rc == 0 and name.lower() == "assetmanager":
                            rc = sync_asset_codecs()
                        return rc

                    try:
                        selected_targets = _resolve_build_targets(selected, plugins=plugins, codec_workers=codec_workers, root=root)
                    except ValueError as exc:
                        log.emit(f"[ERROR] {exc}")
                        code = 2
                        failed_build_name = "target-selection"
                        selected_targets = []

                    def sync_named_target(name: str) -> int:
                        selected_worker = codec_workers_by_lower.get(name.lower(), name)
                        selected_plugin = plugins_by_lower.get(name.lower(), name)
                        if name.lower() in codec_workers_by_lower or (plugins_root(root) / "AssetManager" / "codecs" / name / "Cargo.toml").exists():
                            return sync_codec(selected_worker)
                        if name.lower() not in plugins_by_lower:
                            log.emit(f"[WARN] Selected plugin is not listed in Plugins/build_manifest.json; trying workspace path anyway: {name}")
                        return sync_plugin(selected_plugin)

                    if code == 0 and selected_targets is None:
                        build_plan = [*plugins, *codec_workers]
                        progress_configure(total=max(1, len(build_plan)), current=0, unit="target", phase="build plan resolved")
                        completed_targets = 0
                        for name in plugins:
                            progress_update(current=completed_targets, phase=f"building plugin {name}")
                            code = sync_plugin(name)
                            completed_targets += 1
                            progress_update(current=completed_targets, phase=f"finished plugin {name}")
                            if code != 0:
                                break
                        if code == 0:
                            for worker in codec_workers:
                                progress_update(current=completed_targets, phase=f"building codec {worker}")
                                code = sync_codec(worker)
                                completed_targets += 1
                                progress_update(current=completed_targets, phase=f"finished codec {worker}")
                                if code != 0:
                                    break
                    elif code == 0:
                        log.emit(f"[INFO] Build target selection: {len(selected_targets)} item(s): {', '.join(selected_targets)}")
                        progress_configure(total=max(1, len(selected_targets)), current=0, unit="target", phase="build target selection resolved")
                        for index, name in enumerate(selected_targets, start=1):
                            progress_update(current=index - 1, phase=f"building target {name}")
                            code = sync_named_target(name)
                            progress_update(current=index, phase=f"finished target {name}")
                            if code != 0:
                                break

                    if code == 0:
                        log.emit(f"[OK] Runtime plugin sync completed: {build_type}")
                        log.emit(f"[OK] Runtime plugin dir: {plugin_out}")
        finally:
            finished_utc = utc_iso()
            log_archive = write_plugin_target_log_archive(root, run_stamp=run_stamp, target_logs=target_log_paths)
            if log_archive is not None:
                log.emit(f"[INFO] Per-target build logs archive: {rel(root, log_archive)}")
            write_report_block(
                root,
                log=log,
                run_stamp=run_stamp,
                started_utc=started_utc,
                finished_utc=finished_utc,
                args=args,
                build_type=build_type,
                exit_code=code,
                records=records,
                current_log=current_log,
                latest_log=latest_log,
                root_last_log=root_last_log,
                log_archive=log_archive,
            )
            try:
                status = collect_plugin_status(root, build_type=build_type, platform_id=platform.id)
                status_json, status_md = write_plugin_status_report(root, status)
                summary = status.get("summary", {})
                log.emit(
                    "[INFO] Plugin status: "
                    f"up_to_date={summary.get('up_to_date', 0)} "
                    f"need_rebuild={summary.get('need_rebuild', 0)} "
                    f"report={rel(root, status_md)}"
                )
                log.emit(f"[INFO] Plugin status registry: {rel(root, status_json)}")
            except Exception as exc:
                log.emit(f"[WARN] Failed to write plugin status registry: {exc}")
            log.emit(f"[LOG] finished_utc={finished_utc}")
            log.emit(f"[LOG] exit_code={code}")
            log.emit(f"[INFO] Latest plugin build log: {rel(root, latest_log)}")
            log.emit(f"[INFO] Root last build log: {rel(root, root_last_log)}")
            if code != 0:
                error_log_path = _attach_build_error_log(root, log, failed_name=failed_build_name or selected or "plugin-sync", code=code)
    if code != 0:
        incident = write_incident_bundle(
            root,
            kind="build",
            target=failed_build_name or selected or "plugin-sync",
            exit_code=code,
            primary_log=current_log,
            error_log=error_log_path,
            message="Plugin build failed",
            command=f"takesome.py build-plugins {' '.join(args)}",
            started_utc=started_utc,
            finished_utc=finished_utc,
            extra={"build_type": build_type, "selected": selected, "platform": platform.id},
        )
        emit_incident_console_lines(root, incident, label="Build")
    if pause:
        pause_on_error(code, context="Plugin sync")
    return code


def build_plugin_entry(root: Path, plugin_dir: Path, entry: str, args: list[str]) -> int:
    plugin_name = plugin_dir.resolve().name
    profile_from_entry = {
        "builddev": "dev",
        "builddebug": "debug",
        "buildrelease": "release",
    }.get(entry.lower())
    forwarded = [plugin_name]
    if profile_from_entry:
        forwarded.append(profile_from_entry)
    forwarded.extend(normalize_plugin_entry_args(plugin_dir, entry, args))
    return build_plugins(root, forwarded)


def build_codecs(root: Path, args: list[str]) -> int:
    apply_delete_list(root)
    build_type = "release"
    platform = normalize_build_platform(None)
    force = False
    index = 0
    while index < len(args):
        arg = args[index]
        low = arg.lower()
        if low in {"dev", "debug", "release"}:
            build_type = low
        elif low in {"--force", "-f"}:
            force = True
        elif low in {"--platform", "--build-platform", "--target", "--rust-target"}:
            if index + 1 >= len(args):
                print(colorize_script_line(f"[ERROR] {arg} expects a platform value"))
                return 2
            platform = normalize_build_platform(args[index + 1])
            index += 1
        elif low.startswith(("--platform=", "--build-platform=", "--target=", "--rust-target=")):
            platform = normalize_build_platform(arg.split("=", 1)[1])
        elif low in {"help", "--help", "-h"}:
            print(colorize_script_line("[INFO] Usage: buildAllCodecs.cmd [dev|debug|release] [--platform <id|target>] [--force]"))
            return 0
        else:
            print(colorize_script_line(f"[ERROR] Unknown codec build argument: {arg}"))
            return 2
        index += 1
    ensure_dirs(root)
    run_stamp = now_stamp()
    started_utc = utc_iso()
    records: list[dict] = []
    build_root = build_log_dir(root)
    current_log = build_root / f"codec-sync-{run_stamp}.log"
    latest_log = build_root / "codec-sync-latest.log"
    root_last_log = root / "lastbuild-codecs.log"
    target_log_dir = build_root / f"codec-sync-{run_stamp}-items"
    target_log_paths: list[Path] = []
    failed_build_name: str | None = None
    error_log_path: Path | None = None
    finished_utc = ""

    def target_log_path(name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in name.strip())
        safe = safe.strip("-._") or "codec"
        path = target_log_dir / f"codec-{safe}.log"
        target_log_paths.append(path)
        return path

    code = 0
    with TeeLog(current_log, latest_log, root_last_log) as log:
        try:
            log.emit("[LOG] North Star codec worker build log")
            log.emit(f"[LOG] started_utc={started_utc}")
            log.emit("[LOG] script=python -m noesis suite build-codecs")
            log.emit(f"[LOG] args={' '.join(args)}")
            log.emit(f"[INFO] Codec build log: {rel(root, current_log)}")
            workers = list(manifest(root).get("codecWorkers", []))
            if not workers:
                log.emit("[WARN] No codecWorkers listed in Plugins/build_manifest.json")
                code = 0
            else:
                out_dir = platform_artifact_root(root, platform) / "codecs"
                log.emit(f"[INFO] Build platform: {platform.id} ({platform.label})")
                log.emit(f"[INFO] Rust target: {platform.rust_target or 'host default'}")
                progress_configure(total=max(1, len(workers)), current=0, unit="codec", phase="codec build plan resolved")
                for index, worker in enumerate(workers, start=1):
                    progress_update(current=index - 1, phase=f"building codec {worker}")
                    workspace = plugins_root(root) / "AssetManager" / "codecs" / worker
                    if not (workspace / "Cargo.toml").exists():
                        log.emit(f"[WARN] AssetManager codec worker source not found, keeping existing binaries: {worker}")
                        continue
                    text = read_text(workspace / "Cargo.toml")
                    if not codec_enabled(text):
                        log.emit(f"[SKIP] {worker} is marked package.metadata.newengine.codec.enabled=false")
                        continue
                    code = sync_workspace(
                        root,
                        display_name=worker,
                        workspace_dir=workspace,
                        out_dir=out_dir,
                        kind="codec-worker",
                        build_type=build_type,
                        force=force,
                        log=log,
                        records=records,
                        target_log=target_log_path(worker),
                        platform=platform,
                    )
                    progress_update(current=index, phase=f"finished codec {worker}")
                    if code != 0:
                        failed_build_name = worker
                        break
                if code == 0:
                    log.emit(f"[OK] Codec workers synced: {build_type}")
        finally:
            finished_utc = utc_iso()
            log_archive = write_plugin_target_log_archive(root, run_stamp=run_stamp, target_logs=target_log_paths)
            if log_archive is not None:
                log.emit(f"[INFO] Per-codec build logs archive: {rel(root, log_archive)}")
            write_report_block(
                root,
                log=log,
                run_stamp=run_stamp,
                started_utc=started_utc,
                finished_utc=finished_utc,
                args=["build-codecs", *args],
                build_type=build_type,
                exit_code=code,
                records=records,
                current_log=current_log,
                latest_log=latest_log,
                root_last_log=root_last_log,
                log_archive=log_archive,
            )
            log.emit(f"[LOG] finished_utc={finished_utc}")
            log.emit(f"[LOG] exit_code={code}")
            log.emit(f"[INFO] Latest codec build log: {rel(root, latest_log)}")
            if code != 0:
                error_log_path = _attach_build_error_log(root, log, failed_name=failed_build_name or "codecs", code=code)
    if code != 0:
        incident = write_incident_bundle(
            root,
            kind="build",
            target=failed_build_name or "codecs",
            exit_code=code,
            primary_log=current_log,
            error_log=error_log_path,
            message="Codec build failed",
            command=f"takesome.py build-codecs {' '.join(args)}",
            started_utc=started_utc,
            finished_utc=finished_utc,
            extra={"build_type": build_type, "platform": platform.id},
        )
        emit_incident_console_lines(root, incident, label="Build")
    return code
