from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..build_info import build_info_dir
from ..constants import DLL_EXT, ROOT_EXCLUDED_DIRS, SOURCE_ARCHIVE_EXCLUDED_EXTENSIONS
from ..cargo import cargo_version, rust_target_available
from ..logs import TeeLog
from ..paths import rel, suite_path, suite_root, utc_iso
from ..status_cache import write_status_snapshot
from .cache import scan_and_cache_tools, tool_cache_dir
from .constants import LEGACY_TOOL_PATHS
from .descriptors import discover_tools
from .validation import validate_native_tool_surface
from .invariants import run_p0_invariant_scan


@dataclass
class CheckResult:
    key: str
    status: str
    summary: str
    details: list[str] = field(default_factory=list)
    blocking: bool = False
    remediation: list[str] = field(default_factory=list)

    @property
    def rank(self) -> int:
        return {"OK": 0, "WARN": 1, "ERROR": 2}.get(self.status, 2)

    def as_record(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "rank": self.rank,
            "summary": self.summary,
            "details": self.details,
            "blocking": self.blocking,
            "remediation": self.remediation,
        }


def _ok(key: str, summary: str, details: list[str] | None = None) -> CheckResult:
    return CheckResult(key, "OK", summary, details or [], blocking=False)


def _warn(key: str, summary: str, details: list[str] | None = None, *, remediation: list[str] | None = None) -> CheckResult:
    return CheckResult(key, "WARN", summary, details or [], blocking=False, remediation=remediation or [])


def _error(key: str, summary: str, details: list[str] | None = None, *, remediation: list[str] | None = None) -> CheckResult:
    return CheckResult(key, "ERROR", summary, details or [], blocking=True, remediation=remediation or [])


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except Exception as exc:
        return None, str(exc)


def check_env(repo_root: Path) -> CheckResult:
    details: list[str] = []
    env_ok = os.environ.get("NEWENGINE_SCRIPT_ENV") == "1"
    expected = {
        "NEWENGINE_REPO_ROOT": repo_root,
        "NEWENGINE_ROOT": repo_root / "NewEngine" / "neocore2",
        "NEWENGINE_SCRIPT_ROOT": repo_root / "tools" / "scripts",
        "NEWENGINE_SUITE_ROOT": suite_root(repo_root),
    }
    for name, expected_path in expected.items():
        value = os.environ.get(name, "")
        if not value:
            details.append(f"missing {name}")
            continue
        try:
            if Path(value).resolve() != expected_path.resolve():
                details.append(f"{name}={value} expected={expected_path}")
        except OSError:
            details.append(f"{name}={value} is not resolvable")
    if not env_ok:
        details.append("NEWENGINE_SCRIPT_ENV is not 1")
    if details:
        return _warn("env", "Script Env is incomplete", details)
    return _ok("env", "Script Env valid")


def check_python() -> CheckResult:
    exe = sys.executable or shutil.which("python") or shutil.which("py")
    if not exe:
        return _error("python", "Python not found")
    return _ok("python", Path(exe).name, [sys.version.split()[0]])


def check_cargo() -> CheckResult:
    code, version = cargo_version()
    if code != 0:
        return _error("cargo", "Cargo not found", remediation=["Install Rust/Cargo or open the configured Rust developer environment before running build.plugins.force.dev."])
    return _ok("cargo", version or "cargo found")


def check_rust_target() -> CheckResult:
    requested = os.environ.get("CARGO_BUILD_TARGET", "").strip() or None
    ok, message = rust_target_available(requested)
    if ok:
        return _ok("rust", f"Rust target available{': ' + requested if requested else ''}", [message] if message else [])
    return _warn("rust", "Rust target probe failed", [message])


def check_plugin_manifest(repo_root: Path) -> CheckResult:
    manifest = repo_root / "Plugins" / "build_manifest.json"
    data, err = _read_json(manifest)
    if data is None:
        return _error("plugins", "plugin manifest invalid", [err])
    plugins = data.get("plugins", [])
    if not isinstance(plugins, list) or not plugins:
        return _error("plugins", "plugin manifest has no plugins")
    missing = [name for name in plugins if not (repo_root / "Plugins" / str(name)).exists()]
    if missing:
        return _warn("plugins", f"{len(plugins)} descriptors, {len(missing)} missing roots", missing)
    return _ok("plugins", f"{len(plugins)} descriptors")


