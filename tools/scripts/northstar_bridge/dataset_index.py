from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from .contracts import BridgeContext, BridgeError, MAX_SEARCH_FILE_BYTES, now_utc
from .paths import is_text_file, rel
from .dataset_core import dataset_dirs, dataset_root, path_logic_signals, score_file
from .dataset_browser import profile_path


TOPIC_HINTS = {
    "ai": ["ai", "agent", "behavior", "task", "planner", "decision", "navigation"],
    "animation": ["animation", "anim", "skeleton", "blend", "ik", "pose"],
    "asset": ["asset", "import", "resource", "material", "texture", "model"],
    "audio": ["audio", "sound", "mixer", "bus", "stream"],
    "debug": ["debug", "profiler", "trace", "diagnostic", "log"],
    "physics": ["physics", "collision", "rigid", "cloth", "vehicle", "constraint"],
    "render": ["render", "shader", "material", "lighting", "shadow", "vfx"],
    "scene": ["scene", "world", "entity", "component", "prefab", "streaming"],
    "script": ["script", "vm", "binding", "event", "command"],
    "ui": ["ui", "frontend", "scaleform", "widget", "layout", "text"],
}


def _read_sample(path: Path, max_bytes: int = 8192) -> str:
    if not is_text_file(path) or path.stat().st_size > MAX_SEARCH_FILE_BYTES:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:max_bytes]


def _topic_scores(rel_path: str, sample: str) -> Dict[str, int]:
    hay = f"{rel_path}\n{sample}".lower()
    scores: Dict[str, int] = {}
    for topic, terms in TOPIC_HINTS.items():
        score = sum(hay.count(term) for term in terms)
        if score:
            scores[topic] = score
    return scores


def _knowledge_file_record(ctx: BridgeContext, root: Path, path: Path) -> Dict[str, Any]:
    drel = rel(dataset_root(ctx), path)
    sample = _read_sample(path)
    topics = _topic_scores(drel, sample)
    return {
        "path": rel(ctx.root, path),
        "dataset_relative_path": drel,
        "size_bytes": path.stat().st_size,
        "extension": path.suffix.lower() or "<none>",
        "text_like": is_text_file(path),
        "logic_score": score_file(path),
        "signals": path_logic_signals(path),
        "topics": topics,
    }


def rebuild_index(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("dataset index rebuild requires write mode", "write_disabled")
    dirs = dataset_dirs(ctx)
    dirs["index"].mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, Any]] = []
    directory_profiles: List[Dict[str, Any]] = []
    topic_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    extension_summary: Counter[str] = Counter()
    logic_candidates: List[Dict[str, Any]] = []

    if dirs["extracted"].exists():
        for path in dirs["extracted"].rglob("*"):
            if not path.is_file():
                continue
            record = _knowledge_file_record(ctx, dirs["extracted"], path)
            files.append(record)
            extension_summary[record["extension"]] += 1
            if record["logic_score"]:
                logic_candidates.append(record)
            for topic, score in record["topics"].items():
                if score > 0:
                    topic_index[topic].append({"path": record["path"], "score": score + record["logic_score"], "logic_score": record["logic_score"]})

        for top in sorted([p for p in dirs["extracted"].iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
            directory_profiles.append(profile_path(ctx, top, max_files=5000, sample_limit=30))

    for topic in list(topic_index):
        topic_index[topic] = sorted(topic_index[topic], key=lambda r: (-int(r.get("score", 0)), str(r.get("path", ""))))[:100]
    logic_candidates = sorted(logic_candidates, key=lambda r: (-int(r.get("logic_score", 0)), str(r.get("path", ""))))[:500]

    payload = {
        "schema": "northstar.dataset.index.v2",
        "rebuilt_at": now_utc(),
        "file_count": len(files),
        "extension_summary": dict(extension_summary.most_common(100)),
        "files": files[:20000],
    }
    out = dirs["index"] / "dataset-index.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    browser_payload = {
        "schema": "northstar.dataset.browserIndex.v1",
        "rebuilt_at": now_utc(),
        "directory_count": len(directory_profiles),
        "directories": directory_profiles,
    }
    browser_out = dirs["index"] / "dataset-browser-index.json"
    browser_out.write_text(json.dumps(browser_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    knowledge_payload = {
        "schema": "northstar.knowledgeRegistry.v1",
        "rebuilt_at": now_utc(),
        "dataset_root": rel(ctx.root, dataset_root(ctx)),
        "extracted_root": rel(ctx.root, dirs["extracted"]),
        "file_count": len(files),
        "directory_count": len(directory_profiles),
        "extension_summary": dict(extension_summary.most_common(50)),
        "topics": dict(sorted(topic_index.items())),
        "logic_candidates": logic_candidates,
        "query_hints": {topic: terms for topic, terms in sorted(TOPIC_HINTS.items())},
    }
    knowledge_out = dirs["index"] / "knowledge-registry.json"
    knowledge_out.write_text(json.dumps(knowledge_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_out = dirs["index"] / "knowledge-registry.md"
    md_out.write_text(render_knowledge_markdown(knowledge_payload), encoding="utf-8")

    return {
        "ok": True,
        "path": rel(ctx.root, out),
        "browser_path": rel(ctx.root, browser_out),
        "knowledge_path": rel(ctx.root, knowledge_out),
        "knowledge_markdown": rel(ctx.root, md_out),
        "file_count": len(files),
        "directory_count": len(directory_profiles),
        "topic_count": len(topic_index),
        "truncated": len(files) > 20000,
    }


def render_knowledge_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# North Star Dataset Knowledge Registry",
        "",
        f"- schema: `{payload.get('schema')}`",
        f"- rebuilt_at: `{payload.get('rebuilt_at')}`",
        f"- files: `{payload.get('file_count')}`",
        f"- directories: `{payload.get('directory_count')}`",
        "",
        "## Topics",
        "",
    ]
    topics = payload.get("topics", {}) if isinstance(payload.get("topics"), dict) else {}
    for topic, hits in topics.items():
        lines.append(f"### {topic}")
        for hit in list(hits)[:10]:
            lines.append(f"- `{hit.get('path')}` score={hit.get('score')} logic={hit.get('logic_score')}")
        lines.append("")
    lines.extend(["## Top logic candidates", ""])
    for item in list(payload.get("logic_candidates", []))[:50]:
        lines.append(f"- `{item.get('path')}` logic={item.get('logic_score')} topics={list((item.get('topics') or {}).keys())}")
    return "\n".join(lines) + "\n"
