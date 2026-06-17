from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..paths import rel, suite_path, utc_iso

_MAX_SAMPLE_CHARS = 220
_TIMESTAMP_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}(?:\.\d+)?\]\s*")
_LEVEL_RE = re.compile(r"\[(ERROR|WARN|INFO|DEBUG|TRACE)\]")
_WIN_REPO_RE = re.compile(r"[A-Za-z]:[\\/][^\n\r'\"`]*?NorthStar-Engine[\\/]?", re.IGNORECASE)
_LONG_PATH_RE = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][^\s'\"`|]+){4,}")
_NUMBER_NOISE_RE = re.compile(
    r"\b(?:frame|next_frame|frame_id|raw_delta_ns|clamped_ns|accumulator_ns|payload_bytes|output_bytes|elapsed_ms|started_unix_ms|ended_unix_ms|at_unix_ms|shader_id|job_id)=['\"]?[^\s'\"]+['\"]?"
)
_FLOAT_RE = re.compile(r"\b\d+\.\d+\b")
_BIG_INT_RE = re.compile(r"\b\d{3,}\b")
_WS_RE = re.compile(r"\s+")


def compact_path(root: Path, value: str | Path | None) -> str:
    if value is None:
        return ""
    text = str(value).replace("\\", "/")
    if not text:
        return ""
    root_text = str(root).replace("\\", "/")
    if root_text and text.lower().startswith(root_text.lower()):
        text = "<repo>" + text[len(root_text):]
    text = _WIN_REPO_RE.sub("<repo>/", text)
    text = text.replace("//", "/")
    if text.startswith("<repo>//"):
        text = "<repo>/" + text[len("<repo>//"):]
    if len(text) <= 90:
        return text
    parts = [part for part in text.split("/") if part]
    if text.startswith("<repo>") and len(parts) > 4:
        return "<repo>/.../" + "/".join(parts[-3:])
    if len(parts) > 3:
        prefix = "" if not text.startswith("/") else "/"
        return prefix + ".../" + "/".join(parts[-3:])
    return text[-90:]


def compact_text(root: Path, text: str) -> str:
    text = text.replace("\\", "/")
    root_text = str(root).replace("\\", "/")
    if root_text:
        text = re.sub(re.escape(root_text), "<repo>", text, flags=re.IGNORECASE)
    text = _WIN_REPO_RE.sub("<repo>/", text)

    def shorten_match(match: re.Match[str]) -> str:
        raw = match.group(0)
        if "<repo>" in raw:
            return compact_path(root, raw)
        parts = [part for part in raw.replace("\\", "/").split("/") if part]
        if len(parts) <= 3:
            return raw
        return ".../" + "/".join(parts[-3:])

    text = _LONG_PATH_RE.sub(shorten_match, text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > _MAX_SAMPLE_CHARS:
        text = text[: _MAX_SAMPLE_CHARS - 1].rstrip() + "…"
    return text


def _fingerprint(root: Path, line: str) -> str:
    line = compact_text(root, _TIMESTAMP_RE.sub("", line.strip()))
    line = _NUMBER_NOISE_RE.sub("<n>", line)
    line = _FLOAT_RE.sub("<f>", line)
    line = _BIG_INT_RE.sub("<n>", line)
    line = re.sub(r"profiler-local-\d+", "profiler-local-<n>", line)
    line = re.sub(r"ShaderId\(\d+\)", "ShaderId(<n>)", line)
    return line.lower()


def _read_text(path: Path, *, max_bytes: int = 2_000_000) -> str:
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def summarize_logs(root: Path, log_paths: list[Path]) -> dict[str, Any]:
    level_counts: Counter[str] = Counter()
    grouped: dict[str, dict[str, Any]] = {}
    per_file: dict[str, Counter[str]] = defaultdict(Counter)
    file_samples: dict[str, list[str]] = defaultdict(list)
    processed = 0
    truncated = 0
    files_scanned = 0
    for path in log_paths:
        if not path.exists() or not path.is_file():
            continue
        text = _read_text(path)
        if not text:
            continue
        files_scanned += 1
        file_key = compact_path(root, rel(root, path))
        for raw in text.splitlines():
            if not raw.strip():
                continue
            processed += 1
            match = _LEVEL_RE.search(raw)
            level = match.group(1).lower() if match else "line"
            per_file[file_key][level] += 1
            if level in {"error", "warn"}:
                level_counts[level] += 1
            elif level == "info":
                level_counts[level] += 1
            if level not in {"error", "warn"}:
                continue
            fp = _fingerprint(root, raw)
            if not fp:
                continue
            sample = compact_text(root, _TIMESTAMP_RE.sub("", raw.strip()))
            if len(file_samples[file_key]) < 3:
                file_samples[file_key].append(sample)
            item = grouped.setdefault(fp, {"level": level, "count": 0, "sample": sample, "files": set()})
            item["count"] += 1
            item["files"].add(file_key)
        try:
            if path.stat().st_size > 2_000_000:
                truncated += 1
        except OSError:
            pass
    repeated = []
    for item in grouped.values():
        repeated.append({
            "level": item["level"],
            "count": item["count"],
            "sample": item["sample"],
            "files": sorted(item["files"]),
        })
    repeated.sort(key=lambda it: (it["level"] != "error", -int(it["count"]), it["sample"]))
    files = []
    for file_key, counts in per_file.items():
        files.append({
            "path": file_key,
            "errors": counts.get("error", 0),
            "warnings": counts.get("warn", 0),
            "infos": counts.get("info", 0),
            "lines": sum(counts.values()),
            "samples": file_samples.get(file_key, []),
        })
    files.sort(key=lambda it: (-int(it["errors"]), -int(it["warnings"]), it["path"]))
    return {
        "schema": "takesome.logSummary.v2",
        "files_scanned": files_scanned,
        "lines_scanned": processed,
        "large_files_truncated": truncated,
        "counts": dict(level_counts),
        "files": files[:20],
        "unique_error_warn_groups": len(repeated),
        "top_repeated_error_warn": repeated[:12],
        "latest_unique_error_warn": repeated[-12:] if repeated else [],
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _find_profiler_root(root: Path) -> Path | None:
    candidates = [
        root / "NewEngine" / "neocore2" / "cache" / "profiler",
        suite_path(root, "profiler"),
        suite_path(root, "reports", "profiler"),
    ]
    for path in candidates:
        if (path / "profiler_report_latest.json").exists() or (path / "profiler_top_offenders_latest.csv").exists():
            return path
    return None


def _csv_rows(path: Path, *, limit: int = 8) -> list[dict[str, str]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            return [dict(row) for _, row in zip(range(limit), reader)]
    except Exception:
        return []


def summarize_profiler(root: Path) -> dict[str, Any]:
    profiler_root = _find_profiler_root(root)
    if profiler_root is None:
        return {"available": False}
    report = _read_json(profiler_root / "profiler_report_latest.json")
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    top_rows = _csv_rows(profiler_root / "profiler_top_offenders_latest.csv", limit=6)
    budget_rows = _csv_rows(profiler_root / "profiler_budget_violations_latest.csv", limit=6)
    diagnostics_rows = _csv_rows(profiler_root / "profiler_diagnostics_latest.csv", limit=256)

    grouped_diag: Counter[tuple[str, str]] = Counter()
    for row in diagnostics_rows:
        code = row.get("code", "")
        msg = compact_text(root, row.get("message", ""))
        grouped_diag[(code, msg)] += 1
    diagnostics = [
        {"code": code, "count": count, "message": msg}
        for (code, msg), count in grouped_diag.most_common(8)
    ]

    top = []
    for row in top_rows:
        top.append({
            "rank": row.get("rank", ""),
            "category": row.get("category", ""),
            "source": row.get("source", ""),
            "sample": row.get("sample_name", ""),
            "count": row.get("count", ""),
            "avg_ms": row.get("average_elapsed_ms", ""),
            "max_ms": row.get("max_elapsed_ms", ""),
            "share_percent": row.get("total_share_percent", ""),
        })
    budget = []
    for row in budget_rows:
        budget.append({
            "rank": row.get("rank", ""),
            "category": row.get("category", ""),
            "source": row.get("source", ""),
            "name": row.get("name", ""),
            "elapsed_ms": row.get("elapsed_ms", ""),
            "budget_ms": row.get("budget_ms", ""),
            "load_percent": row.get("load_percent", ""),
        })
    return {
        "available": True,
        "root": compact_path(root, rel(root, profiler_root)),
        "total_jobs": summary.get("completed_jobs_kept", summary.get("total_jobs", "")),
        "failed_jobs": summary.get("failed_jobs", ""),
        "over_budget_jobs": summary.get("over_budget_jobs", ""),
        "slow_or_over_budget_jobs": summary.get("slow_or_over_budget_jobs", ""),
        "max_elapsed_ms": summary.get("max_elapsed_ms", ""),
        "p95_elapsed_ms": (summary.get("elapsed_percentiles_ms") or {}).get("p95", "") if isinstance(summary.get("elapsed_percentiles_ms"), dict) else "",
        "top_offenders": top,
        "budget_violations": budget,
        "diagnostics": diagnostics,
    }


def summarize_build(root: Path) -> dict[str, Any]:
    path = suite_path(root, "buildLog", "buildInfo.json")
    data = _read_json(path)
    latest = data.get("latest", {}) if isinstance(data.get("latest"), dict) else {}
    build_file = latest.get("build_file", {}) if isinstance(latest.get("build_file"), dict) else {}
    artifacts = latest.get("artifacts", []) if isinstance(latest.get("artifacts"), list) else []
    statuses: Counter[str] = Counter(str(item.get("status", "unknown")) for item in artifacts if isinstance(item, dict))
    return {
        "available": bool(latest),
        "started_utc": latest.get("started_utc", ""),
        "finished_utc": latest.get("finished_utc", ""),
        "build_type": latest.get("build_type", ""),
        "exit_code": latest.get("exit_code", ""),
        "artifact_count": latest.get("artifact_count", len(artifacts)),
        "artifact_statuses": dict(statuses),
        "build_file": compact_path(root, build_file.get("path", "")),
        "build_file_hash": str(build_file.get("sha256", ""))[:16],
        "artifacts": [
            {
                "name": item.get("display_name") or item.get("package_name") or Path(str(item.get("path", ""))).name,
                "kind": item.get("kind", ""),
                "status": item.get("status", ""),
                "hash": str(item.get("sha256", ""))[:16],
            }
            for item in artifacts[:12]
            if isinstance(item, dict)
        ],
    }




def _category_summary(copied_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for item in copied_entries:
        category = str(item.get("category", "files"))
        grouped[category]["files"] += 1
        grouped[category]["bytes"] += int(item.get("size_bytes", 0) or 0)
    rows = [
        {"category": category, "files": data["files"], "bytes": data["bytes"]}
        for category, data in grouped.items()
    ]
    rows.sort(key=lambda it: (-int(it["bytes"]), it["category"]))
    return rows


def _runtime_plugin_summary(root: Path, plugin_routes: dict[str, Any]) -> dict[str, Any]:
    installed = plugin_routes.get("installed_dlls", []) if isinstance(plugin_routes.get("installed_dlls"), list) else []
    by_extension: Counter[str] = Counter()
    by_bucket: Counter[str] = Counter()
    total_bytes = 0
    items: list[dict[str, Any]] = []
    for item in installed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        path = str(item.get("path", ""))
        ext = Path(name).suffix.lower() or "<none>"
        by_extension[ext] += 1
        parts = [part for part in path.replace("\\", "/").split("/") if part]
        bucket = "plugins"
        if "codecs" in parts:
            bucket = "codecs"
        elif "importers" in parts:
            bucket = "importers"
        elif "platforms" in parts:
            bucket = "platforms"
        by_bucket[bucket] += 1
        size = int(item.get("size", 0) or 0)
        total_bytes += size
        items.append({
            "name": name,
            "path": compact_path(root, path),
            "size_bytes": size,
            "sha256": str(item.get("sha256", ""))[:16],
            "bucket": bucket,
        })
    items.sort(key=lambda it: (it["bucket"], it["name"]))
    return {
        "installed_count": len(items),
        "total_bytes": total_bytes,
        "by_extension": dict(by_extension),
        "by_bucket": dict(by_bucket),
        "items": items[:24],
    }


def _source_roots_summary(root: Path, profiler_index: dict[str, Any]) -> dict[str, Any]:
    roots = profiler_index.get("roots", []) if isinstance(profiler_index.get("roots"), list) else []
    return {
        "profiler_roots": roots,
        "profiler_files": profiler_index.get("copied_files", 0),
        "cache_cleanup_roots": profiler_index.get("cache_cleanup_roots", []),
        "tool_cache": compact_path(root, rel(root, suite_path(root, "tools"))),
    }

def build_run_report_payload(
    root: Path,
    *,
    bundle_name: str,
    copied_entries: list[dict[str, Any]],
    log_paths: list[Path],
    profiler_index: dict[str, Any],
    system_probe: dict[str, Any],
    plugin_routes: dict[str, Any],
    health_bundle: dict[str, Any] | None = None,
    status_cache_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    categories: Counter[str] = Counter(str(item.get("category", "files")) for item in copied_entries)
    total_bytes = sum(int(item.get("size_bytes", 0) or 0) for item in copied_entries)
    largest = sorted(copied_entries, key=lambda item: int(item.get("size_bytes", 0) or 0), reverse=True)[:12]
    runtime_plugins = _runtime_plugin_summary(root, plugin_routes)
    health_bundle = health_bundle or {}
    status_cache_index = status_cache_index or {}
    return {
        "schema": "takesome.runReport.v3",
        "generated_utc": utc_iso(),
        "bundle": bundle_name,
        "root": root.name,
        "system": {
            "platform": system_probe.get("platform", ""),
            "machine": system_probe.get("machine", ""),
            "cargo_version": system_probe.get("cargo_version", ""),
            "python": str(system_probe.get("python", "")).split(" ")[0],
            "python_executable": system_probe.get("python_executable", ""),
            "cargo": system_probe.get("cargo", ""),
            "env": system_probe.get("env", {}),
        },
        "counts": {
            "copied_files": len(copied_entries),
            "total_bytes": total_bytes,
            "profiler_files": profiler_index.get("copied_files", 0),
            "installed_runtime_plugins": runtime_plugins.get("installed_count", 0),
            "categories": dict(categories),
        },
        "copied_files": {
            "category_summary": _category_summary(copied_entries),
            "largest": [
                {
                    "archive": item.get("archive", ""),
                    "source": compact_path(root, item.get("source", "")),
                    "size_bytes": item.get("size_bytes", 0),
                    "category": item.get("category", ""),
                }
                for item in largest
            ],
        },
        "source_roots": _source_roots_summary(root, profiler_index),
        "runtime_plugins": runtime_plugins,
        "health": health_bundle,
        "status_cache": status_cache_index,
        "build": summarize_build(root),
        "profiler": summarize_profiler(root),
        "logs": summarize_logs(root, log_paths),
        "included_largest_files": [
            {
                "archive": item.get("archive", ""),
                "source": compact_path(root, item.get("source", "")),
                "size_bytes": item.get("size_bytes", 0),
                "category": item.get("category", ""),
            }
            for item in largest
        ],
    }


def _fmt_ms(value: Any) -> str:
    try:
        return f"{float(value):.2f} ms"
    except Exception:
        return str(value) if value not in (None, "") else "n/a"


def _fmt_bytes(value: Any) -> str:
    try:
        raw = int(value)
    except Exception:
        return "n/a"
    units = ["B", "KB", "MB", "GB"]
    size = float(raw)
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{size:.1f} {unit}" if unit != "B" else f"{raw} B"


def render_report_markdown(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    build = payload.get("build", {})
    profiler = payload.get("profiler", {})
    logs = payload.get("logs", {})
    runtime_plugins = payload.get("runtime_plugins", {}) if isinstance(payload.get("runtime_plugins"), dict) else {}
    copied_files = payload.get("copied_files", {}) if isinstance(payload.get("copied_files"), dict) else {}
    source_roots = payload.get("source_roots", {}) if isinstance(payload.get("source_roots"), dict) else {}
    cache_cleanup = payload.get("cache_cleanup", {}) if isinstance(payload.get("cache_cleanup"), dict) else {}
    health = payload.get("health", {}) if isinstance(payload.get("health"), dict) else {}
    status_cache = payload.get("status_cache", {}) if isinstance(payload.get("status_cache"), dict) else {}
    log_counts = logs.get("counts", {}) if isinstance(logs.get("counts"), dict) else {}
    lines: list[str] = [
        "# North Star run report",
        "",
        "Главный отчёт bundle. Он короткий по намерению: детали лежат рядом в `generated/`, `logs/`, `profiler/`, `build/`.",
        "",
        "## Общие данные",
        "",
        "| Поле | Значение |",
        "|---|---|",
        f"| Bundle | `{payload.get('bundle', '')}` |",
        f"| Generated UTC | `{payload.get('generated_utc', '')}` |",
        f"| Workspace | `{payload.get('root', '')}` |",
        f"| Files included | `{counts.get('copied_files', 0)}` |",
        f"| Total raw size | `{_fmt_bytes(counts.get('total_bytes', 0))}` |",
        f"| Runtime plugins | `{counts.get('installed_runtime_plugins', 0)}` |",
        "",
        "## Быстрое состояние",
        "",
    ]
    if build.get("available"):
        build_state = "OK" if str(build.get("exit_code")) == "0" else "FAILED"
        lines.append(f"- Build: **{build_state}**, `{build.get('build_type', '')}`, artifacts `{build.get('artifact_count', 0)}`, hash `{build.get('build_file_hash', '')}`.")
    else:
        lines.append("- Build: данных о последней сборке нет в `.takesome/buildLog/buildInfo.json`.")
    if profiler.get("available"):
        lines.append(
            f"- Profiler: over-budget `{profiler.get('over_budget_jobs', 0)}`, failed `{profiler.get('failed_jobs', 0)}`, max `{_fmt_ms(profiler.get('max_elapsed_ms'))}`, p95 `{_fmt_ms(profiler.get('p95_elapsed_ms'))}`."
        )
    else:
        lines.append("- Profiler: latest profiler report не найден.")
    lines.append(f"- Logs: errors `{log_counts.get('error', 0)}`, warnings `{log_counts.get('warn', 0)}`, unique groups `{logs.get('unique_error_warn_groups', 0)}`.")
    lines.append(f"- Runtime plugins: `{runtime_plugins.get('installed_count', counts.get('installed_runtime_plugins', 0))}` installed, `{_fmt_bytes(runtime_plugins.get('total_bytes', 0))}` total.")
    if health:
        plugins = health.get("plugins", {}) if isinstance(health.get("plugins"), dict) else {}
        tools = health.get("tools", {}) if isinstance(health.get("tools"), dict) else {}
        engine = health.get("engine", {}) if isinstance(health.get("engine"), dict) else {}
        lines.append(f"- Workspace health: **{health.get('workspace_health', 'unknown')}**, next `{health.get('recommended_next', 'n/a')}`.")
        lines.append(f"- Plugin health: total `{plugins.get('total', 0)}`, ready `{plugins.get('up_to_date', 0)}`, stale `{plugins.get('need_rebuild', 0)}`, invalid `{plugins.get('invalid_metadata', 0)}`.")
        lines.append(f"- Tool health: registered `{tools.get('total', 0)}`, invalid `{tools.get('invalid', 0)}`.")
        lines.append(f"- Engine health: runtime libs `{engine.get('installed_dynamic_library_count', 0)}`, run logs `{engine.get('run_log_count', 0)}`, cache exists `{engine.get('cache_exists', False)}`.")
    if status_cache:
        lines.append(f"- Status cache: `{status_cache.get('snapshot_count', 0)}` latest snapshots, copied `{status_cache.get('copied_files', 0)}` file(s).")
    if cache_cleanup:
        lines.append(f"- Post-bundle cache cleanup: cleaned `{cache_cleanup.get('cleaned', 0)}`, skipped `{cache_cleanup.get('skipped', 0)}`, warnings `{cache_cleanup.get('warnings', 0)}`.")

    if health:
        lines.extend(["", "## Health snapshot", "", "| Area | State | Details |", "|---|---|---|"])
        context = health.get("context", {}) if isinstance(health.get("context"), dict) else {}
        plugins = health.get("plugins", {}) if isinstance(health.get("plugins"), dict) else {}
        tools = health.get("tools", {}) if isinstance(health.get("tools"), dict) else {}
        git = health.get("git", {}) if isinstance(health.get("git"), dict) else {}
        engine = health.get("engine", {}) if isinstance(health.get("engine"), dict) else {}
        incident = health.get("incident", {}) if isinstance(health.get("incident"), dict) else {}
        lines.append(f"| Suite context | `{context.get('profile', '')}` / `{context.get('platform', '')}` | source `{context.get('context_source', '')}` |")
        lines.append(f"| Workspace | `{health.get('workspace_health', '')}` | next `{health.get('recommended_next', '')}` |")
        lines.append(f"| Plugins/codecs | `{plugins.get('total', 0)}` total | ready `{plugins.get('up_to_date', 0)}`, stale `{plugins.get('need_rebuild', 0)}`, invalid `{plugins.get('invalid_metadata', 0)}` |")
        lines.append(f"| Tools | `{tools.get('total', 0)}` registered | invalid `{tools.get('invalid', 0)}` |")
        lines.append(f"| Git | `{'dirty' if git.get('dirty') else 'clean' if git.get('available') else 'unavailable'}` | changed `{git.get('changed_files', 0)}`, branch `{git.get('branch', '')}` |")
        lines.append(f"| Engine | `{'present' if engine.get('exists') else 'missing'}` | runtime libs `{engine.get('installed_dynamic_library_count', 0)}`, run logs `{engine.get('run_log_count', 0)}` |")
        lines.append(f"| Last incident | `{'yes' if incident.get('exists') else 'none'}` | {incident.get('kind', '')} `{incident.get('target', '')}` |")
        if isinstance(health.get("paths"), dict):
            lines.extend(["", "### Cached status artifacts", ""])
            for key, value in health.get("paths", {}).items():
                lines.append(f"- `{key}`: `{value}`")

    top = logs.get("top_repeated_error_warn", []) if isinstance(logs.get("top_repeated_error_warn"), list) else []
    lines.extend(["", "## Что смотреть первым", ""])
    if top:
        for item in top[:8]:
            level = str(item.get("level", "")).upper()
            count = item.get("count", 0)
            sample = item.get("sample", "")
            lines.append(f"- **{level} ×{count}** — {sample}")
    else:
        lines.append("- Крупных групп ERROR/WARN в собранных логах не найдено.")

    if build.get("available"):
        lines.extend([
            "",
            "## Последняя сборка",
            "",
            "| Поле | Значение |",
            "|---|---|",
            f"| Started | `{build.get('started_utc', '')}` |",
            f"| Finished | `{build.get('finished_utc', '')}` |",
            f"| Type | `{build.get('build_type', '')}` |",
            f"| Exit code | `{build.get('exit_code', '')}` |",
            f"| Build file | `{build.get('build_file', '')}` |",
        ])
        artifacts = build.get("artifacts", []) if isinstance(build.get("artifacts"), list) else []
        if artifacts:
            lines.extend(["", "| Artifact | Kind | Status | Hash |", "|---|---|---|---|"])
            for item in artifacts[:10]:
                lines.append(f"| `{item.get('name', '')}` | `{item.get('kind', '')}` | `{item.get('status', '')}` | `{item.get('hash', '')}` |")

    if profiler.get("available"):
        lines.extend(["", "## Profiler", "", "### Top offenders", "", "| Rank | Category | Source | Sample | Count | Avg | Max | Share |", "|---:|---|---|---|---:|---:|---:|---:|"])
        for row in profiler.get("top_offenders", [])[:6]:
            lines.append(
                f"| {row.get('rank', '')} | `{row.get('category', '')}` | `{row.get('source', '')}` | `{row.get('sample', '')}` | {row.get('count', '')} | {row.get('avg_ms', '')} | {row.get('max_ms', '')} | {row.get('share_percent', '')}% |"
            )
        budget = profiler.get("budget_violations", []) if isinstance(profiler.get("budget_violations"), list) else []
        if budget:
            lines.extend(["", "### Budget violations", "", "| Rank | Category | Source | Name | Elapsed | Budget | Load |", "|---:|---|---|---|---:|---:|---:|"])
            for row in budget[:6]:
                lines.append(
                    f"| {row.get('rank', '')} | `{row.get('category', '')}` | `{row.get('source', '')}` | `{row.get('name', '')}` | {row.get('elapsed_ms', '')} | {row.get('budget_ms', '')} | {row.get('load_percent', '')}% |"
                )
        diagnostics = profiler.get("diagnostics", []) if isinstance(profiler.get("diagnostics"), list) else []
        if diagnostics:
            lines.extend(["", "### Profiler diagnostics", ""])
            for item in diagnostics[:6]:
                lines.append(f"- `{item.get('code', '')}` ×{item.get('count', 0)} — {item.get('message', '')}")

    plugin_items = runtime_plugins.get("items", []) if isinstance(runtime_plugins.get("items"), list) else []
    if plugin_items:
        lines.extend(["", "## Runtime plugins", "", "| Plugin | Bucket | Size | Hash |", "|---|---|---:|---|"])
        for item in plugin_items[:14]:
            lines.append(f"| `{item.get('name', '')}` | `{item.get('bucket', '')}` | `{_fmt_bytes(item.get('size_bytes', 0))}` | `{item.get('sha256', '')}` |")

    profiler_roots = source_roots.get("profiler_roots", []) if isinstance(source_roots.get("profiler_roots"), list) else []
    cleanup_roots = source_roots.get("cache_cleanup_roots", []) if isinstance(source_roots.get("cache_cleanup_roots"), list) else []
    if profiler_roots or cleanup_roots:
        lines.extend(["", "## Source/cache roots", ""])
        if profiler_roots:
            lines.append("Profiler data copied from:")
            for root_item in profiler_roots:
                lines.append(f"- `{root_item}`")
        if cleanup_roots:
            lines.append("")
            lines.append("Cache roots scheduled for post-bundle cleanup:")
            for root_item in cleanup_roots:
                lines.append(f"- `{root_item}`")

    log_files = logs.get("files", []) if isinstance(logs.get("files"), list) else []
    if log_files:
        lines.extend(["", "## Log files by severity", "", "| Log | Errors | Warnings | Lines |", "|---|---:|---:|---:|"])
        for item in log_files[:10]:
            lines.append(f"| `{item.get('path', '')}` | {item.get('errors', 0)} | {item.get('warnings', 0)} | {item.get('lines', 0)} |")

    if cache_cleanup:
        lines.extend(["", "## Post-bundle cache cleanup", "", "| Path | Status | Message |", "|---|---|---|"])
        for item in cache_cleanup.get("items", [])[:10] if isinstance(cache_cleanup.get("items"), list) else []:
            lines.append(f"| `{item.get('path', '')}` | `{item.get('status', '')}` | {item.get('message', '')} |")

    lines.extend(["", "## Состав bundle", ""])
    category_summary = copied_files.get("category_summary", []) if isinstance(copied_files.get("category_summary"), list) else []
    if category_summary:
        lines.extend(["| Group | Files | Raw size |", "|---|---:|---:|"])
        for item in category_summary:
            lines.append(f"| `{item.get('category', '')}` | {item.get('files', 0)} | `{_fmt_bytes(item.get('bytes', 0))}` |")
    else:
        cats = counts.get("categories", {}) if isinstance(counts.get("categories"), dict) else {}
        if cats:
            lines.extend(["| Group | Files |", "|---|---:|"])
            for key, value in sorted(cats.items()):
                lines.append(f"| `{key}` | {value} |")
    largest = payload.get("included_largest_files", []) if isinstance(payload.get("included_largest_files"), list) else []
    if largest:
        lines.extend(["", "### Largest included files", "", "| File | Size | Group |", "|---|---:|---|"])
        for item in largest[:6]:
            lines.append(f"| `{item.get('archive', '')}` | `{_fmt_bytes(item.get('size_bytes', 0))}` | `{item.get('category', '')}` |")

    lines.extend([
        "",
        "## Где лежат детали",
        "",
        "- `generated/RUN_REPORT.json` — машинный вариант этого отчёта.",
        "- `logs/` — runtime/early logs без длинных repository prefixes.",
        "- `profiler/` — latest profiler artifacts, deduplicated by source path.",
        "- `build/` — latest buildInfo/log artifacts.",
        "- `config/` — runtime config snapshot.",
        "- `generated/health-bundle.json` — сводное состояние Suite context, plugins/codecs, tools, Git, incidents and engine runtime.",
        "- `generated/status-cache-index.json` — индекс сохранённых status snapshots.",
        "- `generated/status-cache/` — reusable JSON/MD snapshots from plugin checks, workspace registry, doctor, tools and engine health.",
        "- `generated/post-bundle-cache-cleanup.json` — результат очистки cache roots после упаковки данных.",
        "",
    ])
    return "\n".join(lines)