def check_tool_registry(repo_root: Path, log: TeeLog | None = None) -> CheckResult:
    tools, warnings = discover_tools(repo_root)
    active = len(tools)
    cache_path = tool_cache_dir(repo_root) / "tool-registry.json"
    if not cache_path.exists() and log is not None:
        scan_and_cache_tools(repo_root, log=log)
    missing_docs = 0
    migration = repo_root / "tools" / "northstar" / "TOOLING_MIGRATION.md"
    if migration.exists():
        text = migration.read_text(encoding="utf-8", errors="replace").lower()
        missing_docs = text.count("missing") + text.count("planned")
    status_code = validate_native_tool_surface(repo_root, log=log or TeeLog())
    details = [*warnings]
    summary = f"{active} active"
    if missing_docs:
        summary += f" / {missing_docs} documented missing"
    if status_code != 0 or warnings:
        return _warn("tools", summary, details)
    return _ok("tools", summary)


def check_p0_invariants(repo_root: Path, log: TeeLog | None = None) -> CheckResult:
    rc = run_p0_invariant_scan(repo_root, strict_large_files=False, strict_boundaries=False, log=log or TeeLog())
    if rc == 0:
        return _ok("invariants", "P0 invariant scan passed; large-module/boundary debt is reported as staged warnings")
    return _warn(
        "invariants",
        "P0 invariant scan has findings; non-blocking for dev plugin rebuild",
        ["Architecture/invariant findings are diagnostic here, not a plugin-build preflight blocker."],
        remediation=["Run diag.invariants for the full architecture report; continue rebuild with build.plugins.force.dev when build preflight is otherwise clean."],
    )


def check_build_info(repo_root: Path) -> CheckResult:
    manifest = build_info_dir(repo_root) / "buildInfo.json"
    latest_report = build_info_dir(repo_root) / "plugin-build-latest.json"
    if not manifest.exists():
        return _warn("buildInfo", "latest buildInfo manifest missing")
    data, err = _read_json(manifest)
    if data is None:
        return _warn("buildInfo", "latest buildInfo manifest invalid", [err])
    if data.get("schema") != "takesome.buildInfo.v2":
        return _warn("buildInfo", "unknown buildInfo schema", [str(data.get("schema"))])
    latest = data.get("latest", {}) if isinstance(data.get("latest"), dict) else {}
    exit_code = latest.get("exit_code")
    artifact_count = latest.get("artifact_count", "?")
    build_file = latest.get("build_file", {}) if isinstance(latest.get("build_file"), dict) else {}
    details = []
    if not latest_report.exists():
        details.append("plugin-build-latest.json missing")
    if not build_file.get("sha256"):
        details.append("latest build file hash missing")
    text = f"latest valid, exit_code={exit_code}, artifacts={artifact_count}"
    return _ok("buildInfo", text, details) if exit_code == 0 and not details else _warn("buildInfo", text, details)


def _runtime_dlls(plugin_dir: Path) -> list[Path]:
    if not plugin_dir.exists():
        return []
    return sorted([*plugin_dir.glob(f"*{DLL_EXT}"), *plugin_dir.glob(f"codecs/*{DLL_EXT}")], key=lambda p: p.as_posix().lower())


def check_runtime_plugin_dir(repo_root: Path) -> CheckResult:
    plugin_dir = repo_root / "NewEngine" / "neocore2" / "plugins"
    if not plugin_dir.exists():
        return _warn("runtime", "runtime plugin dir missing")
    details: list[str] = []
    for stale in plugin_dir.rglob("platforms/*"):
        if stale.is_file():
            details.append(f"stale platform duplicate: {rel(repo_root, stale)}")
    dlls = _runtime_dlls(plugin_dir)
    if details:
        return _warn("runtime", f"{len(dlls)} runtime DLL(s), stale entries found", details)
    return _ok("runtime", f"{len(dlls)} runtime DLL(s)")


def check_dll_mismatch(repo_root: Path) -> CheckResult:
    buckets: dict[str, set[str]] = {}
    for dll in _runtime_dlls(repo_root / "NewEngine" / "neocore2" / "plugins"):
        stem = dll.stem.lower()
        profile = ""
        for suffix in ("-dev", "-debug", "-release"):
            if stem.endswith(suffix):
                profile = suffix[1:]
                stem = stem[: -len(suffix)]
                break
        if profile:
            buckets.setdefault(stem, set()).add(profile)
    mismatches = [f"{name}: {', '.join(sorted(profiles))}" for name, profiles in sorted(buckets.items()) if len(profiles) > 1]
    if mismatches:
        return _warn("dlls", "dev/release DLL mismatch present", mismatches)
    return _ok("dlls", "dev/release DLL mismatch absent")


