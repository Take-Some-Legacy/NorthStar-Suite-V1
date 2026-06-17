from __future__ import annotations

import argparse
import fnmatch
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .paths import rel

TEXT_EXTENSIONS = {
    ".bat", ".cmd", ".cfg", ".conf", ".css", ".csv", ".frag", ".glsl",
    ".h", ".hpp", ".html", ".ini", ".json", ".jsonl", ".lock", ".md", ".py",
    ".rs", ".shader", ".sql", ".toml", ".txt", ".vert", ".xml", ".yaml", ".yml",
}
SKIP_DIR_NAMES = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "target", "dist", "build",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
DENY_PARTS = {
    ".git",
    ".takesome/secrets",
    ".takesome/ai-bridge/patch-backups",
}


def _emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if bool(payload.get("ok", True)) else 1


def _rel_parts(path: Path) -> tuple[str, ...]:
    return tuple(part.replace("\\", "/") for part in path.parts)


def _safe_path(root: Path, raw: str, *, must_exist: bool = False) -> Path:
    raw = str(raw or ".").strip() or "."
    candidate = Path(raw)
    path = candidate if candidate.is_absolute() else root / candidate
    path = path.resolve()
    root_resolved = root.resolve()
    try:
        rel_path = path.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {raw}") from exc
    rel_posix = rel_path.as_posix()
    for denied in DENY_PARTS:
        if rel_posix == denied or rel_posix.startswith(denied + "/"):
            raise ValueError(f"path is denied by operator fs policy: {rel_posix}")
    if must_exist and not path.exists():
        raise FileNotFoundError(rel_posix or ".")
    return path


