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
from ..paths import engine_core_root, plugins_root, rel, suite_path, suite_root, utc_iso
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
        return {"key": self.key, "status": self.status, "rank": self.rank, "summary": self.summary, "details": self.details, "blocking": self.blocking, "remediation": self.remediation}


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
        "NEWENGINE_ROOT": engine_core_root(repo_root),
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
    plugin_root = plugins_root(repo_root)
    manifest = plugin_root / "build_manifest.json"
    data, err = _read_json(manifest)
    if data is None:
        return _error("plugins", "plugin manifest invalid", [err])
    plugins = data.get("plugins", [])
    if not isinstance(plugins, list) or not plugins:
        return _error("plugins", "plugin manifest has no plugins")
    missing = [name for name in plugins if not (plugin_root / str(name)).exists()]
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
    return _warn("invariants", "P0 invariant scan has findings; non-blocking for dev plugin rebuild", ["Architecture/invariant findings are diagnostic here, not a plugin-build preflight blocker."], remediation=["Run diag.invariants for the full architecture report; continue rebuild with build.plugins.force.dev when build preflight is otherwise clean."])


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
    plugin_dir = engine_core_root(repo_root) / "plugins"
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
    for dll in _runtime_dlls(engine_core_root(repo_root) / "plugins"):
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
        engine_core_root(repo_root) / "logs" / "build",
        suite_path(repo_root, "logs", "build"),
    ]
    live = [path for path in old_paths if path.exists()]
    if live:
        return _warn("logs", "legacy build log path exists", [rel(repo_root, path) for path in live])
    return _ok("logs", "legacy build log paths absent")


def check_root_clean(repo_root: Path) -> CheckResult:
    forbidden_exts = {".zip", ".7z", ".rar", ".log", ".dll", ".exe", ".pdb", ".bin"}
    offenders = [p.name for p in repo_root.iterdir() if p.is_file() and p.suffix.lower() in forbidden_exts and not (p.name == "lastbuild.log" or (p.name.startswith("lastbuild-") and p.suffix.lower() == ".log"))]
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
        "EngineRepo/Plugins/winit-platform-plugin/newengine-platform-winit/assets/default_config.json",
        "EngineRepo/Plugins/winit-platform-plugin/newengine-platform-winit/startup_config_schema.json",
        "EngineRepo/NewEngine/neocore2/config.json",
    ]:
        path = repo_root / rel_path
        if not path.exists():
            continue
        data, err = _read_json(path)
        if data is None:
            details.append(f"{rel_path}: invalid json: {err}")
            continue
        for candidate in [["display", "vsync"], ["defaults", "display", "vsync"], ["plugins", "newengine", "platform.winit", "display", "vsync"], ["plugins", "newengine", "startup_window", "display", "vsync"]]:
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
    packer = repo_root / "tools" / "scripts" / "takesome" / "archive.py"
    if not packer.exists():
        details.append("archive.py missing")
    if details:
        return _warn("source", "source archive policy incomplete", details)
    return _ok("source", "source archive policy valid")


def render_workspace_doctor_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Workspace Doctor", "", f"- generated_utc: `{payload.get('generated_utc', '')}`", f"- status: `{payload.get('status', '')}`", "", "| status | key | summary |", "|---|---|---|"]
    for item in payload.get("checks", []):
        lines.append(f"| `{item.get('status')}` | `{item.get('key')}` | {item.get('summary', '')} |")
    lines.append("")
    for item in payload.get("checks", []):
        if item.get("details"):
            lines.append(f"## {item.get('key')}")
            for detail in item.get("details", []):
                lines.append(f"- {detail}")
            lines.append("")
        if item.get("remediation"):
            lines.append(f"### {item.get('key')} remediation")
            for detail in item.get("remediation", []):
                lines.append(f"- {detail}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def workspace_doctor_payload(repo_root: Path, *, full: bool = False, log: TeeLog | None = None) -> dict[str, Any]:
    checks = [check_env(repo_root), check_python(), check_cargo(), check_rust_target(), check_plugin_manifest(repo_root), check_tool_registry(repo_root, log=log), check_p0_invariants(repo_root, log=log), check_build_info(repo_root), check_runtime_plugin_dir(repo_root), check_dll_mismatch(repo_root), check_legacy_paths(repo_root), check_logs(repo_root), check_root_clean(repo_root), check_performance_policy(repo_root), check_source_archive_policy(repo_root)]
    if full:
        checks.extend([])
    status = "OK" if all(item.status == "OK" for item in checks) else "WARN" if all(item.status != "ERROR" for item in checks) else "ERROR"
    payload = {"schema": "takesome.workspace.doctor.v1", "generated_utc": utc_iso(), "status": status, "blocking": any(item.blocking for item in checks), "checks": [item.as_record() for item in checks]}
    return payload


def run_workspace_doctor(repo_root: Path, *, full: bool = False, log: TeeLog | None = None) -> int:
    payload = workspace_doctor_payload(repo_root, full=full, log=log)
    out_dir = build_info_dir(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "workspace-doctor.json"
    md_path = out_dir / "workspace-doctor.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_workspace_doctor_markdown(payload), encoding="utf-8")
    write_status_snapshot(repo_root, "workspace-doctor", payload)
    if log:
        log.emit(f"[INFO] Workspace doctor: {json_path}")
        log.emit(f"[INFO] Workspace doctor markdown: {md_path}")
        for check in payload["checks"]:
            log.emit(f"[{check['status']}] {check['key']}: {check['summary']}")
            for detail in check.get("details", [])[:10]:
                log.emit(f"  - {detail}")
    return 2 if payload.get("blocking") else 0


def workspace_doctor_command(repo_root: Path, _ns: Any) -> int:
    return run_workspace_doctor(repo_root, full=True, log=TeeLog())
