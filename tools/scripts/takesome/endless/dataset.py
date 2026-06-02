from __future__ import annotations

import os
from pathlib import Path

from .model import DatasetHit

DATASET_DIR_NAMES = {"CONSTANTS", "SNAPSHOTS", "RESEARCH", "DATASET", "Data", "docs", "Docs"}
REQUIRED_NAMES = (
    "CAPABILITY",
    "CONFORMANCE",
    "GATEWAY",
    "PROVIDER",
    "NO_LEGACY",
    "NO-LEGACY",
    "SCHEDULING",
    "INTENTS",
    "ECS_ENTITY",
    "BOUNDARIES",
    "REQUEST_NOTES",
    "STATUS_BLOCK",
    "RUNTIME_MODULE",
    "ENGINE_AS_HOST",
    "ARCHITECTURE_INVARIANTS",
)
ALWAYS_INCLUDE = {"README.md", "WORKSPACE.md"}
IGNORED_DIRS = {
    ".git",
    ".idea",
    ".vs",
    ".takesome",
    "target",
    "logs",
    "cache",
    "stamps",
    "node_modules",
    "bin",
    "obj",
    "out",
    "dist",
    "artifacts",
    "__pycache__",
}


def _looks_like_dataset_file(path: Path) -> bool:
    if path.name in ALWAYS_INCLUDE:
        return True
    if path.suffix.lower() not in {".md", ".txt"}:
        return False
    upper_name = path.name.upper()
    if any(part in DATASET_DIR_NAMES for part in path.parts):
        return True
    return any(token in upper_name for token in REQUIRED_NAMES)


def _keywords_for_task(task_title: str) -> set[str]:
    keywords = {
        "engine",
        "gateway",
        "provider",
        "capability",
        "conformance",
        "diagnostics",
        "legacy",
        "fallback",
        "dto",
        "world",
        "entityid",
        "dataset",
    }
    for raw in task_title.replace("/", " ").replace("_", " ").replace("-", " ").split():
        token = raw.strip().lower()
        if len(token) >= 4:
            keywords.add(token)
    return keywords


def _extract_relevant_lines(text: str, keywords: set[str], *, limit: int) -> list[str]:
    excerpts: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        lowered = clean.lower()
        if clean.startswith("#") or "final invariant" in lowered or "rule:" in lowered:
            excerpts.append(clean)
        elif any(keyword in lowered for keyword in keywords):
            excerpts.append(clean)
        if len(excerpts) >= limit:
            break
    return excerpts[:limit]


def _iter_candidate_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_DIRS]
        current = Path(dirpath)
        try:
            rel_dir = current.relative_to(root)
        except ValueError:
            continue
        if any(part in IGNORED_DIRS for part in rel_dir.parts):
            continue
        for filename in filenames:
            path = current / filename
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if _looks_like_dataset_file(rel):
                yield path, rel


def resolve_dataset_context(root: Path, task_title: str, *, max_files: int = 12, excerpt_limit: int = 5) -> list[DatasetHit]:
    keywords = _keywords_for_task(task_title)
    candidates: list[tuple[int, Path, Path]] = []
    for path, rel in _iter_candidate_files(root):
        upper_name = rel.name.upper()
        score = 0
        if any(part in DATASET_DIR_NAMES for part in rel.parts):
            score += 50
        if any(token in upper_name for token in REQUIRED_NAMES):
            score += 80
        if rel.name in ALWAYS_INCLUDE:
            score += 15
        score += sum(1 for keyword in keywords if keyword in str(rel).lower())
        candidates.append((score, path, rel))
    candidates.sort(key=lambda item: (-item[0], str(item[2])))

    hits: list[DatasetHit] = []
    for _, path, rel in candidates[: max(1, max_files)]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpts = _extract_relevant_lines(text, keywords, limit=excerpt_limit)
        if not excerpts:
            excerpts = ["Engine as Host.", "Service as Plugin.", "Capability as Option."][:excerpt_limit]
        hits.append(
            DatasetHit(
                path=str(rel),
                reason=f"matched task keywords: {', '.join(sorted(list(keywords))[:8])}",
                excerpts=excerpts,
            )
        )
    return hits
