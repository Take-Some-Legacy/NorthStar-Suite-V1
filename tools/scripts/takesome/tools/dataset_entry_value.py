from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ..logs import TeeLog
from ..paths import rel

DOMAIN_TERMS: dict[str, list[str]] = {
    "engine.ai": ["ai", "agent", "behavior", "task", "planner", "decision", "brain"],
    "engine.animation": ["animation", "anim", "skeleton", "blend", "ik", "pose"],
    "engine.assets": ["asset", "import", "resource", "texture", "model", "material", "codec", "listfile"],
    "engine.debug": ["debug", "profiler", "trace", "diagnostic", "log"],
    "engine.input": ["input", "keyboard", "mouse", "gamepad", "binding", "action"],
    "engine.physics": ["physics", "collision", "rigid", "cloth", "vehicle", "constraint"],
    "engine.render": ["render", "shader", "lighting", "shadow", "vfx", "gpu", "material"],
    "engine.scene": ["scene", "world", "entity", "component", "prefab", "streaming", "archetype"],
    "engine.ui": ["ui", "frontend", "widget", "layout", "text", "menu", "panel"],
    "engine.scripting": ["script", "vm", "binding", "event", "command"],
}

CAPABILITY_BY_DOMAIN: dict[str, list[str]] = {
    "engine.ai": ["ai.backend", "ai.patterns.utility_planner"],
    "engine.animation": ["animation.backend", "animation.graph"],
    "engine.assets": ["assets.vfs", "assets.listfile.nef8", "assets.import"],
    "engine.debug": ["debug.trace", "debug.diagnostics"],
    "engine.input": ["input.backend", "input.bindings"],
    "engine.physics": ["physics.backend", "physics.contacts"],
    "engine.render": ["render.backend", "render.frame_graph", "render.diagnostics"],
    "engine.scene": ["scene.runtime", "world.streaming", "entity.lifecycle"],
    "engine.ui": ["ui.backend", "ui.text.shaping", "ui.debug.overlay"],
    "engine.scripting": ["scripting.backend", "scripting.bindings"],
}

TEXT_EXT = {".rs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".cpp", ".c", ".h", ".hpp", ".cs", ".java", ".kt", ".lua", ".rb", ".toml", ".json", ".yaml", ".yml", ".xml", ".md", ".txt", ".glsl", ".hlsl", ".shader"}


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slug(value: str, default: str = "entry") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip("-._")
    return cleaned[:80] or default


def _is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXT or path.name.lower() in {"readme", "license", "makefile"}


def _read(path: Path) -> str:
    if not _is_text(path) or path.stat().st_size > 512 * 1024:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:8192]


def _iter_files(base: Path, limit: int) -> list[Path]:
    out: list[Path] = []
    for path in base.rglob("*") if base.is_dir() else [base]:
        if path.is_file():
            out.append(path)
            if len(out) >= limit:
                break
    return out


def _score_file(path: Path) -> int:
    suffix = path.suffix.lower()
    if suffix in {".rs", ".py", ".ts", ".tsx", ".cpp", ".h", ".hpp", ".cs", ".go"}:
        return 8
    if suffix in {".toml", ".json", ".yaml", ".yml", ".xml"}:
        return 5
    if suffix in {".md", ".txt"}:
        return 2
    return 0


