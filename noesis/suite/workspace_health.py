from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .paths import now_stamp, rel, suite_path, suite_root, utc_iso


QUALITY_LOC_LIMIT = 550


_WARN_PASS_MAP: dict[str, tuple[str, str]] = {
    "plugin_rebuild": (
        "P0_REBUILD_ACTIVE_PROVIDER_ARTIFACTS",
        "Rebuild/sync active profile artifacts until plugin matrix reports need_rebuild=0.",
    ),
    "dataset_missing": (
        "P0_DATASET_INDEX_REBUILD",
        "Re-run dataset lifecycle/entry-value indexing and regenerate cell catalog.",
    ),
    "reference_completeness": (
        "P0_REFERENCE_SCANNER_CONTRACT_FIX",
        "Repair reference completeness scanner token/contract so it reports real architecture gaps.",
    ),
    "legacy_false_positive": (
        "P0_INVARIANT_FALSE_POSITIVE_OR_CLEANUP_PASS",
        "Keep canonical extensions allowlisted while legacy tool identities remain denied.",
    ),
    "heartbeat_missing": (
        "P0_BUILD_HEARTBEAT_WATCHDOG",
        "Build process execution must emit liveness heartbeat instead of relying on hard timeout.",
    ),
    "root_noise": (
        "P0_ROOT_NOISE_REHOME",
        "Move generated build/incident logs from source root into suite reports/incidents/buildLog.",
    ),
    "suite_sprawl": (
        "P1_SUITE_ROOT_GROUPING",
        "Group ad-hoc patch scripts, reports and caches into typed Suite subdirectories.",
    ),
    "oversized_module": (
        "P1_TOOLING_MODULE_SPLIT_LEDGER",
        "Split large tooling modules or add explicit ownership/debt ledger entries.",
    ),
    "compiler_warning": (
        "P1_COMPILER_WARNING_LEDGER",
        "Convert compiler warnings into tracked cleanup actions when they indicate dead code or drift.",
    ),
    "redundant_patches": (
        "P1_PATCH_ARTIFACT_ARCHIVE",
        "Move one-off patch scripts from suite root into patch-backups/archive with index entries.",
    ),
    "quality_signal": (
        "P1_BUILD_HEALTH_LOGIC_WARNINGS",
        "Treat build health as compiler + diagnostics + architecture + dataset + hygiene signals.",
    ),
}


