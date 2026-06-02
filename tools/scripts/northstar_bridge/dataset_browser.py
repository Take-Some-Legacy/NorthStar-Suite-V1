from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .contracts import BridgeContext, BridgeError, MAX_SEARCH_FILE_BYTES
from .paths import is_text_file, rel
from .dataset_core import (
    KEY_FILE_NAMES,
    LOGIC_DIR_NAMES,
    dataset_root,
    path_logic_signals,
    read_json_file,
    safe_extracted_path,
    score_file,
)


def _iter_profile_files(base: Path, max_files: int) -> Iterable[Path]:
    count = 0
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        yield path
        count += 1
        if count >= max_files:
            break


def profile_path(ctx: BridgeContext, base: Path, max_files: int = 5000, sample_limit: int = 50) -> Dict[str, Any]:
    files = list(_iter_profile_files(base, max_files))
    ext = Counter((p.suffix.lower() or "<none>") for p in files)
    text_files = [p for p in files if is_text_file(p)]
    key_files = [p for p in files if p.name.lower() in KEY_FILE_NAMES]
    logic_files = sorted([p for p in files if score_file(p) > 0], key=lambda p: (-score_file(p), rel(base, p).lower()))[:sample_limit]
    logic_dirs = Counter()
    for path in logic_files:
        for part in path.relative_to(base).parts[:-1]:
            if part.lower() in LOGIC_DIR_NAMES:
                logic_dirs[part] += 1
    size_bytes = sum(p.stat().st_size for p in files if p.exists())
    manifest_path = base / ".northstar-dataset-manifest.json"
    manifest = read_json_file(manifest_path) if manifest_path.exists() else None
    score = min(100, len(logic_files) * 2 + len(key_files) * 4 + len(logic_dirs) * 3)
    return {
        "path": rel(ctx.root, base),
        "dataset_relative_path": rel(dataset_root(ctx), base),
        "name": base.name,
        "file_count_sampled": len(files),
        "text_file_count_sampled": len(text_files),
        "size_bytes_sampled": size_bytes,
        "logic_score": score,
        "extension_summary": dict(ext.most_common(20)),
        "key_files": [rel(ctx.root, p) for p in key_files[:sample_limit]],
        "logic_dirs": dict(logic_dirs.most_common(20)),
        "logic_files": [
            {"path": rel(ctx.root, p), "score": score_file(p), "signals": path_logic_signals(p), "size_bytes": p.stat().st_size}
            for p in logic_files
        ],
        "manifest": manifest,
        "truncated": len(files) >= max_files,
    }


def browse_directories(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    base = safe_extracted_path(ctx, str(args.get("path", "")), must_exist=False)
    if not base.exists():
        return {"ok": False, "reason": "not_materialized", "base": rel(ctx.root, base), "hint": "run dataset.materialize"}
    if not base.is_dir():
        raise BridgeError("dataset browser path is not a directory", "not_directory", {"path": rel(ctx.root, base)})
    depth = max(0, min(int(args.get("depth", 1)), 4))
    limit = max(1, min(int(args.get("limit", 80)), 500))
    root_parts = len(base.parts)
    dirs: List[Path] = []
    for path in sorted(base.rglob("*"), key=lambda p: p.as_posix().lower()):
        if len(dirs) >= limit:
            break
        if path.is_dir() and len(path.parts) - root_parts <= depth:
            dirs.append(path)
    max_files = max(50, min(int(args.get("max_files", 500)), 5000))
    profile = bool(args.get("profile", True))
    items = [profile_path(ctx, path, max_files=max_files, sample_limit=12) if profile else {"path": rel(ctx.root, path), "name": path.name} for path in dirs]
    return {"ok": True, "base": rel(ctx.root, base), "items": items, "truncated": len(dirs) >= limit, "depth": depth}


def profile_directory(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    base = safe_extracted_path(ctx, str(args.get("path", "")))
    if not base.is_dir():
        raise BridgeError("dataset profile target is not a directory", "not_directory", {"path": rel(ctx.root, base)})
    max_files = max(100, min(int(args.get("max_files", 8000)), 50000))
    sample_limit = max(10, min(int(args.get("sample_limit", 100)), 500))
    return {"ok": True, "profile": profile_path(ctx, base, max_files=max_files, sample_limit=sample_limit)}


def search_directories(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query", ""))
    case = bool(args.get("case_sensitive", False))
    q_cmp = query if case else query.lower()
    limit = max(1, min(int(args.get("limit", 100)), 500))
    base = safe_extracted_path(ctx, "", must_exist=False)
    if not base.exists():
        return {"query": query, "base": rel(ctx.root, base), "hits": [], "reason": "not_materialized"}
    hits: List[Dict[str, Any]] = []
    for path in base.rglob("*"):
        if len(hits) >= limit:
            break
        if not path.is_file() or not is_text_file(path) or path.stat().st_size > MAX_SEARCH_FILE_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hay = text if case else text.lower()
        if q_cmp in hay:
            line_no = next((idx for idx, line in enumerate(text.splitlines(), 1) if q_cmp in (line if case else line.lower())), None)
            hits.append({"path": rel(ctx.root, path), "line": line_no})
    return {"query": query, "base": rel(ctx.root, base), "hits": hits, "truncated": len(hits) >= limit}


def search_logic(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query", ""))
    case = bool(args.get("case_sensitive", False))
    limit = max(1, min(int(args.get("limit", 100)), 500))
    base = safe_extracted_path(ctx, str(args.get("path", "")), must_exist=False)
    if not base.exists():
        return {"query": query, "base": rel(ctx.root, base), "hits": [], "reason": "not_materialized"}
    q_cmp = query if case else query.lower()
    hits: List[Tuple[int, Dict[str, Any]]] = []
    for path in base.rglob("*"):
        if len(hits) >= limit * 4:
            break
        if not path.is_file() or not is_text_file(path) or path.stat().st_size > MAX_SEARCH_FILE_BYTES:
            continue
        path_cmp = rel(base, path) if case else rel(base, path).lower()
        text = path.read_text(encoding="utf-8", errors="replace")
        hay = text if case else text.lower()
        path_match = bool(query and q_cmp in path_cmp)
        content_match = bool(query and q_cmp in hay)
        if query and not path_match and not content_match:
            continue
        if not query and score_file(path) <= 0:
            continue
        line_no = None
        snippet = ""
        if content_match:
            for idx, line in enumerate(text.splitlines(), 1):
                if q_cmp in (line if case else line.lower()):
                    line_no = idx
                    snippet = line.strip()[:500]
                    break
        score = score_file(path) + (15 if content_match else 0) + (6 if path_match else 0)
        hits.append((score, {"path": rel(ctx.root, path), "dataset_relative_path": rel(dataset_root(ctx), path), "line": line_no, "score": score, "signals": path_logic_signals(path), "snippet": snippet}))
    sorted_hits = [item for _, item in sorted(hits, key=lambda kv: (-kv[0], kv[1]["path"].lower()))[:limit]]
    return {"ok": True, "query": query, "base": rel(ctx.root, base), "hits": sorted_hits, "truncated": len(hits) > limit}
