from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Iterable

from .contracts import BridgeContext, BridgeError, SAFE_TEXT_EXTENSIONS
from .paths import is_under_safe_root, rel

SKIP_DIR_NAMES = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "target", "dist", "build",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
TEXT_EXTENSIONS = set(SAFE_TEXT_EXTENSIONS)


def _safe_path(ctx: BridgeContext, raw: str, *, must_exist: bool = False) -> Path:
    raw = str(raw or ".").strip() or "."
    candidate = Path(raw)
    if candidate.is_absolute():
        path = candidate.resolve()
    else:
        path = (ctx.root / candidate).resolve()
    root = ctx.root.resolve()
    try:
        rel_path = path.relative_to(root)
    except ValueError as exc:
        raise BridgeError("path escapes repository root", "unsafe_path", {"path": raw}) from exc
    rel_posix = rel_path.as_posix()
    rel_for_policy = "" if rel_posix == "." else rel_posix
    if rel_for_policy and not is_under_safe_root(rel_for_policy):
        raise BridgeError("path is outside AI bridge safe roots", "unsafe_path", {"path": rel_for_policy})
    if must_exist and not path.exists():
        raise BridgeError("path does not exist", "not_found", {"path": rel_for_policy or "."})
    return path


def _is_text_candidate(path: Path) -> bool:
    return path.is_file() and (path.suffix.lower() in TEXT_EXTENSIONS or path.name in {"Cargo.lock", "LICENSE", "README", "Makefile"})


def _looks_binary(path: Path) -> bool:
    try:
        return b"\0" in path.read_bytes()[:4096]
    except Exception:
        return True


def _iter_files(ctx: BridgeContext, roots: Iterable[str], *, patterns: Iterable[str] = ()) -> Iterable[Path]:
    pats = [str(p) for p in patterns if str(p)]
    for raw in roots:
        try:
            start = _safe_path(ctx, raw, must_exist=True)
        except BridgeError:
            continue
        candidates = [start] if start.is_file() else start.rglob("*")
        for path in candidates:
            try:
                if path.is_dir():
                    continue
                relp = path.relative_to(ctx.root.resolve()).as_posix()
            except Exception:
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if pats and not any(fnmatch.fnmatch(path.name, pat) or fnmatch.fnmatch(relp, pat) for pat in pats):
                continue
            yield path


def list_dir(ctx: BridgeContext, args: dict[str, Any]) -> dict[str, Any]:
    path = _safe_path(ctx, str(args.get("path") or "."), must_exist=True)
    if not path.is_dir():
        raise BridgeError("path is not a directory", "not_directory", {"path": rel(ctx.root, path)})
    limit = max(1, min(int(args.get("limit", 200) or 200), 2000))
    include_skipped = bool(args.get("include_skipped", False))
    rows: list[dict[str, Any]] = []
    for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if len(rows) >= limit:
            break
        if child.name in SKIP_DIR_NAMES and not include_skipped:
            continue
        rows.append({
            "path": rel(ctx.root, child),
            "name": child.name,
            "kind": "dir" if child.is_dir() else "file",
            "size_bytes": child.stat().st_size if child.is_file() else None,
        })
    return {"schema": "northstar.operator_fs.list_dir.v1", "ok": True, "path": rel(ctx.root, path), "count": len(rows), "items": rows}


def read_file(ctx: BridgeContext, args: dict[str, Any]) -> dict[str, Any]:
    path = _safe_path(ctx, str(args.get("path") or ""), must_exist=True)
    if not path.is_file():
        raise BridgeError("path is not a file", "not_file", {"path": rel(ctx.root, path)})
    max_bytes = max(1, min(int(args.get("max_bytes", 65536) or 65536), 256 * 1024))
    offset = max(0, int(args.get("offset", 0) or 0))
    raw = path.read_bytes()
    chunk = raw[offset:offset + max_bytes]
    if b"\0" in chunk[:4096]:
        raise BridgeError("binary content refused by text read layer", "binary_refused", {"path": rel(ctx.root, path), "size_bytes": len(raw)})
    return {
        "schema": "northstar.operator_fs.read_file.v1",
        "ok": True,
        "path": rel(ctx.root, path),
        "offset": offset,
        "bytes_read": len(chunk),
        "size_bytes": len(raw),
        "truncated": offset + len(chunk) < len(raw),
        "content": chunk.decode("utf-8", errors="replace"),
    }


