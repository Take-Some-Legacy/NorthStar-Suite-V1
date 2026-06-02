from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .build_info import build_log_dir
from .logs import TeeLog, pause_on_error, run_process, quote_for_log
from .migration import apply_delete_list
from .paths import now_stamp, rel, utc_iso
from .progress import progress_configure, progress_update
from .plugin_build import build_plugins
from .incidents import emit_incident_console_lines, safe_incident_name, write_incident_bundle
from .plugin_status import collect_plugin_status, stale_sync_targets, write_plugin_status_report
from .cargo.process import cargo_exe

_GAME_BIN = "game-ready-fps"
_VALID_RUN_PROFILES = {"dev", "debug", "release"}
_PLUGIN_SYNC_FLAGS = {"--sync-plugins", "--force-plugins", "--no-plugin-sync", "--check-plugins-only"}


def _explicit_profile_from_args(args: list[str]) -> str | None:
    for arg in args:
        low = arg.lower()
        if low in _VALID_RUN_PROFILES:
            return low
    return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _exit_code_is_zero(value: Any) -> bool:
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return False


def _latest_successful_plugin_build_profile(root: Path) -> str | None:
    """Return the latest successful plugin build type recorded by the suite.

    This is the authoritative default for runGame when the user did not pass an
    explicit profile. It prevents the runtime launcher from rebuilding dev
    plugins after the current workspace plugin set was intentionally built as
    release/debug.
    """
    latest = _read_json(build_log_dir(root) / "plugin-build-latest.json")
    build_type = str(latest.get("build_type", "")).lower()
    if build_type in _VALID_RUN_PROFILES and _exit_code_is_zero(latest.get("exit_code")):
        return build_type

    build_info = _read_json(build_log_dir(root) / "buildInfo.json")
    latest_run = build_info.get("latest")
    if isinstance(latest_run, dict):
        build_type = str(latest_run.get("build_type", "")).lower()
        if build_type in _VALID_RUN_PROFILES and _exit_code_is_zero(latest_run.get("exit_code")):
            return build_type
    return None


def _artifact_mtime(root: Path, status: dict[str, Any]) -> float:
    latest = 0.0
    for record in status.get("records", []):
        if record.get("status_key") != "up_to_date":
            continue
        artifact = str(record.get("artifact", ""))
        if not artifact:
            continue
        path = root / artifact
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def _best_current_plugin_profile(root: Path) -> str | None:
    """Infer the current plugin profile from up-to-date installed artifacts."""
    candidates: list[tuple[float, int, str]] = []
    # Prefer the newest complete installed profile. If mtimes tie, keep the
    # production-first order because release artifacts are the safest runtime
    # default when both release and dev are already valid.
    priority = {"release": 3, "debug": 2, "dev": 1}
    for profile in ("release", "debug", "dev"):
        try:
            status = collect_plugin_status(root, build_type=profile)
        except Exception:
            continue
        summary = status.get("summary", {})
        total = int(summary.get("total", 0) or 0)
        up_to_date = int(summary.get("up_to_date", 0) or 0)
        need_rebuild = int(summary.get("need_rebuild", 0) or 0)
        invalid = int(summary.get("invalid_metadata", 0) or 0)
        if total > 0 and up_to_date > 0 and need_rebuild == 0 and invalid == 0:
            candidates.append((_artifact_mtime(root, status), priority[profile], profile))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def _resolve_requested_profile(root: Path, args: list[str]) -> tuple[str, str]:
    explicit = _explicit_profile_from_args(args)
    if explicit is not None:
        return explicit, "explicit argument"

    for key in ("NEWENGINE_RUN_PROFILE", "NEWENGINE_PLUGIN_BUILD_TYPE", "NEWENGINE_BUILD_TYPE"):
        value = os.environ.get(key, "").strip().lower()
        if value in _VALID_RUN_PROFILES:
            return value, key

    latest = _latest_successful_plugin_build_profile(root)
    if latest is not None:
        return latest, "latest successful plugin build"

    current = _best_current_plugin_profile(root)
    if current is not None:
        return current, "current up-to-date plugin artifacts"

    return "dev", "default fallback"


def _cargo_profile(profile: str) -> str:
    # Plugins use a human-facing "debug" build type, but Cargo's standard
    # build profile for that artifact directory is still "dev".
    return "release" if profile == "release" else "dev"


def _target_profile_dir(cargo_profile: str) -> str:
    return "release" if cargo_profile == "release" else "debug"


def _cargo_executable() -> str:
    # The Windows launcher contract is explicit: run cargo.exe, not cargo run.
    return "cargo.exe" if os.name == "nt" else "cargo"


def _manifest_path(root: Path) -> Path:
    return root / "NewEngine" / "neocore2" / "apps" / _GAME_BIN / "Cargo.toml"


