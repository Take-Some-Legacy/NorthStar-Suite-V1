from __future__ import annotations

"""Index-first dataSet maturity scanner.

This module is intentionally not a Dataset Browser. It treats the materialized
index files as the source of truth and evaluates how ready North Star is to
consume the reference corpus through engine.* domains, capability descriptors,
providers, NullProviders, conformance, DTO boundaries and diagnostics.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .contracts import BridgeContext, BridgeError, MAX_SEARCH_FILE_BYTES, now_utc
from .dataset_core import dataset_dirs, dataset_root, read_json_file
from .paths import is_text_file, rel, slug

ENGINE_ROOT_REL = "NewEngine/neocore2"
CAPABILITY_MATRIX_REL = f"{ENGINE_ROOT_REL}/config/capabilities/engine_capability_matrix.v1.json"
CONFORMANCE_MATRIX_REL = f"{ENGINE_ROOT_REL}/config/conformance/provider_conformance_matrix.v1.json"
REFERENCE_MATRIX_REL = f"{ENGINE_ROOT_REL}/config/reference/module_completeness_matrix.v1.json"
AUDIT_REPORT_REL = "docs/audits/DATASET_MATURITY_REPORT.md"

REQUIRED_INDEX_FILES = (
    "dataset-index.json",
    "dataset-browser-index.json",
    "knowledge-registry.json",
    "knowledge-registry.md",
)

TOPIC_GATEWAYS: Dict[str, Tuple[str, ...]] = {
    "ai": ("engine.ai",),
    "animation": ("engine.animation", "engine.model"),
    "asset": ("engine.assets", "engine.materials", "engine.model"),
    "audio": ("engine.audio",),
    "debug": ("engine.debug", "engine.ui"),
    "physics": ("engine.physics",),
    "render": ("engine.render", "engine.materials", "engine.model"),
    "scene": ("engine.scene", "engine.world", "engine.entity"),
    "script": ("engine.script", "engine.event"),
    "ui": ("engine.ui",),
    "network": ("engine.network", "engine.replication", "engine.script"),
    "event": ("engine.event", "engine.script", "engine.debug"),
    "streaming": ("engine.world", "engine.scene", "engine.assets"),
    "save": ("engine.world", "engine.scene"),
    "vfx": ("engine.render", "engine.vfx"),
    "text": ("engine.ui", "engine.ui.text"),
    "frontend": ("engine.ui",),
    "ik": ("engine.animation", "engine.ik"),
    "cutscene": ("engine.cutscene", "engine.animation", "engine.script"),
    "pathserver": ("engine.navigation", "engine.ai"),
    "peds": ("engine.ai", "engine.entity", "engine.animation"),
    "pedgroup": ("engine.ai", "engine.entity"),
    "performance": ("engine.debug", "engine.scheduler"),
    "modelinfo": ("engine.model", "engine.scene"),
    "objects": ("engine.scene", "engine.entity", "engine.model"),
    "control": ("engine.input", "engine.script"),
}

REFERENCE_BUCKETS: Dict[str, str] = {
    "ai": "covered",
    "animation": "covered",
    "camera": "covered",
    "renderer": "covered",
    "scene": "covered",
    "streaming": "covered",
    "saveload": "covered",
    "script": "covered",
    "replaycoordinator": "covered",
    "audio": "visible_gap",
    "vfx": "visible_gap",
    "text": "visible_gap",
    "frontend": "visible_gap",
    "debug": "visible_gap",
    "control": "visible_gap",
    "ik": "visible_gap",
    "cutscene": "visible_gap",
    "tools": "visible_gap",
    "modelinfo": "visible_gap",
    "objects": "visible_gap",
    "pathserver": "visible_gap",
    "peds": "visible_gap",
    "pedgroup": "visible_gap",
    "physics": "visible_gap",
    "performance": "visible_gap",
    "framework": "visible_gap",
    "speedtree": "visible_gap",
    "pro-shaders": "visible_gap",
    "pro_shaders": "visible_gap",
    "cloth": "visible_gap",
    "system": "visible_gap",
    "game": "visible_gap",
    "core": "visible_gap",
    "network": "missing_gateway",
    "event": "missing_gateway",
    "physx3": "external_reference",
    "scaleform": "external_reference",
    "script-scene": "external_reference",
    "scene-script": "external_reference",
}

HIDDEN_FALLBACK_SCAN_TERMS = ("hidden" + " fallback", "fallback" + " silently", "Internal" + "Null", "unwrap" + "_or_else")

DOMAIN_EXPECTATIONS: Dict[str, Dict[str, Any]] = {
    "engine.ai": {"capabilities": ("ai.backend",), "provider_terms": ("newengine-ai", "ai.api", "AiFrameInput", "AiFrameOutput"), "null_terms": ("NullAI", "null-ai"), "conformance_terms": ("ai",), "dto_terms": ("AiFrameInput", "AiFrameOutput", "AiAgentIntent"), "diagnostic_terms": ("ai trace", "DecisionTrace", "engine.ai route"), "direct_provider_ids": ("ai.api",)},
    "engine.animation": {"capabilities": ("animation.backend",), "provider_terms": ("animation.api", "AnimationFrame"), "null_terms": ("NullAnimation",), "conformance_terms": ("animation",), "dto_terms": ("AnimationFrame", "AnimationPose"), "diagnostic_terms": ("animation trace",), "direct_provider_ids": ("animation.api",)},
    "engine.assets": {"capabilities": ("assets.vfs", "assets.listfile.nef8"), "provider_terms": ("asset_manager.api", "AssetManager"), "null_terms": ("NullAssets",), "conformance_terms": ("asset", "nef8"), "dto_terms": ("file@entry", "ListFile"), "diagnostic_terms": ("asset diagnostic",), "direct_provider_ids": ("asset_manager.api",)},
    "engine.audio": {"capabilities": ("audio.backend",), "provider_terms": ("audio.api", "AudioFrame"), "null_terms": ("NullAudio",), "conformance_terms": ("audio",), "dto_terms": ("AudioFrameInput", "AudioFrameOutput"), "diagnostic_terms": ("audio diagnostic",), "direct_provider_ids": ("audio.api",)},
    "engine.cutscene": {"capabilities": ("cutscene.backend",), "provider_terms": ("cutscene.api",), "null_terms": ("NullCutscene",), "conformance_terms": ("cutscene",), "dto_terms": ("CutsceneFrame",), "diagnostic_terms": ("cutscene diagnostic",), "direct_provider_ids": ("cutscene.api",)},
    "engine.debug": {"capabilities": ("debug.diagnostics",), "provider_terms": ("debug.api", "diagnostics"), "null_terms": ("NullDebug",), "conformance_terms": ("debug", "diagnostic"), "dto_terms": ("Diagnostic", "Trace"), "diagnostic_terms": ("diagnostic", "trace"), "direct_provider_ids": ("debug.api",)},
    "engine.entity": {"capabilities": ("entity.lifecycle",), "provider_terms": ("entity.api", "EntityCommand"), "null_terms": ("NullEntity",), "conformance_terms": ("entity",), "dto_terms": ("EntityHandle", "EntitySnapshot"), "diagnostic_terms": ("entity trace",), "direct_provider_ids": ("entity.api",)},
    "engine.event": {"capabilities": ("event.bus",), "provider_terms": ("event.api", "EventEnvelope"), "null_terms": ("NullEvent",), "conformance_terms": ("event",), "dto_terms": ("EventEnvelope", "EventDispatch"), "diagnostic_terms": ("event trace",), "direct_provider_ids": ("event.api",)},
    "engine.ik": {"capabilities": ("ik.solver",), "provider_terms": ("ik.api", "IKSolver"), "null_terms": ("NullIK",), "conformance_terms": ("ik",), "dto_terms": ("IkSolveInput", "IkSolveOutput"), "diagnostic_terms": ("ik diagnostic",), "direct_provider_ids": ("ik.api",)},
    "engine.input": {"capabilities": ("input.backend", "input.actions"), "provider_terms": ("input.api", "InputPluginHost"), "null_terms": ("NullInput",), "conformance_terms": ("input",), "dto_terms": ("InputFrame", "InputAction"), "diagnostic_terms": ("input trace",), "direct_provider_ids": ("input.api",)},
    "engine.materials": {"capabilities": ("materials.graph.resolve",), "provider_terms": ("materials.api", "MaterialGraph"), "null_terms": ("NullMaterials",), "conformance_terms": ("material",), "dto_terms": ("ResolvedMaterialGraph",), "diagnostic_terms": ("material graph",), "direct_provider_ids": ("materials.api",)},
    "engine.model": {"capabilities": ("model.drawable_dictionary.resolve",), "provider_terms": ("model.api", "DrawableDictionary"), "null_terms": ("NullModel",), "conformance_terms": ("model", "drawable"), "dto_terms": ("DrawableDictionaryManifest",), "diagnostic_terms": ("model diagnostic",), "direct_provider_ids": ("model.api",)},
    "engine.navigation": {"capabilities": ("navigation.backend",), "provider_terms": ("navigation.api", "NavMesh"), "null_terms": ("NullNavigation",), "conformance_terms": ("navigation", "path"), "dto_terms": ("NavigationQuery", "NavigationPath"), "diagnostic_terms": ("navigation trace",), "direct_provider_ids": ("navigation.api",)},
    "engine.network": {"capabilities": ("network.backend",), "provider_terms": ("network.api", "NetworkFrame"), "null_terms": ("NullNetwork",), "conformance_terms": ("network",), "dto_terms": ("NetworkFrameInput", "NetworkFrameOutput"), "diagnostic_terms": ("network trace",), "direct_provider_ids": ("network.api",)},
    "engine.physics": {"capabilities": ("physics.backend",), "provider_terms": ("physics.api", "PhysicsFrameInput"), "null_terms": ("NullPhysics",), "conformance_terms": ("physics",), "dto_terms": ("PhysicsFrameInput", "PhysicsFrameOutput"), "diagnostic_terms": ("physics trace",), "direct_provider_ids": ("physics.api",)},
    "engine.render": {"capabilities": ("render.backend",), "provider_terms": ("render.api", "RenderFrameEnvelope"), "null_terms": ("NullRenderer",), "conformance_terms": ("render",), "dto_terms": ("RenderFrameInput", "RenderFrameOutput", "RenderFrameEnvelope"), "diagnostic_terms": ("frame trace", "render diagnostic"), "direct_provider_ids": ("render.api",)},
    "engine.replication": {"capabilities": ("replication.backend",), "provider_terms": ("replication.api",), "null_terms": ("NullReplication",), "conformance_terms": ("replication",), "dto_terms": ("ReplicationFrame",), "diagnostic_terms": ("replication trace",), "direct_provider_ids": ("replication.api",)},
    "engine.scene": {"capabilities": ("scene.archetype.resolve", "scene.runtime"), "provider_terms": ("scene.api", "SceneCommand"), "null_terms": ("NullScene",), "conformance_terms": ("scene",), "dto_terms": ("SceneCommand", "SceneSnapshot"), "diagnostic_terms": ("scene trace",), "direct_provider_ids": ("scene.api",)},
    "engine.scheduler": {"capabilities": ("scheduler.jobs",), "provider_terms": ("scheduler.api", "JobSystem"), "null_terms": ("NullScheduler",), "conformance_terms": ("scheduler", "job"), "dto_terms": ("SchedulePlan",), "diagnostic_terms": ("scheduler trace",), "direct_provider_ids": ("scheduler.api",)},
    "engine.script": {"capabilities": ("script.backend",), "provider_terms": ("script.api", "ScriptVm"), "null_terms": ("NullScript",), "conformance_terms": ("script",), "dto_terms": ("ScriptCommand", "ScriptEvent"), "diagnostic_terms": ("script trace",), "direct_provider_ids": ("script.api",)},
    "engine.ui": {"capabilities": ("ui.backend",), "provider_terms": ("ui.api", "AureliaUI"), "null_terms": ("NullUI",), "conformance_terms": ("ui",), "dto_terms": ("UiFrameInput", "UiFrameOutput", "UiNodeRequest"), "diagnostic_terms": ("UI Tree", "ui diagnostic"), "direct_provider_ids": ("ui.api",)},
    "engine.ui.text": {"capabilities": ("ui.text.shaping",), "provider_terms": ("text.api", "HarfBuzz"), "null_terms": ("NullText",), "conformance_terms": ("text",), "dto_terms": ("TextShapeRequest", "TextShapeResult"), "diagnostic_terms": ("text backend",), "direct_provider_ids": ("text.api",)},
    "engine.vfx": {"capabilities": ("vfx.backend",), "provider_terms": ("vfx.api", "VfxFrame"), "null_terms": ("NullVfx",), "conformance_terms": ("vfx",), "dto_terms": ("VfxFrameInput", "VfxFrameOutput"), "diagnostic_terms": ("vfx diagnostic",), "direct_provider_ids": ("vfx.api",)},
    "engine.world": {"capabilities": ("world.streaming", "world.save_load"), "provider_terms": ("world.api", "WorldSnapshot", "StreamingCell"), "null_terms": ("NullWorld",), "conformance_terms": ("world", "streaming", "save"), "dto_terms": ("WorldSnapshot", "StreamingCell"), "diagnostic_terms": ("world trace", "streaming trace"), "direct_provider_ids": ("world.api",)},
}

DIRECT_COPY_NOTE = (
    "Reference corpus is behavioral memory only: never direct-copy source. "
    "Convert evidence into engine.* gateways, explicit capabilities, providers, DTOs, diagnostics and conformance."
)


def _repo_json(ctx: BridgeContext, rel_path: str) -> Dict[str, Any]:
    path = ctx.root / rel_path
    value = read_json_file(path) if path.exists() else {}
    return value if isinstance(value, dict) else {"_invalid_root": type(value).__name__}


def _index_file(ctx: BridgeContext, name: str) -> Path:
    return dataset_dirs(ctx)["index"] / name


def _read_required_index(ctx: BridgeContext) -> Dict[str, Any]:
    dirs = dataset_dirs(ctx)
    missing = [name for name in REQUIRED_INDEX_FILES if not (dirs["index"] / name).exists()]
    if missing:
        raise BridgeError(
            "dataSet index stale: required index files are missing; run dataset_rebuild_index first",
            "dataset_index_stale",
            {"missing": missing, "run": "northstar.dataset_rebuild_index"},
        )
    index_file = _index_file(ctx, "dataset-index.json")
    browser_file = _index_file(ctx, "dataset-browser-index.json")
    knowledge_file = _index_file(ctx, "knowledge-registry.json")
    knowledge_md = _index_file(ctx, "knowledge-registry.md")
    newest_source = 0.0
    for source_root in (dirs["extracted"],):
        if source_root.exists():
            newest_source = max(newest_source, source_root.stat().st_mtime)
            for child in source_root.iterdir():
                try:
                    newest_source = max(newest_source, child.stat().st_mtime)
                except OSError:
                    pass
    oldest_index = min(path.stat().st_mtime for path in (index_file, browser_file, knowledge_file, knowledge_md))
    if newest_source and oldest_index + 1 < newest_source:
        raise BridgeError(
            "dataSet index stale: extracted directory changed after index rebuild; run dataset_rebuild_index first",
            "dataset_index_stale",
            {"newest_extracted_mtime": int(newest_source), "oldest_index_mtime": int(oldest_index), "run": "northstar.dataset_rebuild_index"},
        )
    return {
        "dataset_index": _repo_json(ctx, rel(ctx.root, index_file)),
        "browser_index": _repo_json(ctx, rel(ctx.root, browser_file)),
        "knowledge_registry": _repo_json(ctx, rel(ctx.root, knowledge_file)),
        "knowledge_markdown_path": rel(ctx.root, knowledge_md),
        "index_paths": {name: rel(ctx.root, dirs["index"] / name) for name in REQUIRED_INDEX_FILES},
    }


def _matrix_sets(ctx: BridgeContext) -> Dict[str, Any]:
    cap = _repo_json(ctx, CAPABILITY_MATRIX_REL)
    conf = _repo_json(ctx, CONFORMANCE_MATRIX_REL)
    ref = _repo_json(ctx, REFERENCE_MATRIX_REL)
    cap_records = cap.get("records") if isinstance(cap.get("records"), list) else []
    conf_families = conf.get("families") if isinstance(conf.get("families"), list) else []
    return {
        "capability_records": cap_records,
        "conformance_families": conf_families,
        "reference_matrix": ref,
        "gateways": {str(r.get("engine_gateway", "")) for r in cap_records if isinstance(r, dict)},
        "capabilities": {str(r.get("capability_id", "")) for r in cap_records if isinstance(r, dict)},
        "family_names": {str(f.get("family", "")) for f in conf_families if isinstance(f, dict)},
    }


def _entry_id_from_dataset_rel(dataset_rel: str) -> str:
    raw = dataset_rel.replace("\\", "/").strip("/")
    if raw.startswith("extracted/"):
        raw = raw[len("extracted/"):]
    first = raw.split("/", 1)[0] if raw else "dataset"
    return slug(first.lower(), "dataset")


def _topic_domains(topic_scores: Dict[str, Any]) -> List[str]:
    weighted: Counter[str] = Counter()
    for topic, score in (topic_scores or {}).items():
        for gateway in TOPIC_GATEWAYS.get(str(topic).lower(), (f"engine.{str(topic).lower()}",)):
            weighted[gateway] += int(score) if isinstance(score, int) else 1
    return [domain for domain, _ in sorted(weighted.items(), key=lambda kv: (-kv[1], kv[0]))]


def _domains_from_name(entry_id: str) -> List[str]:
    name = entry_id.lower()
    domains: List[str] = []
    for topic, gateways in TOPIC_GATEWAYS.items():
        if topic in name:
            domains.extend(gateways)
    return list(dict.fromkeys(domains))


def _reference_status(entry_id: str, matrices: Dict[str, Any]) -> str:
    normalized = entry_id.lower().replace("_", "-")
    if normalized in REFERENCE_BUCKETS:
        return REFERENCE_BUCKETS[normalized]
    compact = normalized.replace("-", "")
    if compact in REFERENCE_BUCKETS:
        return REFERENCE_BUCKETS[compact]
    ref = matrices.get("reference_matrix") or {}
    for item in ref.get("archive_coverage") or []:
        if not isinstance(item, dict):
            continue
        archive = str(item.get("reference_archive", "")).lower()
        if Path(archive).stem.lower() in {entry_id.lower(), normalized, compact}:
            return str(item.get("northstar_status") or "visible_gap")
    return "unmapped"


def _group_index_entries(index_payload: Dict[str, Any], browser_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    entries: Dict[str, Dict[str, Any]] = {}
    files = index_payload.get("files") if isinstance(index_payload.get("files"), list) else []
    for record in files:
        if not isinstance(record, dict):
            continue
        drel = str(record.get("dataset_relative_path") or "")
        if not drel.startswith("extracted/"):
            continue
        entry_id = _entry_id_from_dataset_rel(drel)
        item = entries.setdefault(entry_id, {"entry_id": entry_id, "file_count": 0, "topic_scores": Counter(), "extensions": Counter(), "evidence": []})
        item["file_count"] += 1
        ext = str(record.get("extension") or "<none>")
        item["extensions"][ext] += 1
        for topic, score in (record.get("topics") or {}).items():
            item["topic_scores"][str(topic)] += int(score) if isinstance(score, int) else 1
        if len(item["evidence"]) < 8:
            item["evidence"].append({"path": record.get("path"), "logic_score": record.get("logic_score"), "topics": record.get("topics") or {}})
    directories = browser_payload.get("directories") if isinstance(browser_payload.get("directories"), list) else []
    for directory in directories:
        if not isinstance(directory, dict):
            continue
        drel = str(directory.get("dataset_relative_path") or "")
        if not drel.startswith("extracted/"):
            continue
        rest = drel[len("extracted/"):].strip("/")
        if not rest or "/" in rest:
            continue
        entry_id = slug(rest.lower(), "dataset")
        item = entries.setdefault(entry_id, {"entry_id": entry_id, "file_count": 0, "topic_scores": Counter(), "extensions": Counter(), "evidence": []})
        item["extracted_path"] = directory.get("path")
        item["logic_score"] = directory.get("logic_score")
        item["directory_profile"] = {k: directory.get(k) for k in ("text_file_count_sampled", "size_bytes_sampled", "key_files", "logic_dirs", "truncated")}
    return entries


def _project_roots(ctx: BridgeContext) -> Iterable[Path]:
    roots = [
        ctx.root / "tools" / "scripts",
        ctx.root / "config",
        ctx.root / "docs",
        ctx.root / ENGINE_ROOT_REL / "crates",
        ctx.root / ENGINE_ROOT_REL / "config",
        ctx.root / ENGINE_ROOT_REL / "scripts",
    ]
    return [root for root in roots if root.exists()]


def _all_tokens() -> List[str]:
    tokens: List[str] = []
    for spec in DOMAIN_EXPECTATIONS.values():
        for key in ("provider_terms", "null_terms", "dto_terms", "diagnostic_terms", "direct_provider_ids"):
            tokens.extend(str(item) for item in spec.get(key, ()))
    tokens.extend(HIDDEN_FALLBACK_SCAN_TERMS)
    return sorted(set(tokens), key=str.lower)


def _token_scan(ctx: BridgeContext, tokens: List[str], max_files: int = 30000) -> Dict[str, Any]:
    lowered = {token: token.lower() for token in tokens}
    counts: Counter[str] = Counter()
    examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    scanned = 0
    for root in _project_roots(ctx):
        for path in root.rglob("*"):
            if scanned >= max_files:
                return {"counts": dict(counts), "examples": dict(examples), "scanned_files": scanned, "truncated": True}
            if not path.is_file() or not is_text_file(path) or path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            hay = text.lower()
            for token in tokens:
                needle = lowered[token]
                if needle in hay:
                    counts[token] += hay.count(needle)
                    if len(examples[token]) < 3:
                        line_no = next((idx for idx, line in enumerate(text.splitlines(), 1) if needle in line.lower()), None)
                        examples[token].append({"path": rel(ctx.root, path), "line": line_no})
    return {"counts": dict(counts), "examples": dict(examples), "scanned_files": scanned, "truncated": False}


def _domain_question(domain: str, needed: bool, matrices: Dict[str, Any], scan: Dict[str, Any]) -> Dict[str, Any]:
    spec = DOMAIN_EXPECTATIONS.get(domain, {"capabilities": (f"{domain.removeprefix('engine.')}.backend",)})
    counts = scan.get("counts") or {}
    capabilities = set(matrices.get("capabilities") or set())
    gateways = set(matrices.get("gateways") or set())
    family_names = set(matrices.get("family_names") or set())
    expected_caps = list(spec.get("capabilities") or [])
    provider_hits = {term: int(counts.get(term, 0)) for term in spec.get("provider_terms", ()) if int(counts.get(term, 0)) > 0}
    null_hits = {term: int(counts.get(term, 0)) for term in spec.get("null_terms", ()) if int(counts.get(term, 0)) > 0}
    dto_hits = {term: int(counts.get(term, 0)) for term in spec.get("dto_terms", ()) if int(counts.get(term, 0)) > 0}
    diag_hits = {term: int(counts.get(term, 0)) for term in spec.get("diagnostic_terms", ()) if int(counts.get(term, 0)) > 0}
    direct_hits = {term: int(counts.get(term, 0)) for term in spec.get("direct_provider_ids", ()) if int(counts.get(term, 0)) > 0}
    conformance_terms = [str(t).lower() for t in spec.get("conformance_terms", ())]
    conformance_matches = sorted([family for family in family_names if any(term in family.lower() for term in conformance_terms)])
    hidden_hits = {term: int(counts.get(term, 0)) for term in HIDDEN_FALLBACK_SCAN_TERMS if int(counts.get(term, 0)) > 0}
    return {
        "domain": domain,
        "engine_gateway_needed": needed,
        "engine_gateway": {"id": domain, "declared": domain in gateways},
        "capability": {"expected": expected_caps, "declared": [c for c in expected_caps if c in capabilities], "missing": [c for c in expected_caps if c not in capabilities]},
        "provider": {"present_signal": bool(provider_hits), "hits": provider_hits},
        "null_provider": {"present_signal": bool(null_hits), "hits": null_hits},
        "conformance": {"present_signal": bool(conformance_matches), "families": conformance_matches},
        "runtime_dto_path": {"present_signal": bool(dto_hits), "hits": dto_hits},
        "diagnostics": {"present_signal": bool(diag_hits), "hits": diag_hits},
        "hidden_fallback": {"suspect_signal": bool(hidden_hits), "hits": hidden_hits},
        "direct_provider_id": {"suspect_signal": bool(direct_hits), "hits": direct_hits},
    }


def _score(q: Dict[str, Any]) -> int:
    if not q.get("engine_gateway_needed"):
        return 0
    flags = [
        q["engine_gateway"].get("declared"),
        not q["capability"].get("missing"),
        q["provider"].get("present_signal"),
        q["null_provider"].get("present_signal"),
        q["conformance"].get("present_signal"),
        q["runtime_dto_path"].get("present_signal"),
        q["diagnostics"].get("present_signal"),
        not q["hidden_fallback"].get("suspect_signal"),
        not q["direct_provider_id"].get("suspect_signal"),
    ]
    return int(round(5 * sum(1 for f in flags if f) / len(flags)))


def _status_from_question(q: Dict[str, Any], entry_status: str) -> str:
    if entry_status in {"external_reference"}:
        return entry_status
    if not q["engine_gateway"].get("declared"):
        return "missing_gateway"
    if q["capability"].get("missing"):
        return "visible_gap"
    if not q["provider"].get("present_signal") or not q["null_provider"].get("present_signal") or not q["conformance"].get("present_signal"):
        return "visible_gap"
    return "covered" if q["runtime_dto_path"].get("present_signal") and q["diagnostics"].get("present_signal") else "visible_gap"


def _missing_for(q: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    if not q["engine_gateway"].get("declared"):
        missing.append(f"{q['domain']} gateway")
    missing.extend(q["capability"].get("missing") or [])
    if not q["provider"].get("present_signal"):
        missing.append(f"{q['domain']} provider family")
    if not q["null_provider"].get("present_signal"):
        missing.append(f"NullProvider for {q['domain']}")
    if not q["conformance"].get("present_signal"):
        missing.append(f"{q['domain']} conformance family")
    if not q["runtime_dto_path"].get("present_signal"):
        missing.append(f"{q['domain']} DTO/schema boundary")
    if not q["diagnostics"].get("present_signal"):
        missing.append(f"{q['domain']} diagnostics route")
    return missing


def formal_manifest(ctx: BridgeContext, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    args = args or {}
    indexes = _read_required_index(ctx)
    matrices = _matrix_sets(ctx)
    entries = _group_index_entries(indexes["dataset_index"], indexes["browser_index"])
    limit = max(1, min(int(args.get("limit", 5000)), 10000))
    records: List[Dict[str, Any]] = []
    for entry_id, item in sorted(entries.items())[:limit]:
        topic_scores = dict(item.get("topic_scores") or {})
        mapped = list(dict.fromkeys(_topic_domains(topic_scores) + _domains_from_name(entry_id)))
        status = _reference_status(entry_id, matrices)
        gaps: List[str] = []
        if not mapped:
            gaps.append("archive visible, no mapped engine domain")
        if status == "unmapped":
            gaps.append("entry not mapped in reference buckets or module_completeness_matrix")
        records.append({
            "archive_id": entry_id,
            "archive_path": None,
            "source_date": str(indexes["dataset_index"].get("rebuilt_at") or "unknown"),
            "extracted_path": item.get("extracted_path") or f".takesome/dataSet/extracted/{entry_id}",
            "file_count": int(item.get("file_count") or 0),
            "topic_tags": sorted(topic_scores, key=lambda k: (-int(topic_scores[k]), k))[:12],
            "topic_scores": topic_scores,
            "mapped_engine_domains": mapped,
            "parity_status": status,
            "visible_gaps": gaps,
            "forbidden_direct_copy_notes": [DIRECT_COPY_NOTE],
            "evidence": item.get("evidence") or [],
        })
    return {
        "ok": True,
        "schema": "northstar.dataset.formal_manifest.v1",
        "generated_at": now_utc(),
        "dataSetDirectory": rel(ctx.root, dataset_root(ctx)),
        "index_paths": indexes["index_paths"],
        "index_first": True,
        "record_count": len(records),
        "records": records,
    }


def _repair_queue(rows: List[Dict[str, Any]], questions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    queue: Dict[str, List[Dict[str, Any]]] = {"P0": [], "P1": [], "P2": []}
    q_by_domain = {q["domain"]: q for q in questions}
    for row in rows:
        if not row.get("mapped_gateways"):
            queue["P0"].append({"archive": row.get("archive"), "todo": "map archive to engine.* domain", "reason": "archive visible, no mapped engine domain"})
        if row.get("status") == "missing_gateway":
            queue["P0"].append({"archive": row.get("archive"), "todo": "declare missing engine.* gateways", "missing": row.get("missing")})
        for domain in row.get("mapped_gateways") or []:
            q = q_by_domain.get(domain)
            if not q:
                continue
            if q["capability"].get("missing"):
                queue["P0"].append({"domain": domain, "todo": "add missing capability descriptors", "missing": q["capability"].get("missing")})
            if q["hidden_fallback"].get("suspect_signal"):
                queue["P0"].append({"domain": domain, "todo": "remove hidden fallback signals", "hits": q["hidden_fallback"].get("hits")})
            if q["direct_provider_id"].get("suspect_signal"):
                queue["P0"].append({"domain": domain, "todo": "audit direct provider id references outside adapter/config/test surfaces", "hits": q["direct_provider_id"].get("hits")})
            if not q["provider"].get("present_signal"):
                queue["P1"].append({"domain": domain, "todo": "add/declare provider family"})
            if not q["null_provider"].get("present_signal"):
                queue["P1"].append({"domain": domain, "todo": "add visible NullProvider route"})
            if not q["conformance"].get("present_signal"):
                queue["P1"].append({"domain": domain, "todo": "add provider-family conformance harness"})
            if not q["runtime_dto_path"].get("present_signal"):
                queue["P2"].append({"domain": domain, "todo": "add DTO/schema runtime path"})
            if not q["diagnostics"].get("present_signal"):
                queue["P2"].append({"domain": domain, "todo": "add diagnostics route"})
    # Deduplicate stable entries.
    for priority, items in list(queue.items()):
        seen: set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for item in items:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        queue[priority] = deduped
    return queue


def maturity_scan(ctx: BridgeContext, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    args = args or {}
    manifest = formal_manifest(ctx, args)
    matrices = _matrix_sets(ctx)
    mapped_domains = sorted({d for record in manifest["records"] for d in record.get("mapped_engine_domains", [])})
    scan = _token_scan(ctx, _all_tokens(), max_files=max(1000, min(int(args.get("max_files", 30000)), 100000)))
    questions = [_domain_question(domain, True, matrices, scan) for domain in sorted(set(mapped_domains))]
    q_by_domain = {q["domain"]: q for q in questions}
    rows: List[Dict[str, Any]] = []
    for record in manifest["records"]:
        domains = record.get("mapped_engine_domains") or []
        domain_scores = {domain: _score(q_by_domain[domain]) for domain in domains if domain in q_by_domain}
        statuses = [_status_from_question(q_by_domain[d], record.get("parity_status", "visible_gap")) for d in domains if d in q_by_domain]
        status = "missing_gateway" if "missing_gateway" in statuses or record.get("parity_status") == "missing_gateway" else ("covered" if statuses and all(s == "covered" for s in statuses) else record.get("parity_status", "visible_gap"))
        missing: List[str] = []
        for domain in domains:
            if domain in q_by_domain:
                missing.extend(_missing_for(q_by_domain[domain]))
        risks = list(record.get("visible_gaps") or [])
        if any(d in {"engine.network", "engine.replication"} for d in domains):
            risks.append("do not add game-specific network domain; use engine.network/engine.replication contracts")
        if any(q_by_domain.get(d, {}).get("direct_provider_id", {}).get("suspect_signal") for d in domains):
            risks.append("direct provider id signal visible; audit boundary before repair pass")
        rows.append({
            "archive": f"{record.get('archive_id')}.zip",
            "archive_id": record.get("archive_id"),
            "topics": record.get("topic_tags") or [],
            "file_count": record.get("file_count"),
            "mapped_gateways": domains,
            "status": status,
            "maturity_score": min(domain_scores.values()) if domain_scores else 0,
            "domain_maturity_scores": domain_scores,
            "missing": sorted(set(missing)),
            "risks": sorted(set(risks)),
            "next_pass": _next_pass(record.get("archive_id"), status, domains),
            "forbidden_direct_copy_notes": record.get("forbidden_direct_copy_notes") or [DIRECT_COPY_NOTE],
        })
    capability_delta = [{"domain": q["domain"], "gateway_declared": q["engine_gateway"]["declared"], "missing_capabilities": q["capability"].get("missing") or []} for q in questions if not q["engine_gateway"]["declared"] or q["capability"].get("missing")]
    conformance_todo = [{"domain": q["domain"], "todo": "provider-family conformance missing or invisible"} for q in questions if not q["conformance"].get("present_signal")]
    return {
        "ok": True,
        "schema": "northstar.dataset.maturity_scan.v1",
        "generated_at": now_utc(),
        "index_first": True,
        "manifest": manifest,
        "maturity_scale": {"0": "archive visible, no mapped engine domain", "1": "mapped to engine.* domain", "2": "gateway exists", "3": "capability descriptor exists", "4": "provider/null-provider/conformance exists", "5": "DTO/schema/runtime/apply-stage + diagnostics + visible gaps closed"},
        "module_completeness_matrix": rows,
        "questions": questions,
        "capability_matrix_delta": capability_delta,
        "conformance_todo": conformance_todo,
        "repair_queue": _repair_queue(rows, questions),
        "token_scan": {"scanned_files": scan.get("scanned_files"), "truncated": scan.get("truncated")},
        "model_hints": {"truth_source": "dataset-index.json + dataset-browser-index.json + knowledge-registry.json", "browser_policy": "browser is human navigation only; maturity scanner consumes index artifacts", "direct_copy_policy": DIRECT_COPY_NOTE},
    }


def _next_pass(entry_id: Any, status: str, domains: List[str]) -> str:
    name = str(entry_id or "dataset")
    if status == "missing_gateway":
        if "engine.network" in domains or "engine.replication" in domains:
            return "P8.network_gateway_foundation"
        return f"P8.{name}_gateway_foundation"
    if status == "visible_gap":
        return f"P9.{name}_maturity_repair"
    if status == "external_reference":
        return f"P9.{name}_external_reference_notes"
    return f"P9.{name}_conformance_closeout"


def render_maturity_markdown(scan: Dict[str, Any]) -> str:
    lines = [
        "# North Star dataSet Maturity Report",
        "",
        f"- schema: `{scan.get('schema')}`",
        f"- generated_at: `{scan.get('generated_at')}`",
        f"- index_first: `{scan.get('index_first')}`",
        f"- records: `{len(scan.get('module_completeness_matrix') or [])}`",
        "",
        "> [!INFO] INFO BLOCK — роль отчёта",
        "> **У нас сейчас:** этот scanner не является Dataset Browser. Он читает готовые index artifacts и строит maturity map поверх них.",
        ">",
        "> **Technical details (EN):** source indexes: `dataset-index.json`, `dataset-browser-index.json`, `knowledge-registry.json`, `knowledge-registry.md`.",
        "",
        "## Maturity scale",
        "",
    ]
    for key, value in (scan.get("maturity_scale") or {}).items():
        lines.append(f"- `{key}` — {value}")
    lines.extend(["", "## Module completeness matrix", "", "| archive | status | score | gateways | missing | risks | next pass |", "|---|---:|---:|---|---|---|---|"])
    for row in scan.get("module_completeness_matrix") or []:
        lines.append(
            f"| `{row.get('archive')}` | `{row.get('status')}` | `{row.get('maturity_score')}` | "
            f"{', '.join(row.get('mapped_gateways') or []) or '-'} | "
            f"{'; '.join(row.get('missing') or []) or '-'} | "
            f"{'; '.join(row.get('risks') or []) or '-'} | `{row.get('next_pass')}` |"
        )
    lines.extend(["", "## Repair queue", ""])
    for priority, items in (scan.get("repair_queue") or {}).items():
        lines.append(f"### {priority}")
        if not items:
            lines.append("- none")
        for item in items:
            owner = item.get("domain") or item.get("archive") or "dataset"
            lines.append(f"- `{owner}` — {item.get('todo')} `{item.get('missing') or item.get('hits') or item.get('reason') or ''}`")
        lines.append("")
    lines.extend(["## Direct-copy policy", "", DIRECT_COPY_NOTE, ""])
    return "\n".join(lines) + "\n"


def write_maturity_index(ctx: BridgeContext, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("dataset maturity index write requires write mode", "write_disabled")
    args = args or {}
    scan = maturity_scan(ctx, args)
    dirs = dataset_dirs(ctx)
    dirs["index"].mkdir(parents=True, exist_ok=True)
    manifest_path = dirs["index"] / "dataset-formal-manifest.json"
    scan_path = dirs["index"] / "dataset-maturity-report.json"
    md_path = dirs["index"] / "dataset-maturity-report.md"
    audit_path = ctx.root / AUDIT_REPORT_REL
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(scan["manifest"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scan_path.write_text(json.dumps(scan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rendered = render_maturity_markdown(scan)
    md_path.write_text(rendered, encoding="utf-8")
    audit_path.write_text(rendered, encoding="utf-8")
    return {
        "ok": True,
        "schema": "northstar.dataset.maturity_write_result.v1",
        "manifest_path": rel(ctx.root, manifest_path),
        "scan_path": rel(ctx.root, scan_path),
        "report_path": rel(ctx.root, md_path),
        "audit_report_path": rel(ctx.root, audit_path),
        "record_count": len(scan.get("module_completeness_matrix") or []),
        "p0_count": len((scan.get("repair_queue") or {}).get("P0", [])),
        "p1_count": len((scan.get("repair_queue") or {}).get("P1", [])),
        "p2_count": len((scan.get("repair_queue") or {}).get("P2", [])),
    }


def strict_findings(scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for row in scan.get("module_completeness_matrix") or []:
        if not row.get("mapped_gateways"):
            findings.append({"severity": "ERROR", "check": "dataset-mapped-system", "archive": row.get("archive"), "message": "archive has no mapped engine.* domain"})
        if row.get("status") == "missing_gateway":
            findings.append({"severity": "ERROR", "check": "dataset-missing-gateway", "archive": row.get("archive"), "message": "mapped system has missing engine.* gateway", "missing": row.get("missing")})
        if row.get("status") in {"visible_gap", "unmapped"}:
            findings.append({"severity": "ERROR", "check": "dataset-visible-gap", "archive": row.get("archive"), "message": "production gap is still visible", "risks": row.get("risks")})
    for q in scan.get("questions") or []:
        if q["engine_gateway_needed"] and not q["engine_gateway"]["declared"]:
            findings.append({"severity": "ERROR", "check": "gateway", "domain": q["domain"], "message": "gateway missing"})
        if q["engine_gateway_needed"] and q["capability"].get("missing"):
            findings.append({"severity": "ERROR", "check": "capability", "domain": q["domain"], "missing": q["capability"].get("missing")})
        if q["engine_gateway_needed"] and not q["null_provider"].get("present_signal"):
            findings.append({"severity": "ERROR", "check": "null-provider", "domain": q["domain"], "message": "replaceable domain has no visible NullProvider"})
        if q["engine_gateway_needed"] and not q["conformance"].get("present_signal"):
            findings.append({"severity": "ERROR", "check": "conformance", "domain": q["domain"], "message": "provider family has no conformance harness"})
    return findings
