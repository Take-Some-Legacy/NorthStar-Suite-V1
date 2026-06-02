from __future__ import annotations

BINARY_ARTIFACT_TRANSFER_BLOCKED = "binary_artifact_transfer_blocked"
_BINARY_ARTIFACT_SUFFIXES = {
    ".zip", ".7z", ".rar", ".tar", ".gz", ".xz", ".zst",
    ".dll", ".exe", ".pdb", ".lib", ".obj", ".o",
    ".png", ".jpg", ".jpeg", ".dds", ".ytd", ".ydd", ".nepak",
    ".woff", ".woff2",
}
_BINARY_TRANSFER_NAME_HINTS = (".b64", "b64_", "base64", "chunk", "part00", "part01")

def _binary_artifact_write_rejection(path: str, content: str = "") -> dict[str, object] | None:
    suffixes = [s.lower() for s in Path(str(path)).suffixes]
    lowered_path = str(path).lower()
    direct_binary_path = any(s in _BINARY_ARTIFACT_SUFFIXES for s in suffixes)
    chunk_like_path = any(hint in lowered_path for hint in _BINARY_TRANSFER_NAME_HINTS)
    sample = "".join(str(content).split())[:64]
    encoded_zip_payload = sample.startswith("UEsDB") or sample.startswith("PK")
    encoded_7z_payload = sample.startswith("N3q8") or sample.startswith("7z")
    if not (direct_binary_path or (chunk_like_path and (encoded_zip_payload or encoded_7z_payload))):
        return None
    return {
        "ok": False,
        "error": BINARY_ARTIFACT_TRANSFER_BLOCKED,
        "message": 'Binary artifact transfer is not supported through text write surface. Use artifact download/local file path/import command.',
        "display": "[BLOCKED] binary artifact write rejected",
        "path": str(path),
        "reason": 'bridge.write_text_file is text-only and may corrupt binary payload',
        "next": [
            "download artifact locally",
            "extract into workspace",
            "run tools.doctor.full",
            "run build.plugins.force.dev",
        ],
    }


import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from .contracts import BridgeContext, BridgeError, MAX_READ_BYTES_DEFAULT, MAX_SEARCH_FILE_BYTES
from .paths import backup_file, is_text_file, is_under_safe_root, latest_existing, norm_rel, read_text_file, rel, safe_path

def read_text(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    path = safe_path(ctx, str(args.get("path", "")))
    if path.is_dir():
        entries = [
            {"name": child.name, "kind": "dir" if child.is_dir() else "file", "size_bytes": child.stat().st_size if child.is_file() else None}
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:300]
        ]
        return {"kind": "directory", "path": rel(ctx.root, path), "entries": entries, "truncated": len(entries) >= 300}
    text, truncated, size = read_text_file(path, int(args.get("max_bytes", MAX_READ_BYTES_DEFAULT)))
    return {"kind": "file", "path": rel(ctx.root, path), "size_bytes": size, "truncated": truncated, "content": text}