def _runtime_binary_path(root: Path, cargo_profile: str) -> Path:
    exe_name = f"{_GAME_BIN}.exe" if os.name == "nt" else _GAME_BIN
    return root / "NewEngine" / "neocore2" / "target" / _target_profile_dir(cargo_profile) / exe_name


def _build_command(root: Path, cargo_profile: str) -> list[str]:
    return [
        _cargo_executable(),
        "build",
        "--color=always",
        "--message-format=json-diagnostic-rendered-ansi",
        "--bin",
        _GAME_BIN,
        "--profile",
        cargo_profile,
        "--manifest-path",
        str(_manifest_path(root)),
    ]


def _runtime_args(args: list[str]) -> list[str]:
    return [arg for arg in args if arg.lower() not in _VALID_RUN_PROFILES and arg.lower() not in _PLUGIN_SYNC_FLAGS]


def _sync_plugins_if_needed(root: Path, *, requested_profile: str, args: list[str], log: TeeLog) -> int:
    force_plugins = "--force-plugins" in [arg.lower() for arg in args]
    explicit_sync = "--sync-plugins" in [arg.lower() for arg in args]
    no_sync = "--no-plugin-sync" in [arg.lower() for arg in args]
    check_only = "--check-plugins-only" in [arg.lower() for arg in args]

    status = collect_plugin_status(root, build_type=requested_profile, force=force_plugins)
    latest_json, latest_md = write_plugin_status_report(root, status)
    summary = status.get("summary", {})
    log.emit(
        "[PLUGIN] status: "
        f"up_to_date={summary.get('up_to_date', 0)} "
        f"need_rebuild={summary.get('need_rebuild', 0)} "
        f"total={summary.get('total', 0)} "
        f"build_type={requested_profile}"
    )
    log.emit(f"[PLUGIN] status json: {rel(root, latest_json)}")
    log.emit(f"[PLUGIN] status md: {rel(root, latest_md)}")

    stale_targets = stale_sync_targets(status)
    for record in status.get("records", []):
        if record.get("status_key") == "up_to_date":
            log.emit(f"[PLUGIN] plugins - up to date: {record.get('name', '')}")
        elif record.get("needs_rebuild"):
            log.emit(f"[PLUGIN] plugins - need rebuild: {record.get('name', '')} ({record.get('reason', '')})")
        else:
            log.emit(f"[PLUGIN] plugins - {record.get('status', 'skip')}: {record.get('name', '')} ({record.get('reason', '')})")

    if check_only:
        return 64 if stale_targets else 0
    if no_sync:
        if stale_targets:
            log.emit("[WARN] Plugin sync disabled by --no-plugin-sync; runtime may use stale/missing plugins.")
        return 0
    if not force_plugins and not explicit_sync and not stale_targets:
        log.emit("[PLUGIN] plugin sync skipped: all runtime plugin artifacts are up to date")
        return 0

    build_args: list[str]
    if force_plugins:
        all_targets = [str(record.get("name", "")) for record in status.get("records", []) if record.get("name") and record.get("status_key") not in {"disabled", "missing_source"}]
        build_args = [",".join(all_targets), requested_profile, "--force"] if all_targets else [requested_profile, "--force"]
        log.emit(f"[PLUGIN] forced plugin sync: {len(all_targets)} target(s)")
    elif explicit_sync and not stale_targets:
        build_args = [requested_profile]
        log.emit("[PLUGIN] explicit plugin sync requested")
    else:
        build_args = [",".join(stale_targets), requested_profile]
        log.emit(f"[PLUGIN] syncing stale plugin target(s): {', '.join(stale_targets)}")

    os.environ["NEWENGINE_PARENT_SCRIPT"] = "runGame"
    try:
        code = build_plugins(root, build_args, pause=False)
    finally:
        os.environ.pop("NEWENGINE_PARENT_SCRIPT", None)
    if code != 0:
        log.emit(f"[ERROR] runGame plugin sync failed with exit code {code}")
        return code

    refreshed = collect_plugin_status(root, build_type=requested_profile)
    write_plugin_status_report(root, refreshed)
    refreshed_summary = refreshed.get("summary", {})
    log.emit(
        "[PLUGIN] refreshed status: "
        f"up_to_date={refreshed_summary.get('up_to_date', 0)} "
        f"need_rebuild={refreshed_summary.get('need_rebuild', 0)}"
    )
    return 0


def _run_error_log_path(root: Path, target: str | None) -> Path:
    return root / f"buildERR-{safe_incident_name(target, fallback='runGame')}.log"


def _attach_run_error_log(root: Path, log: TeeLog, *, failed_name: str | None, code: int) -> Path:
    path = _run_error_log_path(root, failed_name)
    log.add_copy_target(path)
    log.emit(f"[ERROR] Run error mirror: {rel(root, path)}")
    log.emit(f"[ERROR] Failed run target: {safe_incident_name(failed_name, fallback='runGame')} exit_code={code}")
    return path


