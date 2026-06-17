from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .contracts import BridgeContext, BridgeError, MAX_SEARCH_FILE_BYTES
from .dataset_core import dataset_dirs, dataset_root, path_logic_signals, safe_extracted_path, score_file
from .paths import is_text_file, rel, slug


DOMAIN_RULES: dict[str, dict[str, Any]] = {
    "engine.ai": {
        "terms": ["ai", "agent", "behavior", "task", "planner", "decision", "perception", "brain"],
        "capabilities": ["ai.backend", "ai.patterns.utility_planner"],
        "providers": ["NullAI", "AiProvider"],
        "conformance": ["ai.provider.conformance"],
    },
    "engine.animation": {
        "terms": ["animation", "anim", "skeleton", "blend", "ik", "pose", "clip"],
        "capabilities": ["animation.backend", "animation.graph"],
        "providers": ["NullAnimation", "AnimationProvider"],
        "conformance": ["animation.provider.conformance"],
    },
    "engine.assets": {
        "terms": ["asset", "import", "resource", "texture", "model", "material", "codec", "listfile"],
        "capabilities": ["assets.vfs", "assets.listfile.nef8", "assets.import"],
        "providers": ["AssetProvider", "NullAssets"],
        "conformance": ["assets.provider.conformance"],
    },
    "engine.debug": {
        "terms": ["debug", "profiler", "trace", "diagnostic", "log", "telemetry"],
        "capabilities": ["debug.trace", "debug.diagnostics"],
        "providers": ["DebugProvider"],
        "conformance": ["diagnostics.conformance"],
    },
    "engine.input": {
        "terms": ["input", "keyboard", "mouse", "gamepad", "binding", "action"],
        "capabilities": ["input.backend", "input.bindings"],
        "providers": ["NullInput", "InputProvider"],
        "conformance": ["input.provider.conformance"],
    },
    "engine.physics": {
        "terms": ["physics", "collision", "rigid", "cloth", "vehicle", "constraint", "body"],
        "capabilities": ["physics.backend", "physics.contacts"],
        "providers": ["NullPhysics", "PhysicsProvider"],
        "conformance": ["physics.provider.conformance"],
    },
    "engine.render": {
        "terms": ["render", "shader", "lighting", "shadow", "vfx", "gpu", "material", "texture"],
        "capabilities": ["render.backend", "render.frame_graph", "render.diagnostics"],
        "providers": ["NullRenderer", "RenderProvider"],
        "conformance": ["render.provider.conformance"],
    },
    "engine.scene": {
        "terms": ["scene", "world", "entity", "component", "prefab", "streaming", "archetype"],
        "capabilities": ["scene.runtime", "world.streaming", "entity.lifecycle"],
        "providers": ["SceneProvider", "WorldProvider"],
        "conformance": ["scene.provider.conformance"],
    },
    "engine.ui": {
        "terms": ["ui", "frontend", "widget", "layout", "text", "menu", "panel"],
        "capabilities": ["ui.backend", "ui.text.shaping", "ui.debug.overlay"],
        "providers": ["NullUI", "UiProvider"],
        "conformance": ["ui.provider.conformance"],
    },
    "engine.scripting": {
        "terms": ["script", "vm", "binding", "event", "command", "lua", "python"],
        "capabilities": ["scripting.backend", "scripting.bindings"],
        "providers": ["NullScripting", "ScriptingProvider"],
        "conformance": ["scripting.provider.conformance"],
    },
}

TEXT_SAMPLE_LIMIT = 96
FILE_SAMPLE_LIMIT = 5000


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _iter_files(base: Path, max_files: int = FILE_SAMPLE_LIMIT) -> Iterable[Path]:
    count = 0
    for path in base.rglob("*") if base.is_dir() else [base]:
        if not path.is_file():
            continue
        yield path
        count += 1
        if count >= max_files:
            return


def _read_sample(path: Path) -> str:
    if not is_text_file(path) or path.stat().st_size > MAX_SEARCH_FILE_BYTES:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:8192]