def _is_text_candidate(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS


def _looks_binary(path: Path) -> bool:
    try:
        return b"\0" in path.read_bytes()[:4096]
    except Exception:
        return True


def _iter_files(root: Path, roots: Iterable[str], *, patterns: Iterable[str] = ()) -> Iterable[Path]:
    pats = [p for p in patterns if p]
    for raw in roots:
        try:
            start = _safe_path(root, raw, must_exist=True)
        except Exception:
            continue
        if start.is_file():
            candidates = [start]
        else:
            candidates = start.rglob("*")
        for path in candidates:
            try:
                if path.is_dir():
                    continue
                relp = path.relative_to(root.resolve()).as_posix()
            except Exception:
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if pats and not any(fnmatch.fnmatch(path.name, pat) or fnmatch.fnmatch(relp, pat) for pat in pats):
                continue
            yield path


def ns_list_dir_command(root: Path, ns: argparse.Namespace) -> int:
    try:
        path = _safe_path(root, ns.path, must_exist=True)
        if not path.is_dir():
            return _emit({"schema": "northstar.operator_fs.list_dir.v1", "ok": False, "error": "path is not a directory", "path": rel(root, path)})
        limit = max(1, min(int(ns.limit), 2000))
        rows = []
        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if len(rows) >= limit:
                break
            name = child.name
            if name in SKIP_DIR_NAMES and not bool(getattr(ns, "include_skipped", False)):
                continue
            rows.append({
                "path": rel(root, child),
                "name": name,
                "kind": "dir" if child.is_dir() else "file",
                "size_bytes": child.stat().st_size if child.is_file() else None,
            })
        return _emit({"schema": "northstar.operator_fs.list_dir.v1", "ok": True, "path": rel(root, path), "count": len(rows), "items": rows})
    except Exception as exc:
        return _emit({"schema": "northstar.operator_fs.list_dir.v1", "ok": False, "error": str(exc)})


def ns_read_file_command(root: Path, ns: argparse.Namespace) -> int:
    try:
        path = _safe_path(root, ns.path, must_exist=True)
        if not path.is_file():
            return _emit({"schema": "northstar.operator_fs.read_file.v1", "ok": False, "error": "path is not a file", "path": rel(root, path)})
        max_bytes = max(1, min(int(ns.max_bytes), 256 * 1024))
        offset = max(0, int(getattr(ns, "offset", 0) or 0))
        raw = path.read_bytes()
        chunk = raw[offset:offset + max_bytes]
        binary = b"\0" in chunk[:4096]
        if binary:
            return _emit({"schema": "northstar.operator_fs.read_file.v1", "ok": False, "path": rel(root, path), "error": "binary content refused by text read layer", "size_bytes": len(raw)})
        text = chunk.decode("utf-8", errors="replace")
        return _emit({
            "schema": "northstar.operator_fs.read_file.v1",
            "ok": True,
            "path": rel(root, path),
            "offset": offset,
            "bytes_read": len(chunk),
            "size_bytes": len(raw),
            "truncated": offset + len(chunk) < len(raw),
            "content": text,
        })
    except Exception as exc:
        return _emit({"schema": "northstar.operator_fs.read_file.v1", "ok": False, "error": str(exc)})


def ns_search_text_command(root: Path, ns: argparse.Namespace) -> int:
    query = str(ns.query or "")
    if not query:
        return _emit({"schema": "northstar.operator_fs.search_text.v1", "ok": False, "error": "query is required"})
    try:
        flags = 0 if ns.case_sensitive else re.IGNORECASE
        pattern = re.compile(query if ns.regex else re.escape(query), flags)
    except re.error as exc:
        return _emit({"schema": "northstar.operator_fs.search_text.v1", "ok": False, "error": f"invalid regex: {exc}"})
    roots = ns.root or ["."]
    globs = ns.glob or []
    limit = max(1, min(int(ns.limit), 2000))
    results = []
    scanned = 0
    for path in _iter_files(root, roots, patterns=globs):
        if len(results) >= limit:
            break
        if not _is_text_candidate(path) or _looks_binary(path):
            continue
        scanned += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for idx, line in enumerate(lines, start=1):
            if pattern.search(line):
                results.append({"path": rel(root, path), "line": idx, "text": line})
                if len(results) >= limit:
                    break
    return _emit({"schema": "northstar.operator_fs.search_text.v1", "ok": True, "query": query, "scanned_files": scanned, "count": len(results), "results": results})


def ns_file_stat_command(root: Path, ns: argparse.Namespace) -> int:
    rows = []
    ok = True
    for raw in ns.paths:
        try:
            path = _safe_path(root, raw, must_exist=True)
            stat = path.stat()
            rows.append({"path": rel(root, path), "kind": "dir" if path.is_dir() else "file", "size_bytes": stat.st_size, "mtime": stat.st_mtime})
        except Exception as exc:
            ok = False
            rows.append({"path": raw, "error": str(exc)})
    return _emit({"schema": "northstar.operator_fs.file_stat.v1", "ok": ok, "count": len(rows), "items": rows})


def ns_tree_command(root: Path, ns: argparse.Namespace) -> int:
    try:
        start = _safe_path(root, ns.path, must_exist=True)
        if not start.is_dir():
            return _emit({"schema": "northstar.operator_fs.tree.v1", "ok": False, "error": "path is not a directory", "path": rel(root, start)})
        max_depth = max(0, min(int(ns.depth), 12))
        limit = max(1, min(int(ns.limit), 5000))
        root_resolved = root.resolve()
        start_depth = len(start.relative_to(root_resolved).parts)
        rows = []
        for path in sorted(start.rglob("*"), key=lambda p: p.as_posix().lower()):
            if len(rows) >= limit:
                break
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            try:
                depth = len(path.relative_to(root_resolved).parts) - start_depth
            except Exception:
                continue
            if depth > max_depth:
                continue
            rows.append({"path": rel(root, path), "kind": "dir" if path.is_dir() else "file", "size_bytes": path.stat().st_size if path.is_file() else None, "depth": depth})
        return _emit({"schema": "northstar.operator_fs.tree.v1", "ok": True, "path": rel(root, start), "depth": max_depth, "count": len(rows), "items": rows})
    except Exception as exc:
        return _emit({"schema": "northstar.operator_fs.tree.v1", "ok": False, "error": str(exc)})


def ns_count_lines_command(root: Path, ns: argparse.Namespace) -> int:
    roots = ns.root or ["."]
    globs = ns.glob or ["*.py", "*.rs", "*.toml", "*.json", "*.md", "*.yml", "*.yaml"]
    limit = max(1, min(int(ns.limit), 20000))
    rows = []
    total = 0
    for path in _iter_files(root, roots, patterns=globs):
        if len(rows) >= limit:
            break
        if not _is_text_candidate(path) or _looks_binary(path):
            continue
        try:
            count = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
        except Exception:
            continue
        total += count
        rows.append({"path": rel(root, path), "lines": count})
    rows.sort(key=lambda item: item["lines"], reverse=True)
    return _emit({"schema": "northstar.operator_fs.count_lines.v1", "ok": True, "file_count": len(rows), "total_lines": total, "items": rows})
