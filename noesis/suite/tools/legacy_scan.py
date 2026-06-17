from __future__ import annotations

from pathlib import Path

from ..logs import TeeLog
from ..paths import rel
from .constants import LEGACY_TOOL_IDENTITIES, SOURCE_SKIP_DIRS, TEXT_EXTS

_ALLOWED_LEGACY_SOURCE_FILES = {
    "delete_files.txt",
    "noesis/suite/tools/constants.py",
    "noesis/suite/tools/legacy_scan.py",
    "noesis/suite/tools/cache.py",
}


def path_is_skipped(path: Path) -> bool:
    return bool(set(path.parts) & SOURCE_SKIP_DIRS)


def _watched_files(repo_root: Path) -> list[Path]:
    watch_roots = [repo_root / "tools" / "scripts", repo_root]
    watched: list[Path] = []
    for base in watch_roots:
        if not base.exists():
            continue
        if base == repo_root:
            candidates = [p for p in base.iterdir() if p.is_file() and p.suffix.lower() in {".bat", ".cmd", ".ps1"}]
        else:
            candidates = [p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in TEXT_EXTS and not path_is_skipped(p)]
        watched.extend(candidates)
    return sorted(set(watched), key=lambda p: p.as_posix().lower())


def validate_source_for_legacy_tool_identities(repo_root: Path, *, log: TeeLog) -> int:
    code = 0
    for path in _watched_files(repo_root):
        low_rel = rel(repo_root, path).lower().replace("\\", "/")
        if low_rel in _ALLOWED_LEGACY_SOURCE_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for identity in LEGACY_TOOL_IDENTITIES:
            # `nepak` is a legacy tool identity, but `.nepak` is the current
            # canonical VFS package extension.  The path-based scan above still
            # rejects resurrected `tools/NePak` / `tools/nepak` directories; the
            # source-text scan must not reject safety lists or package policies
            # that mention the valid `.nepak` extension.
            haystack = text.replace(".nepak", "") if identity == "nepak" else text
            if identity in haystack:
                log.emit(f"[ERROR] Legacy tool identity `{identity}` appears in live script/launcher: {rel(repo_root, path)}")
                code = 1
    if code == 0:
        log.emit("[OK] Legacy tool identities are absent from live script/launcher surface.")
    return code