def _read_text(path: Path, *, limit: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if limit is not None and len(text) > limit:
        return text[-limit:]
    return text


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _json_inline(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _table_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _warn(warn_id: str, category: str, problem: str, impact: str) -> dict[str, str]:
    pass_id, fix = _WARN_PASS_MAP[category]
    return {
        "warn_id": warn_id,
        "category": category,
        "problem": problem,
        "impact": impact,
        "next_pass": pass_id,
        "recommended_fix": fix,
    }


def _latest_run(root: Path, action_prefix: str) -> Path | None:
    runs = suite_path(root, "suite", "runs")
    if not runs.exists():
        return None
    matches = sorted(runs.glob(f"{action_prefix}-*/result.json"), key=lambda p: p.stat().st_mtime if p.exists() else 0)
    return matches[-1] if matches else None


def _collect_plugin_status(root: Path) -> dict[str, Any]:
    status = _read_json(suite_path(root, "build-state", "plugin-status-latest.json"))
    records = status.get("records") if isinstance(status.get("records"), list) else []
    summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    ready = [r for r in records if isinstance(r, dict) and r.get("up_to_date")]
    need = [r for r in records if isinstance(r, dict) and r.get("needs_rebuild")]
    codecs = [r for r in records if isinstance(r, dict) and r.get("kind") == "codec-worker"]
    plugins = [r for r in records if isinstance(r, dict) and r.get("kind") == "plugin"]
    return {
        "source": rel(root, suite_path(root, "build-state", "plugin-status-latest.json")),
        "build_type": status.get("build_type", "unknown"),
        "platform": status.get("platform", "unknown"),
        "summary": summary,
        "records": records,
        "ready": ready,
        "need_rebuild": need,
        "plugins": plugins,
        "codecs": codecs,
    }


def _collect_dataset_pressure(root: Path) -> dict[str, Any]:
    cell_catalog = _read_json(suite_path(root, "dataSet", "index", "cell-catalog.json"))
    warn_ledger = suite_path(root, "dataSet", "index", "WARN_LEDGER.md")
    warn_text = _read_text(warn_ledger)
    warn_ids = sorted(set(re.findall(r"WARN-[A-Z0-9-]+", warn_text)))
    top_actions = cell_catalog.get("top_recommended_actions") or []
    return {
        "source": rel(root, suite_path(root, "dataSet", "index", "cell-catalog.json")),
        "cell_count": cell_catalog.get("cell_count"),
        "value_level_counts": cell_catalog.get("value_level_counts") or {},
        "top_domains_by_cell_count": cell_catalog.get("top_domains_by_cell_count") or [],
        "top_capability_candidates": cell_catalog.get("top_capability_candidates") or [],
        "top_recommended_actions": top_actions,
        "warn_ids": warn_ids,
        "warn_ledger": rel(root, warn_ledger),
        "catalog_exists": bool(cell_catalog),
    }


def _collect_diagnostics(root: Path) -> dict[str, Any]:
    logs_py = root / "tools" / "scripts" / "takesome" / "logs.py"
    logs_text = _read_text(logs_py)
    heartbeat_ok = "[ALIVE] process heartbeat" in logs_text and "threading.Thread" in logs_text and "queue.Queue" in logs_text

    legacy_scan_py = root / "tools" / "scripts" / "takesome" / "tools" / "legacy_scan.py"
    legacy_text = _read_text(legacy_scan_py)
    package_extension_allow_ok = 'replace(".nepak", "")' in legacy_text or "replace('.nepak', '')" in legacy_text

    reference_run = _latest_run(root, "diag.reference.completeness")
    reference_status = "unknown"
    reference_summary = "no reference completeness run found"
    if reference_run is not None:
        data = _read_json(reference_run)
        exit_code = data.get("result", {}).get("exit_code") if isinstance(data.get("result"), dict) else data.get("exit_code")
        stdout = data.get("result", {}).get("stdout", "") if isinstance(data.get("result"), dict) else ""
        reference_status = "ok" if exit_code == 0 else "fail"
        lines = [line for line in str(stdout).splitlines() if line.strip()]
        reference_summary = lines[-1] if lines else f"exit_code={exit_code}"

    invariant_run = _latest_run(root, "diag.invariants")
    invariant_status = "unknown"
    invariant_summary = "no invariant run found"
    if invariant_run is not None:
        data = _read_json(invariant_run)
        exit_code = data.get("result", {}).get("exit_code") if isinstance(data.get("result"), dict) else data.get("exit_code")
        stdout = data.get("result", {}).get("stdout", "") if isinstance(data.get("result"), dict) else ""
        invariant_status = "ok" if exit_code == 0 else "fail"
        lines = [line for line in str(stdout).splitlines() if line.strip()]
        invariant_summary = lines[-1] if lines else f"exit_code={exit_code}"

    return {
        "heartbeat_ok": heartbeat_ok,
        "heartbeat_source": rel(root, logs_py),
        "legacy_package_extension_false_positive_fixed": package_extension_allow_ok,
        "legacy_source": rel(root, legacy_scan_py),
        "reference_status": reference_status,
        "reference_summary": reference_summary,
        "reference_run": rel(root, reference_run) if reference_run else "",
        "invariant_status": invariant_status,
        "invariant_summary": invariant_summary,
        "invariant_run": rel(root, invariant_run) if invariant_run else "",
    }


def _collect_workspace_hygiene(root: Path) -> dict[str, Any]:
    root_entries = []
    root_noise = []
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if path.name.startswith(".git"):
            continue
        kind = "dir" if path.is_dir() else "file"
        root_entries.append({"name": path.name, "kind": kind})
        if path.is_file() and (path.name.startswith("buildERR") or path.name.startswith("lastbuild") or path.name.startswith("last-incident")):
            root_noise.append(path.name)

    top_entries = []
    suite = suite_root(root)
    if suite.exists():
        for path in sorted(suite.iterdir(), key=lambda p: p.name.lower()):
            files = 0
            dirs = 0
            if path.is_dir():
                try:
                    for _dp, dn, fs in path.walk():
                        dirs += len(dn)
                        files += len(fs)
                        if files > 100_000:
                            break
                except OSError:
                    pass
            top_entries.append({"name": path.name, "kind": "dir" if path.is_dir() else "file", "files": files, "dirs": dirs})

    patch_scripts = sorted(p.name for p in suite.glob("patch*.py")) if suite.exists() else []
    return {
        "repo_root": str(root.resolve()),
        "suite_root": str(suite.resolve()),
        "root_entries": root_entries,
        "root_noise": root_noise,
        "suite_top_entries": top_entries,
        "suite_top_count": len(top_entries),
        "patch_scripts": patch_scripts,
    }


def _collect_optimization(root: Path) -> dict[str, Any]:
    oversized: list[dict[str, Any]] = []
    scripts = root / "tools" / "scripts"
    if scripts.exists():
        for path in scripts.rglob("*.py"):
            if any(part in {"__pycache__", "target", ".git"} for part in path.parts):
                continue
            try:
                loc = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                continue
            if loc > QUALITY_LOC_LIMIT:
                oversized.append({"path": rel(root, path), "loc": loc})
    oversized.sort(key=lambda item: (-int(item["loc"]), item["path"]))

    warning_counter: Counter[str] = Counter()
    warning_samples: list[str] = []
    for log_path in (suite_path(root, "buildLog", "plugin-sync-latest.log"), root / "lastbuild-all.log"):
        text = _read_text(log_path, limit=120_000)
        for line in text.splitlines():
            if "warning:" in line.lower():
                label = line.strip()
                warning_counter[label] += 1
                if len(warning_samples) < 20:
                    warning_samples.append(label)

    hygiene = _collect_workspace_hygiene(root)
    return {
        "oversized_modules": oversized,
        "warning_count": sum(warning_counter.values()),
        "warning_samples": warning_samples,
        "redundant_patch_scripts": hygiene["patch_scripts"],
    }


def _derive_warnings(plugin: dict[str, Any], dataset: dict[str, Any], diagnostics: dict[str, Any], hygiene: dict[str, Any], optimization: dict[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if plugin["need_rebuild"]:
        warnings.append(_warn(
            "WARN-BUILD-0001",
            "plugin_rebuild",
            f"{len(plugin['need_rebuild'])} active plugin/codec artifacts need rebuild.",
            "Runtime provider graph may not represent active profile truth.",
        ))
    if not dataset["catalog_exists"]:
        warnings.append(_warn(
            "WARN-DATASET-0001",
            "dataset_missing",
            "Dataset cell catalog is missing or unreadable.",
            "Dataset as Truth Host cannot guide build/architecture health.",
        ))
    if not diagnostics["heartbeat_ok"]:
        warnings.append(_warn(
            "WARN-DIAG-0001",
            "heartbeat_missing",
            "Build process runner does not expose heartbeat reader-thread proof.",
            "Long builds can look dead or be killed by request timeout semantics.",
        ))
    if not diagnostics["legacy_package_extension_false_positive_fixed"]:
        warnings.append(_warn(
            "WARN-LEGACY-0001",
            "legacy_false_positive",
            "Legacy scanner may still treat canonical `.nepak` extension as a legacy tool identity.",
            "False positives can block build preflight and hide real legacy violations.",
        ))
    if diagnostics["reference_status"] == "fail":
        warnings.append(_warn(
            "WARN-REFERENCE-0001",
            "reference_completeness",
            f"Reference completeness scan is failing: {diagnostics['reference_summary']}",
            "Reference/dataset parity map cannot be trusted as a roadmap input.",
        ))
    if hygiene["root_noise"]:
        warnings.append(_warn(
            "WARN-WORKSPACE-0001",
            "root_noise",
            f"Source root contains generated logs/incidents: {', '.join(hygiene['root_noise'][:8])}.",
            "Source root stops being a clean EngineRepository contract.",
        ))
    if hygiene["suite_top_count"] > 20:
        warnings.append(_warn(
            "WARN-WORKSPACE-0002",
            "suite_sprawl",
            f"Suite root has {hygiene['suite_top_count']} top-level entries.",
            "Operational state is becoming hard to navigate and reason about.",
        ))
    if optimization["oversized_modules"]:
        top = optimization["oversized_modules"][0]
        warnings.append(_warn(
            "WARN-QUALITY-0001",
            "oversized_module",
            f"Oversized tooling module: {top['path']} has {top['loc']} LOC.",
            "Tooling risks becoming god-object shaped and harder to audit.",
        ))
    if optimization["warning_count"]:
        warnings.append(_warn(
            "WARN-COMPILER-0001",
            "compiler_warning",
            f"Recent build logs contain {optimization['warning_count']} compiler warning line(s).",
            "Compiler warnings may signal dead code, drift or incomplete feature integration.",
        ))
    if len(optimization["redundant_patch_scripts"]) >= 3:
        warnings.append(_warn(
            "WARN-WORKSPACE-0003",
            "redundant_patches",
            f"Suite root contains {len(optimization['redundant_patch_scripts'])} ad-hoc patch script(s).",
            "Patch artifacts add noise and duplicate operational history outside incident/archive structure.",
        ))
    warnings.append(_warn(
        "WARN-QUALITY-0002",
        "quality_signal",
        "Build health must not rely only on compiler warnings.",
        "A bad architectural or operational decision can compile successfully.",
    ))
    return warnings


def _status_icon(ok: bool) -> str:
    return "✅" if ok else "⚠️"


def _render_markdown(payload: dict[str, Any]) -> str:
    plugin = payload["plugin_status"]
    dataset = payload["dataset_pressure"]
    diagnostics = payload["diagnostics"]
    hygiene = payload["workspace_hygiene"]
    optimization = payload["optimization"]
    warnings = payload["warnings"]

    plugin_ok = not plugin["need_rebuild"] and bool(plugin["records"])
    dataset_ok = bool(dataset["catalog_exists"])
    diagnostics_ok = diagnostics["heartbeat_ok"] and diagnostics["legacy_package_extension_false_positive_fixed"] and diagnostics["reference_status"] != "fail"
    hygiene_ok = not hygiene["root_noise"] and hygiene["suite_top_count"] <= 20
    optimization_ok = not optimization["oversized_modules"] and optimization["warning_count"] == 0 and len(optimization["redundant_patch_scripts"]) < 3

    md: list[str] = []
    md.append(f"# 🧭 Build Health Report — {payload['generated_at']}\n\n")
    md.append("> [!INFO] INFO BLOCK — report contract\n")
    md.append("> **У нас сейчас:** этот отчёт объединяет build truth, dataset pressure, diagnostics, workspace hygiene и logic/optimization WARNs.\n>\n")
    md.append("> **Technical details (EN):** generated by `takesome.py workspace-health` / SuiteAction `workspace.health`; output schema `northstar.workspace.health.v1`.\n\n")

    md.append("## ✨ MD Summary\n\n")
    md.append("| Area | Status | Signal |\n|---|---|---|\n")
    md.append(f"| 🔌 Plugin/Codec Status | {_status_icon(plugin_ok)} | active profile `{plugin['build_type']}` / `{plugin['platform']}`, ready `{len(plugin['ready'])}`, need rebuild `{len(plugin['need_rebuild'])}` |\n")
    md.append(f"| 📚 Dataset Pressure | {_status_icon(dataset_ok)} | cells `{dataset.get('cell_count')}`, levels `{_table_escape(_json_inline(dataset.get('value_level_counts')))} ` |\n")
    md.append(f"| 🩺 Diagnostics | {_status_icon(diagnostics_ok)} | heartbeat `{diagnostics['heartbeat_ok']}`, legacy `.nepak` allow `{diagnostics['legacy_package_extension_false_positive_fixed']}`, reference `{diagnostics['reference_status']}` |\n")
    md.append(f"| 🧹 Workspace Hygiene | {_status_icon(hygiene_ok)} | root noise `{len(hygiene['root_noise'])}`, suite top-level `{hygiene['suite_top_count']}` |\n")
    md.append(f"| 🚀 Optimization Ideas | {_status_icon(optimization_ok)} | oversized modules `{len(optimization['oversized_modules'])}`, compiler warning lines `{optimization['warning_count']}`, patch scripts `{len(optimization['redundant_patch_scripts'])}` |\n\n")

    md.append("## 🤖 LLM Analysis\n\n")
    md.append("North Star build health should be read as an architecture signal, not just a compiler signal. A clean compiler result proves syntax/type correctness; it does not prove provider readiness, dataset truth freshness, workspace hygiene, scanner correctness or runtime replacement safety. ")
    if plugin_ok:
        md.append("The active provider layer is currently healthy: plugin/codec artifacts are ready for the selected profile. ")
    else:
        md.append("The active provider layer is not fully healthy: at least one plugin/codec artifact still needs rebuild, so runtime truth may differ from source intent. ")
    if dataset_ok:
        md.append("Dataset pressure is available and should be used as context for next passes, not as direct implementation authority. ")
    else:
        md.append("Dataset pressure is unavailable; roadmap decisions should not claim dataset support until the catalog is rebuilt. ")
    if not hygiene_ok:
        md.append("Workspace hygiene needs attention because operational noise in source root or suite root makes diagnostics harder to trust. ")
    if optimization["oversized_modules"]:
        md.append("Oversized tooling modules are the strongest maintainability risk; they should be split or explicitly tracked as debt. ")
    md.append("\n\n")

    md.append("## 1. 🔌 Plugin/Codec Status\n\n")
    md.append(f"- **Active profile:** `{plugin['build_type']}`\n")
    md.append(f"- **Platform:** `{plugin['platform']}`\n")
    md.append(f"- **Summary:** `{_json_inline(plugin['summary'])}`\n")
    md.append(f"- **Plugins:** `{len(plugin['plugins'])}`\n")
    md.append(f"- **Codecs:** `{len(plugin['codecs'])}`\n")
    md.append(f"- **Ready/up-to-date:** `{len(plugin['ready'])}`\n")
    md.append(f"- **Need rebuild/stale:** `{len(plugin['need_rebuild'])}`\n\n")
    if plugin["records"]:
        md.append("| Name | Kind | Status | Reason |\n|---|---|---|---|\n")
        for record in plugin["records"]:
            name = record.get("name") or record.get("display_name") or record.get("package_name")
            md.append(f"| `{_table_escape(name)}` | `{record.get('kind')}` | `{record.get('status')}` | {_table_escape(record.get('reason', ''))} |\n")
        md.append("\n")

    md.append("## 2. 📚 Dataset Pressure\n\n")
    md.append(f"- **Entry-value cells:** `{dataset.get('cell_count')}`\n")
    levels = dataset.get("value_level_counts") or {}
    md.append(f"- **Value levels:** high `{levels.get('high', 0)}`, medium `{levels.get('medium', 0)}`, low `{levels.get('low', 0)}`\n")
    md.append(f"- **WARNs generated:** `{len(dataset.get('warn_ids') or [])}`\n")
    md.append(f"- **WARN ledger:** `{dataset.get('warn_ledger')}`\n\n")
    md.append("### Top dataset domains\n\n| Domain | Cells |\n|---|---:|\n")
    for dom, count in (dataset.get("top_domains_by_cell_count") or [])[:12]:
        md.append(f"| `{dom}` | {count} |\n")
    md.append("\n### Next passes recommended by dataset pressure\n\n| Action | Cells |\n|---|---:|\n")
    for action, count in (dataset.get("top_recommended_actions") or [])[:12]:
        md.append(f"| `{action}` | {count} |\n")
    md.append("\n")

    md.append("## 3. 🩺 Diagnostics\n\n")
    md.append("| Diagnostic | Status | Evidence |\n|---|---|---|\n")
    md.append(f"| Heartbeat check | {_status_icon(diagnostics['heartbeat_ok'])} | `{diagnostics['heartbeat_source']}` |\n")
    md.append(f"| Legacy `.nepak` false-positive guard | {_status_icon(diagnostics['legacy_package_extension_false_positive_fixed'])} | `{diagnostics['legacy_source']}` |\n")
    md.append(f"| Reference completeness | {_status_icon(diagnostics['reference_status'] != 'fail')} `{diagnostics['reference_status']}` | {_table_escape(diagnostics['reference_summary'])} |\n")
    md.append(f"| P0 invariants | {_status_icon(diagnostics['invariant_status'] != 'fail')} `{diagnostics['invariant_status']}` | {_table_escape(diagnostics['invariant_summary'])} |\n\n")

    md.append("## 4. 🧹 Workspace Hygiene\n\n")
    md.append(f"- **Repository root:** `{hygiene['repo_root']}`\n")
    md.append(f"- **Suite root:** `{hygiene['suite_root']}`\n")
    md.append(f"- **Root noise candidates:** `{len(hygiene['root_noise'])}` — `{', '.join(hygiene['root_noise'])}`\n")
    md.append(f"- **Suite top-level entries:** `{hygiene['suite_top_count']}`\n\n")
    md.append("| Suite entry | Kind | Files sampled | Dirs sampled |\n|---|---|---:|---:|\n")
    for entry in hygiene["suite_top_entries"]:
        md.append(f"| `{entry['name']}` | `{entry['kind']}` | {entry['files']} | {entry['dirs']} |\n")
    md.append("\n")

    md.append("## 5. 🚀 Ideas for Optimization\n\n")
    md.append("### Oversized modules\n\n| Module | LOC |\n|---|---:|\n")
    for item in optimization["oversized_modules"][:20]:
        md.append(f"| `{item['path']}` | {item['loc']} |\n")
    if not optimization["oversized_modules"]:
        md.append("| none | 0 |\n")
    md.append("\n### Compiler warning samples\n\n")
    if optimization["warning_samples"]:
        for sample in optimization["warning_samples"][:20]:
            md.append(f"- `{_table_escape(sample)}`\n")
    else:
        md.append("- none\n")
    md.append("\n### Redundant patch scripts\n\n")
    if optimization["redundant_patch_scripts"]:
        for name in optimization["redundant_patch_scripts"]:
            md.append(f"- `{name}`\n")
    else:
        md.append("- none\n")
    md.append("\n")

    md.append("## ⚠️ WARN Ledger — WARN → P0/P1 Pass\n\n")
    md.append("| WARN ID | Problem | Impact | Next pass | Recommended fix |\n|---|---|---|---|---|\n")
    for warn in warnings:
        md.append(f"| `{warn['warn_id']}` | {_table_escape(warn['problem'])} | {_table_escape(warn['impact'])} | `{warn['next_pass']}` | {_table_escape(warn['recommended_fix'])} |\n")
    md.append("\n## ✅ Acceptance checklist\n\n")
    md.append("```text\n")
    md.append("[ ] Plugin/codec status is ready for active profile.\n")
    md.append("[ ] Dataset pressure is readable and current.\n")
    md.append("[ ] Heartbeat/liveness is present for long-running builds.\n")
    md.append("[ ] Legacy scanner does not confuse canonical formats with legacy tools.\n")
    md.append("[ ] Reference completeness scanner reports real gaps, not scanner contract failure.\n")
    md.append("[ ] Root noise is rehomed into Suite state.\n")
    md.append("[ ] Oversized modules are split or tracked.\n")
    md.append("[ ] Compiler warnings are converted into cleanup ledger entries.\n")
    md.append("```\n")
    return "".join(md)


def generate_workspace_health(root: Path) -> dict[str, Any]:
    root = root.resolve()
    generated_at = utc_iso()
    plugin = _collect_plugin_status(root)
    dataset = _collect_dataset_pressure(root)
    diagnostics = _collect_diagnostics(root)
    hygiene = _collect_workspace_hygiene(root)
    optimization = _collect_optimization(root)
    warnings = _derive_warnings(plugin, dataset, diagnostics, hygiene, optimization)
    payload: dict[str, Any] = {
        "schema": "northstar.workspace.health.v1",
        "generated_at": generated_at,
        "repo_root": str(root),
        "suite_root": str(suite_root(root)),
        "plugin_status": plugin,
        "dataset_pressure": dataset,
        "diagnostics": diagnostics,
        "workspace_hygiene": hygiene,
        "optimization": optimization,
        "warnings": warnings,
    }
    payload["markdown"] = _render_markdown(payload)
    return payload


def workspace_health_command(root: Path, args: Any | None = None) -> int:
    payload = generate_workspace_health(root)
    reports = suite_path(root, "reports")
    reports.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    latest_md = reports / "build-health-latest.md"
    stamped_md = reports / f"build-health-{stamp}.md"
    latest_json = reports / "build-health-latest.json"
    stamped_json = reports / f"build-health-{stamp}.json"

    markdown = str(payload.pop("markdown"))
    latest_md.write_text(markdown, encoding="utf-8")
    stamped_md.write_text(markdown, encoding="utf-8")
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    stamped_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    warn_count = len(payload.get("warnings") or [])
    print(f"[OK] Workspace health report: {latest_md}")
    print(f"[OK] Workspace health JSON:   {latest_json}")
    print(f"[INFO] Warnings: {warn_count}")
    return 0
