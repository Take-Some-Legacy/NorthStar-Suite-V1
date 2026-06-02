from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .contracts import (
    BridgeContext,
    BridgeError,
    DENY_PARTS,
    MAX_READ_BYTES_DEFAULT,
    MAX_TOOL_OUTPUT_BYTES,
    SAFE_ROOTS,
    SAFE_TEXT_EXTENSIONS,
)

def slug(value: str, default: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip("-._")
    return cleaned[:80] or default

def norm_rel(path: str) -> str:
    raw = str(path).replace("\\", "/").strip().strip('"')
    if not raw:
        raise BridgeError("path is empty", "invalid_path")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise BridgeError("absolute paths are not accepted", "invalid_path", {"path": path})
    parts: List[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise BridgeError("parent traversal is not accepted", "invalid_path", {"path": path})
        parts.append(part)
    if not parts:
        raise BridgeError("path resolves to repository root", "invalid_path", {"path": path})
    return "/".join(parts)

def is_under_safe_root(rel: str) -> bool:
    """Return whether a repo-relative path is available to the bridge.

    The North Star Suite is an operator for this project, so it needs broad
    project-root freedom: edit source, configs, docs, tools, assets, logs,
    generated dataset state and cleanup artifacts. The hard boundary is the
    repository root plus a tiny deny-list for VCS/trust/secrets.

    SAFE_ROOTS remains exported for diagnostics/backward compatibility, but it
    is no longer a narrow write jail for the public MCP surface.
    """
    rel_l = rel.lower().strip("/")
    for deny in DENY_PARTS:
        d = deny.lower().strip("/")
        if rel_l == d or rel_l.startswith(d + "/") or ("/" + d + "/") in ("/" + rel_l + "/"):
            return False
    return True

def safe_path(ctx: BridgeContext, rel_path: str, *, must_exist: bool = True) -> Path:
    rel = norm_rel(rel_path)
    if not is_under_safe_root(rel):
        raise BridgeError("path is outside AI bridge safe roots", "unsafe_path", {"path": rel, "safe_roots": list(SAFE_ROOTS)})
    path = (ctx.root / rel).resolve()
    try:
        path.relative_to(ctx.root.resolve())
    except ValueError:
        raise BridgeError("path escapes repository root", "unsafe_path", {"path": rel})
    if must_exist and not path.exists():
        raise BridgeError("path does not exist", "not_found", {"path": rel})
    return path

def rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)

def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in SAFE_TEXT_EXTENSIONS or path.name in {"Cargo.lock", "LICENSE", "README", "Makefile"}

def read_text_file(path: Path, max_bytes: int = MAX_READ_BYTES_DEFAULT) -> Tuple[str, bool, int]:
    if not is_text_file(path):
        raise BridgeError("file extension is not text-whitelisted", "not_text", {"path": str(path)})
    size = path.stat().st_size
    data = path.read_bytes()[: max(1, max_bytes)]
    return data.decode("utf-8", errors="replace"), size > len(data), size

def load_config(ctx: BridgeContext) -> Dict[str, Any]:
    try:
        return json.loads(ctx.bridge_config.read_text(encoding="utf-8")) if ctx.bridge_config.exists() else {}
    except Exception as exc:
        return {"_config_error": str(exc)}

def backup_file(ctx: BridgeContext, path: Path) -> Optional[Path]:
    if not path.exists() or not path.is_file():
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ctx.backup_dir / stamp / rel(ctx.root, path)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    return backup

def truncate(text: str, limit: int = MAX_TOOL_OUTPUT_BYTES) -> Tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text, False
    return raw[:limit].decode("utf-8", errors="replace"), True


def truncate_tail(text: str, limit: int = MAX_TOOL_OUTPUT_BYTES) -> Tuple[str, bool, int]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text, False, len(raw)
    marker = b"...[northstar-output-truncated-tail]\n"
    keep = max(1, limit - len(marker))
    return (marker + raw[-keep:]).decode("utf-8", errors="replace"), True, len(raw)

def find_root(start: Path) -> Path:
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / "docs" / "SUITE.md").exists() or (candidate / "NewEngine" / "neocore2" / "Cargo.toml").exists():
            return candidate
    return start

def latest_existing(root: Path, patterns: Iterable[str], limit: int) -> List[Dict[str, Any]]:
    items: List[Path] = []
    for pattern in patterns:
        items.extend(root.glob(pattern))
    out: List[Dict[str, Any]] = []
    for path in sorted(set(items), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:limit]:
        if path.exists():
            out.append({"path": rel(root, path), "size_bytes": path.stat().st_size, "modified_utc": int(path.stat().st_mtime)})
    return out