def check_legacy_paths(repo_root: Path) -> CheckResult:
    live = [path for raw in LEGACY_TOOL_PATHS if (path := repo_root / raw).exists()]
    if live:
        return _warn("legacy", f"{len(live)} legacy path(s) still exist", [rel(repo_root, p) for p in live])
    return _ok("legacy", "legacy paths absent")


def check_logs(repo_root: Path) -> CheckResult:
    old_paths = [
        repo_root / "NewEngine" / "neocore2" / "logs" / "build",
        suite_path(repo_root, "logs", "build"),
    ]
    live = [path for path in old_paths if path.exists()]
    if live:
        return _warn("logs", "legacy build log path exists", [rel(repo_root, path) for path in live])
    return _ok("logs", "legacy build log paths absent")


def check_root_clean(repo_root: Path) -> CheckResult:
    forbidden_exts = {".zip", ".7z", ".rar", ".log", ".dll", ".exe", ".pdb", ".bin"}
    offenders = [
        p.name
        for p in repo_root.iterdir()
        if p.is_file()
        and p.suffix.lower() in forbidden_exts
        and not (p.name == "lastbuild.log" or (p.name.startswith("lastbuild-") and p.suffix.lower() == ".log"))
    ]
    if offenders:
        return _warn("root", "root has random archive/log/bin files", sorted(offenders))
    return _ok("root", "root has no random zip/log/bin")



def _json_path_bool(data: dict[str, Any], path: list[str], default: bool | None = None) -> bool | None:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur if isinstance(cur, bool) else default


def check_performance_policy(repo_root: Path) -> CheckResult:
    details: list[str] = []

    for rel_path in [
        "Plugins/winit-platform-plugin/newengine-platform-winit/assets/default_config.json",
        "Plugins/winit-platform-plugin/newengine-platform-winit/startup_config_schema.json",
        "NewEngine/neocore2/config.json",
    ]:
        path = repo_root / rel_path
        if not path.exists():
            continue
        data, err = _read_json(path)
        if data is None:
            details.append(f"{rel_path}: invalid json: {err}")
            continue
        for candidate in [
            ["display", "vsync"],
            ["defaults", "display", "vsync"],
            ["plugins", "newengine", "platform.winit", "display", "vsync"],
            ["plugins", "newengine", "startup_window", "display", "vsync"],
        ]:
            value = _json_path_bool(data, candidate, None)
            if value is True:
                details.append(f"{rel_path}: {'.'.join(candidate)} is true; max-FPS runs require explicit opt-in vsync")

    present_mode = os.environ.get("NEWENGINE_VULKAN_PRESENT_MODE", "").strip().lower()
    if present_mode in {"fifo", "vsync", "stable"}:
        details.append(f"NEWENGINE_VULKAN_PRESENT_MODE={present_mode} caps presentation; use immediate/mailbox/uncapped for benchmark/dev max-FPS")

    frame_driver = os.environ.get("NEWENGINE_PLATFORM_FRAME_DRIVER", "").strip().lower()
    if frame_driver in {"wait", "redraw", "redraw-wait"}:
        details.append(f"NEWENGINE_PLATFORM_FRAME_DRIVER={frame_driver} can idle-cap redraw cadence; default poll is preferred for max-FPS development")

    if details:
        return _warn("perf", "max-FPS policy has explicit caps", details)
    return _ok("perf", "max-FPS defaults active; caps require explicit opt-in")


def check_source_archive_policy(repo_root: Path) -> CheckResult:
    details: list[str] = []
    if not SOURCE_ARCHIVE_EXCLUDED_EXTENSIONS:
        details.append("SOURCE_ARCHIVE_EXCLUDED_EXTENSIONS is empty")
    for name in ROOT_EXCLUDED_DIRS:
        if name in {"target", ".takesome", ".git"}:
            continue
    packer = repo_root / "tools" / "scripts" / "takesome" / "archive.py"
    if not packer.exists():
        details.append("archive.py missing")
    if details:
        return _warn("source", "source archive policy incomplete", details)
    return _ok("source", "source archive policy valid")


