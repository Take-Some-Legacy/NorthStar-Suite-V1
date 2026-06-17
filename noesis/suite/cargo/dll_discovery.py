from __future__ import annotations

import sys
from pathlib import Path

from ..constants import DLL_EXT, WIN
from ..logs import TeeLog
from ..paths import rel


def cleanup_old_versions(directory: Path, stem: str, keep: str, log: TeeLog, *, library_ext: str | None = None) -> None:
    if not directory.exists():
        return
    ext = library_ext or DLL_EXT
    for path in sorted(directory.glob(f"{stem}-*{ext}")):
        if path.name.lower() == keep.lower():
            continue
        try:
            log.emit(f"[CLEAN] deleting old {stem} DLL: {path.name}")
            path.unlink()
        except OSError as exc:
            log.emit(f"[WARN] Failed to delete {path}: {exc}")


def dynamic_library_names_for_stem(stem: str, *, library_ext: str | None = None) -> list[str]:
    ext = library_ext or DLL_EXT
    if ext == ".dll":
        return [f"{stem}.dll"]
    if ext == ".dylib":
        return [f"lib{stem}.dylib", f"{stem}.dylib"]
    if ext == ".so":
        return [f"lib{stem}.so", f"{stem}.so"]
    return [f"{stem}{ext}"]


def unique_in_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower() if WIN else item
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def candidate_built_dlls(
    target_dir: Path,
    profile: str,
    stems: list[str],
    exact_names: list[str] | None = None,
    extra_dirs: list[Path] | None = None,
    library_ext: str | None = None,
) -> list[Path]:
    base_dirs = [target_dir / profile, target_dir / profile / "deps", *(extra_dirs or [])]
    dirs: list[Path] = []
    seen_dirs: set[str] = set()
    for directory in base_dirs:
        key = str(directory.resolve()) if directory.exists() else str(directory)
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        dirs.append(directory)

    ext = library_ext or DLL_EXT
    names = unique_in_order([*(exact_names or []), *(name for stem in stems for name in dynamic_library_names_for_stem(stem, library_ext=ext))])
    found: list[Path] = []

    for directory in dirs:
        for name in names:
            path = directory / name
            if path.exists() and path.is_file():
                found.append(path)
    if found:
        return sorted(set(found), key=lambda path: path.stat().st_mtime, reverse=True)

    recursive_roots = [target_dir, *(extra_dirs or [])]
    seen_roots: set[str] = set()
    for root in recursive_roots:
        if not root.exists() or not root.is_dir():
            continue
        key = str(root.resolve())
        if key in seen_roots:
            continue
        seen_roots.add(key)
        for name in names:
            found.extend(path for path in root.rglob(name) if path.is_file())
    if found:
        return sorted(set(found), key=lambda path: path.stat().st_mtime, reverse=True)

    glob_stems = unique_in_order([*stems, *(Path(name).stem for name in (exact_names or []))])
    glob_patterns = [f"*{stem}*{ext}" for stem in glob_stems]
    for root in recursive_roots:
        if not root.exists() or not root.is_dir():
            continue
        for pattern in glob_patterns:
            found.extend(path for path in root.rglob(pattern) if path.is_file())
    return sorted(set(found), key=lambda path: path.stat().st_mtime, reverse=True)