def search_text(ctx: BridgeContext, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "")
    if not query:
        raise BridgeError("query is required", "missing_query")
    try:
        flags = 0 if bool(args.get("case_sensitive", False)) else re.IGNORECASE
        pattern = re.compile(query if bool(args.get("regex", False)) else re.escape(query), flags)
    except re.error as exc:
        raise BridgeError(f"invalid regex: {exc}", "invalid_regex") from exc
    roots = [str(x) for x in args.get("roots", []) or args.get("root", []) or ["."]]
    globs = [str(x) for x in args.get("glob", []) or []]
    limit = max(1, min(int(args.get("limit", 100) or 100), 2000))
    rows: list[dict[str, Any]] = []
    scanned = 0
    for path in _iter_files(ctx, roots, patterns=globs):
        if len(rows) >= limit:
            break
        if not _is_text_candidate(path) or _looks_binary(path):
            continue
        scanned += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for index, line in enumerate(lines, start=1):
            if pattern.search(line):
                rows.append({"path": rel(ctx.root, path), "line": index, "text": line})
                if len(rows) >= limit:
                    break
    return {"schema": "northstar.operator_fs.search_text.v1", "ok": True, "query": query, "scanned_files": scanned, "count": len(rows), "results": rows}


def file_stat(ctx: BridgeContext, args: dict[str, Any]) -> dict[str, Any]:
    paths = [str(x) for x in args.get("paths", []) or []]
    if not paths:
        raise BridgeError("paths are required", "missing_paths")
    rows: list[dict[str, Any]] = []
    ok = True
    for raw in paths:
        try:
            path = _safe_path(ctx, raw, must_exist=True)
            stat = path.stat()
            rows.append({"path": rel(ctx.root, path), "kind": "dir" if path.is_dir() else "file", "size_bytes": stat.st_size, "mtime": stat.st_mtime})
        except BridgeError as exc:
            ok = False
            rows.append({"path": raw, "error": str(exc), "code": exc.code})
    return {"schema": "northstar.operator_fs.file_stat.v1", "ok": ok, "count": len(rows), "items": rows}


def tree(ctx: BridgeContext, args: dict[str, Any]) -> dict[str, Any]:
    start = _safe_path(ctx, str(args.get("path") or "."), must_exist=True)
    if not start.is_dir():
        raise BridgeError("path is not a directory", "not_directory", {"path": rel(ctx.root, start)})
    max_depth = max(0, min(int(args.get("depth", 2) or 2), 12))
    limit = max(1, min(int(args.get("limit", 500) or 500), 5000))
    root = ctx.root.resolve()
    start_depth = 0 if start == root else len(start.relative_to(root).parts)
    rows: list[dict[str, Any]] = []
    for path in sorted(start.rglob("*"), key=lambda p: p.as_posix().lower()):
        if len(rows) >= limit:
            break
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            depth = len(path.relative_to(root).parts) - start_depth
        except Exception:
            continue
        if depth > max_depth:
            continue
        rows.append({"path": rel(ctx.root, path), "kind": "dir" if path.is_dir() else "file", "size_bytes": path.stat().st_size if path.is_file() else None, "depth": depth})
    return {"schema": "northstar.operator_fs.tree.v1", "ok": True, "path": rel(ctx.root, start), "depth": max_depth, "count": len(rows), "items": rows}


def count_lines(ctx: BridgeContext, args: dict[str, Any]) -> dict[str, Any]:
    roots = [str(x) for x in args.get("roots", []) or args.get("root", []) or ["."]]
    globs = [str(x) for x in args.get("glob", []) or ["*.py", "*.rs", "*.toml", "*.json", "*.md", "*.yml", "*.yaml"]]
    limit = max(1, min(int(args.get("limit", 2000) or 2000), 20000))
    rows: list[dict[str, Any]] = []
    total = 0
    for path in _iter_files(ctx, roots, patterns=globs):
        if len(rows) >= limit:
            break
        if not _is_text_candidate(path) or _looks_binary(path):
            continue
        try:
            count = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
        except Exception:
            continue
        total += count
        rows.append({"path": rel(ctx.root, path), "lines": count})
    rows.sort(key=lambda item: item["lines"], reverse=True)
    return {"schema": "northstar.operator_fs.count_lines.v1", "ok": True, "file_count": len(rows), "total_lines": total, "items": rows}