def analyze_entry(repo_root: Path, entry: Path, *, max_files: int) -> dict[str, Any]:
    files = _iter_files(entry, max_files)
    entry_rel = rel(repo_root, entry)
    ext = Counter((p.suffix.lower() or "<none>") for p in files)
    text_count = sum(1 for p in files if _is_text(p))
    domain_scores: dict[str, int] = {}
    evidence: list[dict[str, Any]] = []
    for path in files[:96]:
        hay = f"{entry_rel}\n{path.name}\n{_read(path)}".lower()
        matched: list[str] = []
        for domain, terms in DOMAIN_TERMS.items():
            score = sum(hay.count(term) for term in terms)
            if score:
                domain_scores[domain] = domain_scores.get(domain, 0) + score
                matched.append(domain)
        if matched:
            evidence.append({"path": rel(repo_root, path), "domains": matched[:8], "logic_score": _score_file(path)})
    mapped = [d for d, _ in sorted(domain_scores.items(), key=lambda kv: (-kv[1], kv[0]))]
    capabilities = sorted({cap for d in mapped for cap in CAPABILITY_BY_DOMAIN.get(d, [])})
    value = min(100, sum(_score_file(p) for p in files[:300]) // 4 + min(40, len(mapped) * 8) + min(20, text_count // 10)) if files else 0
    level = "high" if value >= 70 else "medium" if value >= 35 else "low" if value else "unknown"
    recommended = [{"priority": "P0" if value >= 70 else "P1" if value >= 35 else "P2", "action_id": f"repair.{d.removeprefix('engine.')}.parity", "reason": f"Entry has deterministic reference signals for {d}."} for d in mapped[:6]]
    return {
        "schema": "northstar.dataset.entry_value.v1",
        "entry_id": _slug(entry.name),
        "entry_path": entry_rel,
        "analyzed_at": _now(),
        "file_count_sampled": len(files),
        "text_file_count_sampled": text_count,
        "extension_summary": dict(ext.most_common(30)),
        "architectural_value_score": int(value),
        "value_level": level,
        "topic_tags": [d.removeprefix("engine.") for d in mapped],
        "mapped_engine_domains": mapped,
        "domain_scores": domain_scores,
        "capability_candidates": capabilities,
        "provider_candidates": [f"{d.removeprefix('engine.').title()}Provider" for d in mapped],
        "conformance_candidates": [f"{d.removeprefix('engine')}.provider.conformance".strip(".") for d in mapped],
        "how_it_can_help": [f"Use as behavioral/reference corpus for {d} without direct source copying." for d in mapped[:8]] or ["Entry is indexed but has weak deterministic value signals so far."],
        "recommended_actions": recommended,
        "maturity_questions": [f"Does {d} have gateway/capability/provider/NullProvider/conformance/diagnostics coverage?" for d in mapped[:8]],
        "risk_flags": ["analysis_truncated_by_file_limit"] if len(files) >= max_files else [],
        "forbidden_direct_copy_notes": [
            "Reference/dataSet Entry is behavioral corpus only.",
            "Do not copy foreign source directly into North Star.",
            "Translate findings into gateways, capabilities, DTOs, providers, conformance and diagnostics.",
        ],
        "evidence": evidence[:50],
    }


def render_markdown(index: dict[str, Any]) -> str:
    lines = ["# North Star dataSet Entry Value Index", "", f"- updated_at: `{index.get('updated_at')}`", f"- entries: `{index.get('entry_count')}`", ""]
    for entry in index.get("entries", []):
        lines.extend([f"## {entry.get('entry_id')}", "", f"- value: `{entry.get('value_level')}` / `{entry.get('architectural_value_score')}`", f"- path: `{entry.get('entry_path')}`", f"- domains: `{', '.join(entry.get('mapped_engine_domains') or [])}`", ""])
    return "\n".join(lines).rstrip() + "\n"


def dataset_entry_value_analysis(repo_root: Path, *, limit: int = 500, max_files: int = 5000, log: TeeLog | None = None) -> int:
    own_log = log or TeeLog()
    data_root = repo_root / ".takesome" / "dataSet"
    extracted = data_root / "extracted"
    index_root = data_root / "index"
    values_root = index_root / "entry-values"
    index_root.mkdir(parents=True, exist_ok=True)
    values_root.mkdir(parents=True, exist_ok=True)
    if not extracted.exists():
        own_log.emit(f"[WARN] dataSet extracted root missing: {rel(repo_root, extracted)}")
        return 1
    entries = sorted([p for p in extracted.iterdir() if p.is_dir()], key=lambda p: p.name.lower())[:max(1, limit)]
    reports: list[dict[str, Any]] = []
    for entry in entries:
        report = analyze_entry(repo_root, entry, max_files=max_files)
        reports.append(report)
        (values_root / f"{report['entry_id']}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        own_log.emit(f"[OK] entry value {report['entry_id']} score={report['architectural_value_score']} domains={','.join(report['mapped_engine_domains'][:4])}")
    index = {"schema": "northstar.dataset.entry_value_index.v1", "updated_at": _now(), "entry_count": len(reports), "entries": sorted(reports, key=lambda item: (-int(item.get("architectural_value_score", 0)), item.get("entry_id", "")))}
    (index_root / "entry-value-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (index_root / "entry-value-report.md").write_text(render_markdown(index), encoding="utf-8")
    own_log.emit(f"[OK] entry value index: {rel(repo_root, index_root / 'entry-value-index.json')}")
    return 0
