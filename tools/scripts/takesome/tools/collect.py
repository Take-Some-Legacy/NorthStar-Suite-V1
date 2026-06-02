from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from ..build_info import build_info_dir
from ..filesystem import best_effort_remove_path
from ..logs import TeeLog
from ..paths import now_stamp, rel, suite_path, suite_root, utc_iso
from ..status_cache import build_status_cache_index, status_cache_dir, write_status_cache_index, write_status_snapshot
from .cache import scan_and_cache_tools, tool_cache_dir
from .run_report import build_run_report_payload, compact_path, render_report_markdown


DYNAMIC_LIBRARY_EXTENSIONS = {".dll", ".so", ".dylib"}


def _write_json_to_zip(zf: zipfile.ZipFile, name: str, payload: dict) -> None:
    zf.writestr(name, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _entry(root: Path, path: Path, archive_name: str, category: str, copied: bool, error: str = "") -> dict[str, Any]:
    try:
        stat = path.stat() if path.exists() else None
        size = stat.st_size if stat else 0
        modified = int(stat.st_mtime) if stat else 0
    except OSError:
        size = 0
        modified = 0
    payload: dict[str, Any] = {
        "source": rel(root, path),
        "source_short": compact_path(root, rel(root, path)),
        "archive": archive_name,
        "category": category,
        "size_bytes": size,
        "modified_unix": modified,
        "copied": copied,
    }
    if error:
        payload["error"] = error
    return payload


def _unique_archive_name(used: set[str], preferred: str) -> str:
    preferred = preferred.replace("\\", "/").strip("/")
    if preferred not in used:
        used.add(preferred)
        return preferred
    path = Path(preferred)
    suffix = path.suffix
    stem = path.name[: -len(suffix)] if suffix else path.name
    parent = path.parent.as_posix()
    index = 2
    while True:
        name = f"{stem}-{index}{suffix}"
        candidate = f"{parent}/{name}" if parent and parent != "." else name
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def _write_file(
    zf: zipfile.ZipFile,
    root: Path,
    path: Path,
    *,
    archive_name: str,
    category: str,
    used_archives: set[str],
    copied_entries: list[dict[str, Any]],
    seen_sources: set[str],
) -> bool:
    if not path.exists() or not path.is_file():
        return False
    source_key = str(path.resolve()).lower()
    if source_key in seen_sources:
        return False
    seen_sources.add(source_key)
    final_name = _unique_archive_name(used_archives, archive_name)
    try:
        zf.write(path, final_name)
    except OSError as exc:
        copied_entries.append(_entry(root, path, final_name, category, False, str(exc)))
        return False
    copied_entries.append(_entry(root, path, final_name, category, True))
    return True


def _copy_file(
    zf: zipfile.ZipFile,
    root: Path,
    path: Path,
    *,
    archive_name: str | None = None,
    category: str = "files",
    used_archives: set[str] | None = None,
    copied_entries: list[dict[str, Any]] | None = None,
    seen_sources: set[str] | None = None,
) -> bool:
    # Compatibility helper for older call sites; new collect-run passes explicit manifests.
    used = used_archives if used_archives is not None else set()
    entries = copied_entries if copied_entries is not None else []
    seen = seen_sources if seen_sources is not None else set()
    name = archive_name or f"files/{rel(root, path)}"
    return _write_file(zf, root, path, archive_name=name, category=category, used_archives=used, copied_entries=entries, seen_sources=seen)


def _copy_tree(
    zf: zipfile.ZipFile,
    root: Path,
    directory: Path,
    *,
    archive_root: str,
    category: str,
    used_archives: set[str],
    copied_entries: list[dict[str, Any]],
    seen_sources: set[str],
    log_paths: list[Path] | None = None,
) -> int:
    if not directory.exists():
        return 0
    count = 0
    for path in sorted(directory.rglob("*"), key=lambda p: p.as_posix().lower()):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(directory).as_posix()
        except ValueError:
            relative = path.name
        if _write_file(
            zf,
            root,
            path,
            archive_name=f"{archive_root}/{relative}",
            category=category,
            used_archives=used_archives,
            copied_entries=copied_entries,
            seen_sources=seen_sources,
        ):
            count += 1
            if log_paths is not None and path.suffix.lower() == ".log":
                log_paths.append(path)
    return count


def _compact_env_value(root: Path, value: str) -> str:
    if not value:
        return ""
    return compact_path(root, value)


def _system_probe(root: Path) -> dict:
    cargo = shutil.which("cargo")
    cargo_version = ""
    if cargo:
        proc = subprocess.run([cargo, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        cargo_version = proc.stdout.strip()
    return {
        "schema": "takesome.systemProbe.v2",
        "generated_utc": utc_iso(),
        "root": root.name,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.replace("\n", " "),
        "python_executable": _compact_env_value(root, sys.executable),
        "cargo": _compact_env_value(root, cargo or ""),
        "cargo_version": cargo_version,
        "env": {
            key: _compact_env_value(root, os.environ.get(key, ""))
            for key in [
                "NEWENGINE_SCRIPT_ENV",
                "NEWENGINE_REPO_ROOT",
                "NEWENGINE_ROOT",
                "NEWENGINE_SCRIPT_ROOT",
                "CARGO_BUILD_TARGET",
            ]
        },
    }


def _plugin_route_dump(root: Path) -> dict:
    plugin_dir = root / "NewEngine" / "neocore2" / "plugins"
    binaries = []
    if plugin_dir.exists():
        for path in sorted(plugin_dir.rglob("*"), key=lambda p: p.as_posix().lower()):
            if not path.is_file() or path.suffix.lower() not in DYNAMIC_LIBRARY_EXTENSIONS:
                continue
            try:
                size = path.stat().st_size
                sha = _sha256_file(path)
            except OSError:
                size = 0
                sha = ""
            binaries.append({"name": path.name, "path": compact_path(root, rel(root, path)), "size": size, "sha256": sha[:16], "extension": path.suffix.lower()})
    manifest = root / "Plugins" / "build_manifest.json"
    manifest_data = {}
    if manifest.exists():
        try:
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            manifest_data = {"error": str(exc)}
    return {
        "schema": "takesome.pluginRouteDump.v3",
        "generated_utc": utc_iso(),
        "runtime_plugin_dir": compact_path(root, rel(root, plugin_dir)),
        "installed_dynamic_library_count": len(binaries),
        "installed_dll_count": len([item for item in binaries if item.get("extension") == ".dll"]),
        "installed_dynamic_libraries": binaries,
        "installed_dlls": binaries,
        "build_manifest": manifest_data,
    }


def _latest_profiler_reports(root: Path) -> list[Path]:
    patterns = [
        "NewEngine/neocore2/cache/profiler/profiler_report_latest.*",
        "NewEngine/neocore2/cache/profiler/profiler_report*.zip",
        "NewEngine/neocore2/cache/profiler/profiler_*.csv",
        "NewEngine/neocore2/logs/**/*profiler*",
        "NewEngine/neocore2/logs/**/*profile*",
        ".takesome/reports/**/*profiler*",
        "profiler_report*.zip",
        "profiler*.zip",
    ]
    found: list[Path] = []
    for pattern in patterns:
        found.extend(path for path in root.glob(pattern) if path.is_file())
    seen: set[str] = set()
    deduped: list[Path] = []
    for path in sorted(found, key=lambda p: p.stat().st_mtime, reverse=True):
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped[:80]


def _profiler_data_roots(root: Path) -> list[Path]:
    candidates = [
        root / "NewEngine" / "neocore2" / "cache" / "profiler",
        suite_path(root, "profiler"),
        suite_path(root, "reports", "profiler"),
    ]
    return [path for path in candidates if path.exists()]


def _collect_profiler_data(
    zf: zipfile.ZipFile,
    root: Path,
    *,
    used_archives: set[str],
    copied_entries: list[dict[str, Any]],
    seen_sources: set[str],
) -> tuple[int, dict]:
    copied = 0
    files: list[dict[str, Any]] = []
    root_stats: dict[str, dict[str, Any]] = {}

    def root_key_for(path: Path) -> str:
        for directory in _profiler_data_roots(root):
            try:
                path.resolve().relative_to(directory.resolve())
                return compact_path(root, rel(root, directory))
            except ValueError:
                continue
        return "latest-patterns"

    def add_file(path: Path) -> None:
        nonlocal copied
        if not path.exists() or not path.is_file():
            return
        before = len(copied_entries)
        ok = _write_file(
            zf,
            root,
            path,
            archive_name=f"profiler/{path.name}",
            category="profiler",
            used_archives=used_archives,
            copied_entries=copied_entries,
            seen_sources=seen_sources,
        )
        if not ok:
            return
        copied += 1
        entry = copied_entries[-1] if len(copied_entries) > before else _entry(root, path, f"profiler/{path.name}", "profiler", True)
        files.append(entry)
        key = root_key_for(path)
        stat = root_stats.setdefault(key, {"root": key, "files": 0, "bytes": 0})
        stat["files"] += 1
        stat["bytes"] += int(entry.get("size_bytes", 0) or 0)

    profiler_roots = _profiler_data_roots(root)
    for directory in profiler_roots:
        for path in sorted(directory.rglob("*"), key=lambda p: p.as_posix().lower()):
            add_file(path)

    for path in _latest_profiler_reports(root):
        add_file(path)

    cache_cleanup_roots = _bundle_cache_cleanup_roots(root)
    manifest = {
        "schema": "takesome.profilerDataIndex.v3",
        "generated_utc": utc_iso(),
        "roots": [compact_path(root, rel(root, path)) for path in profiler_roots],
        "root_stats": sorted(root_stats.values(), key=lambda it: str(it.get("root", ""))),
        "cache_cleanup_roots": [compact_path(root, rel(root, path)) for path in cache_cleanup_roots],
        "latest_patterns_included": True,
        "copied_files": copied,
        "files": files,
    }
    return copied, manifest



def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _engine_health_snapshot(root: Path, plugin_routes: dict[str, Any]) -> dict[str, Any]:
    engine_root = root / "NewEngine" / "neocore2"
    runtime_plugin_dir = engine_root / "plugins"
    runtime_codec_dir = runtime_plugin_dir / "codecs"
    logs_root = engine_root / "logs"
    runtime_plugins = plugin_routes.get("installed_dynamic_libraries", []) if isinstance(plugin_routes.get("installed_dynamic_libraries"), list) else []
    return {
        "schema": "takesome.engineHealth.v1",
        "generated_utc": utc_iso(),
        "engine_root": rel(root, engine_root),
        "exists": engine_root.exists(),
        "cargo_toml_exists": (engine_root / "Cargo.toml").exists(),
        "config_exists": (engine_root / "config.json").exists(),
        "runtime_plugin_dir": rel(root, runtime_plugin_dir),
        "runtime_plugin_dir_exists": runtime_plugin_dir.exists(),
        "runtime_codec_dir_exists": runtime_codec_dir.exists(),
        "installed_dynamic_library_count": len(runtime_plugins),
        "installed_plugin_count": len([item for item in runtime_plugins if isinstance(item, dict) and "/codecs/" not in str(item.get("path", "")).replace("\\", "/")]),
        "installed_codec_count": len([item for item in runtime_plugins if isinstance(item, dict) and "/codecs/" in str(item.get("path", "")).replace("\\", "/")]),
        "logs_root_exists": logs_root.exists(),
        "run_log_count": len(list((logs_root / "run").glob("*.log"))) if (logs_root / "run").exists() else 0,
        "build_log_count": len(list((logs_root / "build").glob("*.log"))) if (logs_root / "build").exists() else 0,
        "cache_exists": (engine_root / "cache").exists(),
    }


def _collect_diagnostics_status_cache(root: Path, *, system_probe: dict[str, Any], plugin_routes: dict[str, Any], log: TeeLog) -> dict[str, Any]:
    """Refresh reusable status snapshots before collect-run packs them."""

    from ..plugin_status import collect_plugin_status, write_plugin_status_report
    from ..suite.context import load_suite_context
    from ..suite.settings import load_suite_settings
    from ..suite.status.git_health import collect_git_health
    from ..suite.status.incident_health import collect_incident_health
    from ..suite.status.tool_health import collect_tool_health
    from ..workspace_registry import build_workspace_registry, write_registry_files

    context = load_suite_context(root)
    settings = load_suite_settings(root)
    log.emit(f"[COLLECT] Refreshing status cache for profile={context.profile} platform={context.platform.id}.")

    plugin_status = collect_plugin_status(root, build_type=context.profile, platform_id=context.platform.id)
    plugin_status_json, plugin_status_md = write_plugin_status_report(root, plugin_status)

    workspace_registry = build_workspace_registry(root)
    workspace_json, workspace_md = write_registry_files(root, workspace_registry)

    tool_registry = _read_json_file(suite_path(root, "tools", "tool-registry.json"))
    tool_health = collect_tool_health(root)
    git_health = collect_git_health(root)
    incident_health = collect_incident_health(root)
    engine_health = _engine_health_snapshot(root, plugin_routes)

    context_payload = {
        "schema": "takesome.suiteContextStatus.v1",
        "generated_utc": utc_iso(),
        "profile": context.profile,
        "platform": context.platform.id,
        "platform_label": context.platform.label,
        "rust_target": context.platform.rust_target or "",
        "context_source": context.source,
        "settings": {
            "theme": settings.theme,
            "density": settings.density,
            "show_paths": settings.show_paths,
            "show_recent": settings.show_recent,
            "source": settings.source,
        },
    }
    write_status_snapshot(root, "suite-context", context_payload, source="collect-run")

    tool_health_payload = {
        "schema": "takesome.toolHealth.v1",
        "generated_utc": utc_iso(),
        "total": tool_health.total,
        "invalid": tool_health.invalid,
        "warnings": list(tool_health.warnings),
        "registry": tool_registry,
    }
    write_status_snapshot(root, "tool-health", tool_health_payload, source="collect-run")

    git_payload = {
        "schema": "takesome.gitHealth.v1",
        "generated_utc": utc_iso(),
        "available": git_health.available,
        "dirty": git_health.dirty,
        "changed_files": git_health.changed_files,
        "branch": git_health.branch,
        "error": git_health.error,
    }
    write_status_snapshot(root, "git-health", git_payload, source="collect-run")

    incident_payload = {
        "schema": "takesome.incidentHealth.v1",
        "generated_utc": utc_iso(),
        "exists": incident_health.exists,
        "kind": incident_health.kind,
        "target": incident_health.target,
        "incident_generated_utc": incident_health.generated_utc,
        "summary": incident_health.summary,
        "exit_code": incident_health.exit_code,
    }
    write_status_snapshot(root, "incident-health", incident_payload, source="collect-run")
    write_status_snapshot(root, "engine-health", engine_health, source="collect-run")
    write_status_snapshot(root, "system-probe", system_probe, source="collect-run")
    write_status_snapshot(root, "plugin-route-dump", plugin_routes, source="collect-run")

    plugin_summary = plugin_status.get("summary", {}) if isinstance(plugin_status.get("summary"), dict) else {}
    workspace_summary = workspace_registry.get("summary", {}) if isinstance(workspace_registry.get("summary"), dict) else {}
    health_bundle = {
        "schema": "takesome.collectRunHealthBundle.v1",
        "generated_utc": utc_iso(),
        "context": context_payload,
        "workspace_health": "error" if plugin_summary.get("invalid_metadata") else ("warn" if plugin_summary.get("need_rebuild") or git_health.dirty or tool_health.invalid else "ok"),
        "recommended_next": "Explain plugin state" if plugin_summary.get("invalid_metadata") else ("Plugin Maintenance" if plugin_summary.get("need_rebuild") else ("Review Git batch" if git_health.dirty else "Dev Smoke")),
        "plugins": plugin_summary,
        "workspace_registry_summary": workspace_summary,
        "tools": {"total": tool_health.total, "invalid": tool_health.invalid, "warnings": list(tool_health.warnings)},
        "git": git_payload,
        "incident": incident_payload,
        "engine": engine_health,
        "paths": {
            "plugin_status_json": rel(root, plugin_status_json),
            "plugin_status_md": rel(root, plugin_status_md),
            "workspace_registry_json": rel(root, workspace_json),
            "workspace_registry_md": rel(root, workspace_md),
            "status_cache": rel(root, status_cache_dir(root)),
        },
    }
    write_status_snapshot(root, "collect-run-health", health_bundle, source="collect-run")
    index_path = write_status_cache_index(root)
    health_bundle["status_cache_index"] = rel(root, index_path)
    health_bundle["status_cache"] = build_status_cache_index(root)
    return health_bundle


def _collect_status_cache_data(
    zf: zipfile.ZipFile,
    root: Path,
    *,
    used_archives: set[str],
    copied_entries: list[dict[str, Any]],
    seen_sources: set[str],
) -> dict[str, Any]:
    cache_root = status_cache_dir(root)
    copied = _copy_tree(
        zf,
        root,
        cache_root,
        archive_root="generated/status-cache",
        category="status-cache",
        used_archives=used_archives,
        copied_entries=copied_entries,
        seen_sources=seen_sources,
    )
    index = build_status_cache_index(root)
    index["copied_files"] = copied
    return index


def _collect_latest_build_log(
    zf: zipfile.ZipFile,
    root: Path,
    *,
    used_archives: set[str],
    copied_entries: list[dict[str, Any]],
    seen_sources: set[str],
) -> int:
    build_root = build_info_dir(root)
    copied = 0
    latest_paths = [
        build_root / "buildInfo.json",
        build_root / "plugin-build-latest.json",
        build_root / "plugin-build-latest.md",
        build_root / "plugin-sync-latest.log",
        build_root / "plugin-sync-latest-items.zip",
    ]
    latest_manifest = build_root / "buildInfo.json"
    if latest_manifest.exists():
        try:
            data = json.loads(latest_manifest.read_text(encoding="utf-8"))
            latest = data.get("latest", {}) if isinstance(data, dict) else {}
            for key in ["build_file", "report_json", "report_md"]:
                value = latest.get(key) if isinstance(latest, dict) else None
                if isinstance(value, dict) and value.get("path"):
                    latest_paths.append(root / str(value["path"]))
        except Exception:
            pass
    for path in latest_paths:
        if _write_file(
            zf,
            root,
            path,
            archive_name=f"build/{path.name}",
            category="build",
            used_archives=used_archives,
            copied_entries=copied_entries,
            seen_sources=seen_sources,
        ):
            copied += 1
    return copied


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _bundle_cache_cleanup_roots(root: Path) -> list[Path]:
    candidates = [
        root / "NewEngine" / "neocore2" / "cache",
        suite_path(root, "tools"),
        suite_path(root, "profiler"),
        suite_path(root, "reports"),
    ]
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.exists():
            continue
        if not _is_inside(candidate, root):
            continue
        # Bundle output is project-root/run-bundle-*.zip, so suite report/cache
        # roots can be cleaned after their data has been copied.
        key = str(candidate.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(candidate)
    roots.sort(key=lambda p: p.as_posix().lower())
    return roots


def _clean_bundle_cache_roots(root: Path, roots: list[Path], log: TeeLog) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "takesome.postBundleCacheCleanup.v1",
        "generated_utc": utc_iso(),
        "cleaned": 0,
        "skipped": 0,
        "warnings": 0,
        "items": [],
    }
    if not roots:
        log.emit("[COLLECT] No post-bundle cache roots to clean.")
        return result
    log.emit(f"[COLLECT] Cleaning {len(roots)} cache root(s) after bundle data was copied.")
    for cache_dir in roots:
        label = rel(root, cache_dir)
        log.emit(f"[COLLECT] Cache cleanup: {label}")
        item = {"path": compact_path(root, label), "status": "", "message": ""}
        cleanup = best_effort_remove_path(root, cache_dir, quarantine_on_failure=False)
        item["status"] = cleanup.status
        item["message"] = cleanup.message
        if cleanup.status == "deleted":
            result["cleaned"] += 1
            suffix = f" ({cleanup.message})" if cleanup.message else ""
            log.emit(f"[OK] Cache cleaned: {label}{suffix}")
        elif cleanup.status == "missing":
            result["skipped"] += 1
            log.emit(f"[SKIP] Cache already missing: {label}")
        else:
            result["warnings"] += 1
            log.emit(f"[WARN] Cache cleanup failed: {label}: {cleanup.message}")
        result["items"].append(item)
    return result


def collect_run_bundle(root: Path, *, log: TeeLog | None = None) -> int:
    own_log = log or TeeLog()
    suite_root(root).mkdir(parents=True, exist_ok=True)
    out = root / f"run-bundle-{now_stamp()}.zip"
    own_log.emit(f"[COLLECT] Building run diagnostic bundle: {rel(root, out)}")
    scan_and_cache_tools(root, log=own_log)

    copied_entries: list[dict[str, Any]] = []
    used_archives: set[str] = set()
    seen_sources: set[str] = set()
    log_paths: list[Path] = []
    system_probe = _system_probe(root)
    plugin_routes = _plugin_route_dump(root)
    health_bundle = _collect_diagnostics_status_cache(
        root,
        system_probe=system_probe,
        plugin_routes=plugin_routes,
        log=own_log,
    )

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        _copy_tree(
            zf,
            root,
            root / "NewEngine" / "neocore2" / "logs" / "run",
            archive_root="logs/run",
            category="logs",
            used_archives=used_archives,
            copied_entries=copied_entries,
            seen_sources=seen_sources,
            log_paths=log_paths,
        )
        _copy_tree(
            zf,
            root,
            root / "logs" / "run",
            archive_root="logs/root-run",
            category="logs",
            used_archives=used_archives,
            copied_entries=copied_entries,
            seen_sources=seen_sources,
            log_paths=log_paths,
        )
        for name in ["newengine.log", "game-ready-early.log", "platform-host-early.log", "winit-early.log"]:
            for base, archive_root in [(root / "NewEngine" / "neocore2", "logs/early"), (root, "logs/root")]:
                path = base / name
                if _write_file(
                    zf,
                    root,
                    path,
                    archive_name=f"{archive_root}/{name}",
                    category="logs",
                    used_archives=used_archives,
                    copied_entries=copied_entries,
                    seen_sources=seen_sources,
                ):
                    log_paths.append(path)
        _, profiler_index = _collect_profiler_data(
            zf,
            root,
            used_archives=used_archives,
            copied_entries=copied_entries,
            seen_sources=seen_sources,
        )
        _collect_latest_build_log(
            zf,
            root,
            used_archives=used_archives,
            copied_entries=copied_entries,
            seen_sources=seen_sources,
        )
        status_cache_index = _collect_status_cache_data(
            zf,
            root,
            used_archives=used_archives,
            copied_entries=copied_entries,
            seen_sources=seen_sources,
        )
        config_sources = [
            (tool_cache_dir(root) / "tool-registry.json", "config/tool-registry.json"),
            (root / "NewEngine" / "neocore2" / "config.json", "config/neocore2-config.json"),
            (root / "config.json", "config/root-config.json"),
        ]
        for path, archive_name in config_sources:
            _write_file(
                zf,
                root,
                path,
                archive_name=archive_name,
                category="config",
                used_archives=used_archives,
                copied_entries=copied_entries,
                seen_sources=seen_sources,
            )

        report_payload = build_run_report_payload(
            root,
            bundle_name=out.name,
            copied_entries=[entry for entry in copied_entries if entry.get("copied")],
            log_paths=log_paths,
            profiler_index=profiler_index,
            system_probe=system_probe,
            plugin_routes=plugin_routes,
            health_bundle=health_bundle,
            status_cache_index=status_cache_index,
        )
        cleanup_result = _clean_bundle_cache_roots(root, _bundle_cache_cleanup_roots(root), own_log)
        report_payload["cache_cleanup"] = cleanup_result
        zf.writestr("REPORT.md", render_report_markdown(report_payload))
        _write_json_to_zip(zf, "generated/RUN_REPORT.json", report_payload)
        _write_json_to_zip(zf, "generated/plugin-route-dump.json", plugin_routes)
        _write_json_to_zip(zf, "generated/system-probe.json", system_probe)
        _write_json_to_zip(zf, "generated/profiler-data-index.json", profiler_index)
        _write_json_to_zip(zf, "generated/status-cache-index.json", status_cache_index)
        _write_json_to_zip(zf, "generated/health-bundle.json", health_bundle)
        _write_json_to_zip(zf, "generated/post-bundle-cache-cleanup.json", cleanup_result)
        _write_json_to_zip(zf, "generated/bundle-manifest.json", {
            "schema": "takesome.runBundle.v3",
            "generated_utc": utc_iso(),
            "root": root.name,
            "report": "REPORT.md",
            "copied_files": len([entry for entry in copied_entries if entry.get("copied")]),
            "categories": report_payload.get("counts", {}).get("categories", {}),
            "status_cache": status_cache_index,
            "health": {
                "workspace_health": health_bundle.get("workspace_health", ""),
                "recommended_next": health_bundle.get("recommended_next", ""),
            },
            "cache_cleanup": cleanup_result,
        })
    own_log.emit(f"[OK] Run bundle written: {rel(root, out)}")
    own_log.emit(f"[INFO] Root report: REPORT.md")
    own_log.emit(f"[INFO] Profiler files included: {profiler_index.get('copied_files', 0)}")
    own_log.emit(f"[INFO] Bundle size: {out.stat().st_size} bytes")
    return 0 if int(cleanup_result.get("warnings", 0) or 0) == 0 else 1