def _score_domains(entry_rel: str, files: list[Path]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    scores: dict[str, int] = {domain: 0 for domain in DOMAIN_RULES}
    for path in files[:TEXT_SAMPLE_LIMIT]:
        sample = _read_sample(path)
        hay = f"{entry_rel}\n{path.name}\n{sample}".lower()
        matched_domains: list[str] = []
        for domain, rule in DOMAIN_RULES.items():
            hits = sum(hay.count(term) for term in rule["terms"])
            if hits:
                scores[domain] += hits
                matched_domains.append(domain)
        if matched_domains:
            evidence.append({
                "path": path.as_posix(),
                "domains": matched_domains[:8],
                "logic_score": score_file(path),
                "signals": path_logic_signals(path),
            })
    return {k: v for k, v in scores.items() if v > 0}, evidence[:50]


def _value_level(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 35:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def _dedupe(items: Iterable[str]) -> list[str]:
    return sorted({str(item) for item in items if str(item).strip()})


def analyze_extracted_entry(ctx: BridgeContext, base: Path, *, max_files: int = FILE_SAMPLE_LIMIT) -> Dict[str, Any]:
    if not base.exists():
        raise BridgeError("dataset entry does not exist", "not_found", {"path": str(base)})
    ds_root = dataset_root(ctx)
    entry_rel = rel(ds_root, base)
    files = list(_iter_files(base, max_files=max_files))
    ext = Counter((p.suffix.lower() or "<none>") for p in files)
    text_count = sum(1 for p in files if is_text_file(p))
    logic_scores = [score_file(p) for p in files]
    domain_scores, evidence = _score_domains(entry_rel, files)
    mapped_domains = [domain for domain, _ in sorted(domain_scores.items(), key=lambda kv: (-kv[1], kv[0]))]
    topic_tags = [domain.removeprefix("engine.") for domain in mapped_domains]
    capability_candidates = _dedupe(cap for d in mapped_domains for cap in DOMAIN_RULES[d]["capabilities"])
    provider_candidates = _dedupe(provider for d in mapped_domains for provider in DOMAIN_RULES[d]["providers"])
    conformance_candidates = _dedupe(conf for d in mapped_domains for conf in DOMAIN_RULES[d]["conformance"])
    score = min(100, (sum(logic_scores[:200]) // 5) + min(40, len(mapped_domains) * 8) + min(20, text_count // 10))
    if not files:
        score = 0
    how = [
        f"Use as behavioral/reference corpus for {domain} without direct source copying."
        for domain in mapped_domains[:8]
    ] or ["Entry has not produced enough deterministic signals yet; keep it indexed but do not drive repair work from it alone."]
    recommended: list[dict[str, Any]] = []
    priority = "P0" if score >= 70 else "P1" if score >= 35 else "P2"
    for domain in mapped_domains[:6]:
        recommended.append({
            "priority": priority,
            "action_id": f"repair.{domain.removeprefix('engine.')}.parity",
            "reason": f"Entry shows useful reference signals for {domain}; compare against gateway/capability/provider/conformance maturity.",
        })
    maturity_questions = []
    for domain in mapped_domains[:6]:
        maturity_questions.extend([
            f"Does {domain} have a declared engine.* gateway?",
            f"Does {domain} have capability descriptors and visible diagnostics?",
            f"Does {domain} have provider and NullProvider conformance coverage?",
        ])
    risk_flags = []
    lower_names = "\n".join(p.name.lower() for p in files[:1000])
    if any(x in lower_names for x in ("license", "copyright", "third_party", "vendor")):
        risk_flags.append("licensing_or_third_party_terms_present")
    if len(files) >= max_files:
        risk_flags.append("analysis_truncated_by_file_limit")
    return {
        "schema": "northstar.dataset.entry_value.v1",
        "entry_id": slug(base.name),
        "entry_path": rel(ctx.root, base),
        "dataset_relative_path": entry_rel,
        "analyzed_at": _now(),
        "file_count_sampled": len(files),
        "text_file_count_sampled": text_count,
        "extension_summary": dict(ext.most_common(30)),
        "architectural_value_score": int(score),
        "value_level": _value_level(int(score)),
        "topic_tags": topic_tags,
        "mapped_engine_domains": mapped_domains,
        "domain_scores": domain_scores,
        "capability_candidates": capability_candidates,
        "provider_candidates": provider_candidates,
        "conformance_candidates": conformance_candidates,
        "how_it_can_help": how,
        "recommended_actions": recommended,
        "maturity_questions": _dedupe(maturity_questions),
        "risk_flags": risk_flags,
        "forbidden_direct_copy_notes": [
            "Use this Entry as reference behavior and architecture inspiration only.",
            "Do not copy foreign source code, proprietary names, or implementation structure directly into North Star.",
            "Translate value into engine.* gateways, capability descriptors, DTOs, conformance and diagnostics.",
        ],
        "evidence": evidence,
    }


def render_entry_value_markdown(index: Dict[str, Any]) -> str:
    lines = [
        "# North Star dataSet Entry Value Index",
        "",
        f"- schema: `{index.get('schema')}`",
        f"- updated_at: `{index.get('updated_at')}`",
        f"- entries: `{index.get('entry_count')}`",
        "",
    ]
    for entry in index.get("entries", []):
        lines.extend([
            f"## {entry.get('entry_id')}",
            "",
            f"- path: `{entry.get('entry_path')}`",
            f"- value: `{entry.get('value_level')}` / `{entry.get('architectural_value_score')}`",
            f"- domains: `{', '.join(entry.get('mapped_engine_domains') or [])}`",
            f"- capabilities: `{', '.join(entry.get('capability_candidates') or [])}`",
            "",
        ])
        help_items = entry.get("how_it_can_help") or []
        if help_items:
            lines.append("Useful because:")
            for item in help_items[:8]:
                lines.append(f"- {item}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def analyze_entries(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("dataset entry value analysis requires write mode", "write_disabled")
    dirs = dataset_dirs(ctx)
    extracted = dirs["extracted"]
    if not extracted.exists():
        return {"ok": False, "reason": "not_materialized", "entries": []}
    raw_path = str(args.get("path", "") or "").strip()
    limit = max(1, min(int(args.get("limit", 200) or 200), 1000))
    max_files = max(100, min(int(args.get("max_files", FILE_SAMPLE_LIMIT) or FILE_SAMPLE_LIMIT), 50000))
    if raw_path:
        bases = [safe_extracted_path(ctx, raw_path)]
    else:
        bases = sorted([p for p in extracted.iterdir() if p.is_dir()], key=lambda p: p.name.lower())[:limit]
    out_dir = dirs["index"] / "entry-values"
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for base in bases:
        report = analyze_extracted_entry(ctx, base, max_files=max_files)
        entries.append(report)
        (out_dir / f"{report['entry_id']}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index = {
        "schema": "northstar.dataset.entry_value_index.v1",
        "updated_at": _now(),
        "entry_count": len(entries),
        "entries": sorted(entries, key=lambda item: (-int(item.get("architectural_value_score", 0)), str(item.get("entry_id", "")))),
    }
    index_path = dirs["index"] / "entry-value-index.json"
    report_path = dirs["index"] / "entry-value-report.md"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_entry_value_markdown(index), encoding="utf-8")
    return {
        "ok": True,
        "schema": index["schema"],
        "entry_count": len(entries),
        "index_path": rel(ctx.root, index_path),
        "report_path": rel(ctx.root, report_path),
        "entries": index["entries"],
    }