def run_game(root: Path, args: list[str]) -> int:
    apply_delete_list(root)
    requested_profile, profile_source = _resolve_requested_profile(root, args)
    cargo_profile = _cargo_profile(requested_profile)

    log_dir = root / "NewEngine" / "neocore2" / "logs" / "run"
    run_stamp = now_stamp()
    started_utc = utc_iso()
    finished_utc = ""
    current = log_dir / f"game-ready-fps-{run_stamp}.log"
    latest = log_dir / "game-ready-fps-latest.log"
    code = 0
    incident_target: str | None = None
    incident_message = "runGame failed"
    error_log_path: Path | None = None

    with TeeLog(current, latest) as log:
        env = os.environ.copy()
        env["NEWENGINE_REQUIRE_RENDER_BACKEND"] = "1"
        env.setdefault("NEWENGINE_TERMINAL_TYPEWRITER", "0")
        env.setdefault("NEWENGINE_TERMINAL_TYPEWRITER_DELAY_MS", "0")

        progress_configure(total=3, current=0, unit="phase", phase="run preflight")
        log.emit(f"[runGame] run log: {rel(root, current)}")
        log.emit(f"[runGame] started_utc: {started_utc}")
        log.emit(f"[runGame] selected profile: {requested_profile} ({profile_source})")

        progress_update(current=0, phase=f"syncing {requested_profile} runtime plugins")
        code = _sync_plugins_if_needed(root, requested_profile=requested_profile, args=args, log=log)
        if code != 0:
            incident_target = "runGame-plugin-sync"
            incident_message = "runGame plugin status/sync failed"
        else:
            progress_update(current=1, phase="runtime plugins ready")
            manifest = _manifest_path(root)
            if not manifest.exists():
                log.emit(f"[ERROR] game-ready-fps manifest not found: {rel(root, manifest)}")
                code = 2
                incident_target = "game-ready-fps-manifest"
                incident_message = "game-ready-fps manifest not found"
            else:
                build_args = _build_command(root, cargo_profile)
                log.emit(
                    f"[runGame] building {_GAME_BIN} requested_profile={requested_profile} cargo_profile={cargo_profile}"
                )
                log.emit(f"[runGame] manifest: {rel(root, manifest)}")
                progress_update(current=1, phase="building game-ready-fps")
                code = run_process(build_args, cwd=root, log=log, env=env)
                if code != 0:
                    log.emit(f"[ERROR] game-ready-fps build failed with exit code {code}.")
                    log.emit(f"[runGame] latest run log: {rel(root, latest)}")
                    incident_target = _GAME_BIN
                    incident_message = "game-ready-fps cargo build failed"
                else:
                    progress_update(current=2, phase="game-ready-fps built")
                    runtime_exe = _runtime_binary_path(root, cargo_profile)
                    if not runtime_exe.exists():
                        log.emit(f"[ERROR] Built runtime executable was not found: {rel(root, runtime_exe)}")
                        log.emit("[ERROR] Cargo build succeeded, but runGame could not resolve the binary path.")
                        log.emit(f"[runGame] latest run log: {rel(root, latest)}")
                        code = 3
                        incident_target = "game-ready-fps-executable"
                        incident_message = "game-ready-fps executable lookup failed"
                    else:
                        run_args = [str(runtime_exe), *_runtime_args(args)]
                        log.emit(f"[runGame] launching {_GAME_BIN}: {' '.join(quote_for_log(a) for a in run_args)}")
                        progress_update(current=2, phase="running game-ready-fps")
                        code = run_process(run_args, cwd=root / "NewEngine" / "neocore2", log=log, env=env)
                        progress_update(current=3, phase="runtime exited")
                        log.emit(f"[runGame] latest run log: {rel(root, latest)}")
                        if code != 0:
                            incident_target = "game-ready-fps-runtime"
                            incident_message = "game-ready-fps runtime exited with failure"

        finished_utc = utc_iso()
        log.emit(f"[runGame] finished_utc: {finished_utc}")
        log.emit(f"[runGame] exit_code: {code}")
        if code != 0:
            error_log_path = _attach_run_error_log(root, log, failed_name=incident_target or "runGame", code=code)

    if code != 0:
        incident = write_incident_bundle(
            root,
            kind="run",
            target=incident_target or "runGame",
            exit_code=code,
            primary_log=current,
            error_log=error_log_path,
            message=incident_message,
            command=f"takesome.py run-game {' '.join(args)}",
            started_utc=started_utc,
            finished_utc=finished_utc,
            extra={
                "requested_profile": requested_profile,
                "profile_source": profile_source,
                "cargo_profile": cargo_profile,
            },
        )
        emit_incident_console_lines(root, incident, label="Run")

    pause_on_error(code, context="runGame")
    return code
