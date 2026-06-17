from __future__ import annotations

import os
from pathlib import Path

from .model import DatasetHit

DATASET_ROOTS = ("CONSTANTS", "SNAPSHOTS", "RESEARCH", "Data", "docs", "Docs")
ROOT_DOCS = ("README.md", "WORKSPACE.md")
REQUIRED_NAMES = (
    "CAPABILITY", "CONFORMANCE", "GATEWAY", "PROVIDER", "NO_LEGACY", "NO-LEGACY",
    "SCHEDULING", "INTENTS", "ECS_ENTITY", "BOUNDARIES", "REQUEST_NOTES", "STATUS_BLOCK",
    "RUNTIME_MODULE", "ENGINE_AS_HOST", "ARCHITECTURE_INVARIANTS",
)
IGNORED_DIRS = {".git", ".takesome", "target", "logs", "cache", "stamps", "node_modules", "__pycache__"}


def _keywords_for_task(task_title: str) -> set[str]:
    keywords = {"engine", "gateway", "provider", "capability", "conformance", "diagnostics", "legacy", "fallback", "dto", "world", "entityid", "dataset"}
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
        if clean.startswith("#") or "final invariant" in lowered or "rule:" in lowered or any(keyword in lowered for keyword in keywords):
            excerpts.append(clean)
        if len(excerpts) >= limit:
            break
    return excerpts[:limit]


def _iter_dataset_files(root: Path, *, max_files: int = 300):
    yielded = 0
    for doc in ROOT_DOCS:
        path = root / doc
        if path.exists():
            yield path, path.relative_to(root)
            yielded += 1
    for name in DATASET_ROOTS:
        scan_root = root / name
        if not scan_root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = [dirname for dirname in dirnames if dirname not in IGNORED_DIRS]
            for filename in filenames:
                path = Path(dirpath) / filename
                if path.suffix.lower() not in {".md", ".txt"}:
                    continue
                yield path, path.relative_to(root)
                yielded += 1
                if yielded >= max_files:
                    return
    # Fallback for datasets kept as root-level named markdown files.
    for path in root.glob("*.md"):
        if path.name in ROOT_DOCS:
            continue
        upper = path.name.upper()
        if any(token in upper for token in REQUIRED_NAMES):
            yield path, path.relative_to(root)
            yielded += 1
            if yielded >= max_files:
                return


def resolve_dataset_context(root: Path, task_title: str, *, max_files: int = 12, excerpt_limit: int = 5) -> list[DatasetHit]:
    keywords = _keywords_for_task(task_title)
    candidates: list[tuple[int, Path, Path]] = []
    for path, rel in _iter_dataset_files(root):
        upper_name = rel.name.upper()
        score = 0
        if any(token in upper_name for token in REQUIRED_NAMES):
            score += 80
        score += sum(1 for keyword in keywords if keyword in str(rel).lower())
        candidates.append((score, path, rel))
    candidates.sort(key=lambda item: (-item[0], str(item[2])))
    hits: list[DatasetHit] = []
    for _, path, rel in candidates[: max(1, max_files)]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpts = _extract_relevant_lines(text, keywords, limit=excerpt_limit) or ["Engine as Host.", "Service as Plugin.", "Capability as Option."][:excerpt_limit]
        hits.append(DatasetHit(str(rel), f"matched task keywords: {', '.join(sorted(list(keywords))[:8])}", excerpts))
    return hits
