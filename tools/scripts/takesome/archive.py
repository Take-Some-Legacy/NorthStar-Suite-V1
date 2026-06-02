from __future__ import annotations

import argparse
import fnmatch
import time
import zipfile
from pathlib import Path

from .console import console_emit
from .constants import ROOT_EXCLUDED_DIRS, SOURCE_ARCHIVE_EXCLUDED_EXTENSIONS, SOURCE_ARCHIVE_EXCLUDED_FILENAMES
from .migration import apply_delete_list
from .paths import now_stamp
from .progress import progress_configure, progress_update


def should_skip_archive_entry(root: Path, path: Path, output: Path, excluded_dirs: set[str], excluded_exts: set[str], excluded_files: set[str]) -> bool:
    if path.resolve() == output.resolve():
        return True
    parts = set(path.relative_to(root).parts[:-1])
    if parts & excluded_dirs:
        return True
    if path.name in excluded_files:
        return True
    if path.suffix.lower() in excluded_exts:
        return True
    relp = path.relative_to(root).as_posix()
    generated_patterns = [
        "NewEngine/neocore2/logs/*",
        "NewEngine/neocore2/cache/*",
        "NewEngine/neocore2/assets/fonts/*",
        "Plugins/build-state/*",
        ".takesome/build-state/*",
        "*/target/*",
    ]
    return any(fnmatch.fnmatch(relp, pat) for pat in generated_patterns)


def _emit_status(message: str) -> None:
    console_emit(message)


def pack_source(root: Path, ns: argparse.Namespace) -> int:
    apply_delete_list(root)
    started = time.perf_counter()
    output = Path(ns.output).resolve() if ns.output else root / f"{root.name}-source-{now_stamp()}.zip"
    if not output.is_absolute():
        output = (root / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    excluded_dirs = set(ROOT_EXCLUDED_DIRS) | set(ns.exclude_dir or [])
    excluded_exts = set(SOURCE_ARCHIVE_EXCLUDED_EXTENSIONS) | {e if e.startswith('.') else f'.{e}' for e in (ns.exclude_ext or [])}
    excluded_files = set(SOURCE_ARCHIVE_EXCLUDED_FILENAMES) | set(ns.exclude_file or [])

    _emit_status(f"[pack-source] root   : {root}")
    _emit_status(f"[pack-source] output : {output}")
    progress_configure(total=1, current=0, unit="phase", phase="scanning source tree")
    _emit_status("[pack-source] scanning source tree...")

    files: list[Path] = []
    visited = 0
    last_scan_emit = time.perf_counter()
    for path in root.rglob("*"):
        visited += 1
        if visited % 1500 == 0 or (time.perf_counter() - last_scan_emit) >= 2.0:
            _emit_status(f"[pack-source] scanning... visited={visited} selected={len(files)}")
            last_scan_emit = time.perf_counter()
        if not path.is_file():
            continue
        if should_skip_archive_entry(root, path, output, excluded_dirs, excluded_exts, excluded_files):
            continue
        files.append(path)
    files.sort(key=lambda p: p.relative_to(root).as_posix().lower())

    total_bytes = 0
    for path in files:
        try:
            total_bytes += path.stat().st_size
        except OSError:
            pass
    _emit_status(f"[pack-source] files  : {len(files)}")
    _emit_status(f"[pack-source] source : {total_bytes / (1024 * 1024):.2f} MiB before compression")
    _emit_status("[pack-source] writing zip entries...")
    progress_configure(total=max(1, len(files)), current=0, unit="files", phase="writing zip entries")

    fixed_date = (1980, 1, 1, 0, 0, 0)
    written_bytes = 0
    last_write_emit = time.perf_counter()
    last_progress_emit = time.perf_counter()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for index, path in enumerate(files, start=1):
            entry = path.relative_to(root).as_posix()
            zi = zipfile.ZipInfo(entry, fixed_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as fh:
                data = fh.read()
            zf.writestr(zi, data)
            written_bytes += len(data)
            now = time.perf_counter()
            if index == len(files) or index % 25 == 0 or (now - last_progress_emit) >= 0.20:
                progress_update(current=index, total=max(1, len(files)), unit="files", phase=f"packing {entry}")
                last_progress_emit = now
            if ns.verbose:
                _emit_status(f"[pack] {entry}")
            elif index == len(files) or index % 250 == 0 or (time.perf_counter() - last_write_emit) >= 2.0:
                percent = (index / len(files) * 100.0) if files else 100.0
                _emit_status(
                    f"[pack-source] writing... {index}/{len(files)} files ({percent:.1f}%), "
                    f"{written_bytes / (1024 * 1024):.2f}/{total_bytes / (1024 * 1024):.2f} MiB"
                )
                last_write_emit = time.perf_counter()

    elapsed = time.perf_counter() - started
    archive_size = output.stat().st_size if output.exists() else 0
    progress_update(current=max(1, len(files)), total=max(1, len(files)), unit="files", phase="source archive created")
    _emit_status(f"[OK] Source archive created: {output}")
    _emit_status(f"[OK] Archive size: {archive_size / (1024 * 1024):.2f} MiB; elapsed={elapsed:.1f}s")
    return 0