def write_text(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    _binary_rejection = _binary_artifact_write_rejection(str(args.get("path", "")), str(args.get("content", "")))
    if _binary_rejection is not None:
        return _binary_rejection
    if not ctx.write_enabled:
        raise BridgeError("write_text rejected because NORTHSTAR_AI_BRIDGE_WRITE is not enabled", "write_disabled")
    path = safe_path(ctx, str(args.get("path", "")), must_exist=False)
    if not is_text_file(path):
        raise BridgeError("target extension is not text-whitelisted", "not_text", {"path": rel(ctx.root, path)})
    backup = backup_file(ctx, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = str(args.get("content", ""))
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": rel(ctx.root, path), "bytes_written": len(content.encode("utf-8")), "backup": rel(ctx.root, backup) if backup else None}

def delete_path(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("delete_path rejected because NORTHSTAR_AI_BRIDGE_WRITE is not enabled", "write_disabled")
    path = safe_path(ctx, str(args.get("path", "")), must_exist=True)
    recursive = bool(args.get("recursive", False))
    dry_run = bool(args.get("dry_run", False))
    if path == ctx.root.resolve():
        raise BridgeError("refusing to delete repository root", "unsafe_path")
    item = {
        "path": rel(ctx.root, path),
        "kind": "directory" if path.is_dir() else "file",
        "dry_run": dry_run,
    }
    if dry_run:
        if path.is_dir():
            item["requires_recursive"] = True
        return {"ok": True, "deleted": False, **item}
    if path.is_dir():
        if not recursive:
            raise BridgeError("directory deletion requires recursive=true", "recursive_required", {"path": rel(ctx.root, path)})
        shutil.rmtree(path)
        return {"ok": True, "deleted": True, **item, "backup": None}
    backup = backup_file(ctx, path)
    size = path.stat().st_size
    path.unlink()
    return {
        "ok": True,
        "deleted": True,
        **item,
        "size_bytes": size,
        "backup": rel(ctx.root, backup) if backup else None,
    }

def search_text(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query", ""))
    regex = bool(args.get("regex", False))
    case = bool(args.get("case_sensitive", False))
    limit = max(1, min(int(args.get("limit", 100)), 200))
    roots = args.get("roots") or ["docs", "tools/scripts", "config", "Plugins", "NewEngine/neocore2/crates", "NewEngine/neocore2/apps"]
    flags = 0 if case else re.IGNORECASE
    pattern = re.compile(query, flags) if regex else None
    hits: List[Dict[str, Any]] = []
    for root_arg in roots:
        try:
            base = safe_path(ctx, str(root_arg), must_exist=True)
        except BridgeError:
            continue
        files = [base] if base.is_file() else list(base.rglob("*"))
        for path in files:
            if len(hits) >= limit:
                break
            if not path.is_file() or not is_text_file(path) or path.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), 1):
                matched = bool(pattern.search(line)) if pattern else ((query if case else query.lower()) in (line if case else line.lower()))
                if matched:
                    hits.append({"path": rel(ctx.root, path), "line": line_no, "text": line[:500]})
                    break
            if len(hits) >= limit:
                break
    return {"query": query, "scanned_roots": roots, "hits": hits, "truncated": len(hits) >= limit}

def list_tree(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    base = ctx.root if str(args.get("path", ".")) in {"", "."} else safe_path(ctx, str(args.get("path")))
    max_depth = max(0, min(int(args.get("max_depth", 2)), 6))
    limit = max(1, min(int(args.get("limit", 300)), 2000))
    base_parts = len(base.relative_to(ctx.root).parts) if base != ctx.root else 0
    items: List[Dict[str, Any]] = []
    for path in sorted(base.rglob("*"), key=lambda p: p.as_posix().lower()):
        if len(items) >= limit:
            break
        try:
            rel_path = path.relative_to(ctx.root).as_posix()
        except ValueError:
            continue
        depth = len(path.relative_to(ctx.root).parts) - base_parts
        if depth > max_depth or not is_under_safe_root(rel_path):
            continue
        items.append({"path": rel_path, "kind": "dir" if path.is_dir() else "file", "size_bytes": path.stat().st_size if path.is_file() else None})
    return {"path": rel(ctx.root, base), "items": items, "truncated": len(items) >= limit}

def list_logs(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"logs": latest_existing(ctx.root, ["lastbuild.log", "lastbuild-all.log", "buildERR-*.log", ".takesome/ai-bridge/logs/*.jsonl", ".takesome/incidents/*/summary.md", "NewEngine/neocore2/logs/**/*.log"], max(1, min(int(args.get("limit", 30)), 100)))}

def latest_incident(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    items = latest_existing(ctx.root, ["last-incident.md", "last-incident.json", ".takesome/incidents/*/summary.md"], 10)
    max_bytes = int(args.get("max_bytes", 256 * 1024))
    docs: List[Dict[str, Any]] = []
    for item in items:
        path = ctx.root / item["path"]
        if path.exists() and path.is_file() and is_text_file(path):
            text, truncated, size = read_text_file(path, max_bytes)
            docs.append({**item, "content": text, "truncated": truncated, "size_bytes": size})
    return {"incidents": docs}

def git_status(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not (ctx.root / ".git").exists():
        return {"ok": False, "reason": "not_a_git_checkout"}
    proc = subprocess.run(["git", "status", "--short"], cwd=str(ctx.root), text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=None)
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}

def patch_preview(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    patch_path = safe_path(ctx, str(args.get("patch_path", "")))
    if patch_path.suffix.lower() != ".zip":
        raise BridgeError("only .zip patch preview is supported", "invalid_patch")
    entries: List[Dict[str, Any]] = []
    unsafe: List[Dict[str, Any]] = []
    with zipfile.ZipFile(patch_path, "r") as zf:
        for info in zf.infolist():
            try:
                member = norm_rel(info.filename)
                safe = is_under_safe_root(member) or member in {"DELETE_FILES.txt", "aiBridge.bat", "aiBridgeServer.bat"}
            except BridgeError:
                member = info.filename
                safe = False
            item = {"path": member, "size_bytes": info.file_size, "is_dir": info.is_dir(), "safe": safe}
            entries.append(item)
            if not safe:
                unsafe.append(item)
    return {"patch_path": rel(ctx.root, patch_path), "entry_count": len(entries), "unsafe_count": len(unsafe), "unsafe_entries": unsafe[:50], "entries": entries[:200], "truncated": len(entries) > 200}

def apply_changed_files_zip(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("apply_changed_files_zip requires write mode", "write_disabled")
    patch_path = safe_path(ctx, str(args.get("patch_path", "")))
    applied: List[Dict[str, Any]] = []
    backups: List[str] = []
    with zipfile.ZipFile(patch_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            member = norm_rel(info.filename)
            if not (is_under_safe_root(member) or member in {"DELETE_FILES.txt", "aiBridge.bat", "aiBridgeServer.bat"}):
                raise BridgeError("patch contains unsafe path", "unsafe_patch", {"path": member})
            dest = (ctx.root / member).resolve()
            dest.relative_to(ctx.root.resolve())
            backup = backup_file(ctx, dest)
            if backup:
                backups.append(rel(ctx.root, backup))
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            applied.append({"path": member, "size_bytes": info.file_size})
    return {"ok": True, "patch_path": rel(ctx.root, patch_path), "applied": applied, "backups": backups[:200]}