def render_workspace_doctor_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Workspace Doctor",
        "",
        f"- generated_utc: `{payload.get('generated_utc', '')}`",
        f"- status: `{payload.get('status', '')}`",
        "",
        "| status | key | summary |",
        "|---|---|---|",
    ]
    for check in payload.get("checks", []):
        if not isinstance(check, dict):
            continue
        summary = str(check.get("summary", "")).replace("|", "/")
        lines.append(f"| {check.get('status', '')} | `{check.get('key', '')}` | {summary} |")
        details = check.get("details", [])
        if isinstance(details, list):
            for detail in details[:10]:
                lines.append(f"|  |  | - {str(detail).replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def run_workspace_doctor(repo_root: Path, *, full: bool, log: TeeLog | None = None) -> int:
    own_log = log or TeeLog()
    checks = [
        check_env(repo_root),
        check_python(),
        check_cargo(),
        check_rust_target(),
        check_plugin_manifest(repo_root),
        check_tool_registry(repo_root, log=own_log),
        check_p0_invariants(repo_root, log=own_log),
        check_build_info(repo_root),
        check_runtime_plugin_dir(repo_root),
        check_dll_mismatch(repo_root),
        check_performance_policy(repo_root),
        check_legacy_paths(repo_root),
        check_logs(repo_root),
        check_root_clean(repo_root),
        check_source_archive_policy(repo_root),
    ]
    grouped = {
        "env": ["env", "python", "cargo", "rust"],
        "plugins": ["plugins"],
        "tools": ["tools"],
        "invariants": ["invariants"],
        "buildInfo": ["buildInfo"],
        "runtime": ["runtime", "dlls"],
        "perf": ["perf"],
        "legacy": ["legacy"],
        "logs": ["logs"],
        "root": ["root"],
        "source": ["source"],
    }
    by_key = {check.key: check for check in checks}
    own_log.emit("")
    own_log.emit("WORKSPACE DOCTOR")
    worst = 0
    for group, keys in grouped.items():
        group_checks = [by_key[key] for key in keys if key in by_key]
        rank = max((c.rank for c in group_checks), default=0)
        worst = max(worst, rank)
        status = {0: "OK", 1: "WARN", 2: "ERROR"}[rank]
        summary = "; ".join(c.summary for c in group_checks if c.rank == rank) or "; ".join(c.summary for c in group_checks)
        own_log.emit(f"  {group:<10} {status:<5} {summary}")
        if full:
            for check in group_checks:
                if check.details:
                    for detail in check.details:
                        own_log.emit(f"    - {check.key}: {detail}")
    blocking_checks = [check for check in checks if check.status == "ERROR" and check.blocking]
    warning_checks = [check for check in checks if check.status == "WARN" or (check.status == "ERROR" and not check.blocking)]
    status_label = "ERROR" if blocking_checks else ({0: "OK", 1: "WARN", 2: "WARN"}.get(worst, "WARN"))
    payload = {
        "schema": "takesome.workspaceDoctor.v1",
        "generated_utc": utc_iso(),
        "full": bool(full),
        "status": status_label,
        "worst_rank": worst,
        "blocking_count": len(blocking_checks),
        "warning_count": len(warning_checks),
        "blocking": [check.as_record() for check in blocking_checks],
        "warnings": [check.as_record() for check in warning_checks],
        "remediation": [item for check in blocking_checks for item in check.remediation],
        "checks": [check.as_record() for check in checks],
        "groups": {
            group: {
                "status": {0: "OK", 1: "WARN", 2: "ERROR"}[max((by_key[key].rank for key in keys if key in by_key), default=0)],
                "keys": [key for key in keys if key in by_key],
            }
            for group, keys in grouped.items()
        },
    }
    summary_md = render_workspace_doctor_markdown(payload)
    write_status_snapshot(
        repo_root,
        "workspace-doctor",
        payload,
        summary_markdown=summary_md,
        source="tools.doctor.run_workspace_doctor",
    )
    own_log.emit("")
    if not blocking_checks and not warning_checks:
        own_log.emit("[OK] Workspace doctor passed.")
        own_log.emit("[NEXT] Agent-safe rebuild command: build.plugins.force.dev")
        return 0
    if not blocking_checks:
        own_log.emit(f"[WARN] Workspace doctor completed with {len(warning_checks)} non-blocking warning/check finding(s).")
        own_log.emit("[NEXT] Optional cleanup: workspace.clean.full")
        own_log.emit("[NEXT] Agent-safe rebuild command: build.plugins.force.dev")
        return 0
    own_log.emit(f"[ERROR] Workspace doctor found {len(blocking_checks)} blocking error(s).")
    own_log.emit("[NEXT] Fix blocking checks listed above, then run workspace.clean.full and build.plugins.force.dev.")
    return 1
