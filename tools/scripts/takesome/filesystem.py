from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .paths import rel, suite_path


@dataclass(frozen=True)
class RemoveResult:
    status: str
    path: Path
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"deleted", "missing", "quarantined"}


def _chmod_writable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    except OSError:
        pass


def _clear_windows_attributes(path: Path) -> None:
    if os.name != "nt":
        return
    # Git object stores and copied legacy tools often carry readonly/hidden/system
    # attributes. Python's shutil.rmtree can trip over those on Windows, so clear
    # them before the rmtree retry path.
    candidates = [str(path)]
    if path.is_dir():
        candidates.append(str(path / "*"))
    for candidate in candidates:
        try:
            subprocess.run(
                ["attrib", "-R", "-H", "-S", candidate, "/S", "/D"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            pass


def _prepare_tree_for_delete(path: Path) -> None:
    _clear_windows_attributes(path)
    if path.is_dir() and not path.is_symlink():
        for current_root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                _chmod_writable(Path(current_root) / name)
            for name in dirs:
                _chmod_writable(Path(current_root) / name)
    _chmod_writable(path)


def _rmtree(path: Path) -> None:
    def onerror(func, failed_path, _exc_info):
        failed = Path(failed_path)
        _clear_windows_attributes(failed)
        _chmod_writable(failed)
        func(failed_path)

    def onexc(func, failed_path, _exc):  # Python 3.12+
        failed = Path(failed_path)
        _clear_windows_attributes(failed)
        _chmod_writable(failed)
        func(failed_path)

    _prepare_tree_for_delete(path)
    try:
        shutil.rmtree(path, onexc=onexc)  # type: ignore[call-arg]
    except TypeError:
        shutil.rmtree(path, onerror=onerror)  # Python <= 3.11


def _unlink(path: Path) -> None:
    _clear_windows_attributes(path)
    _chmod_writable(path)
    path.unlink()


def _trash_path(root: Path, path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_rel = rel(root, path).replace("\\", "/").replace("/", "__").replace(":", "_")
    trash_root = suite_path(root, "trash")
    trash_root.mkdir(parents=True, exist_ok=True)
    candidate = trash_root / f"{safe_rel}-{stamp}"
    index = 1
    while candidate.exists():
        candidate = trash_root / f"{safe_rel}-{stamp}-{index}"
        index += 1
    return candidate


def best_effort_remove_path(
    root: Path,
    path: Path,
    *,
    quarantine_on_failure: bool = False,
    retries: int = 2,
) -> RemoveResult:
    """Remove a repo-local path without making cleanup/build workflows brittle.

    The function aggressively handles Windows readonly/hidden/system attributes and
    read-only Git object stores. When `quarantine_on_failure` is enabled and final
    deletion still fails, it tries to move the path into `.takesome/trash` so the
    live legacy/build path is no longer visible to scanners.
    """
    if not path.exists() and not path.is_symlink():
        return RemoveResult("missing", path)

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if path.is_dir() and not path.is_symlink():
                _rmtree(path)
            else:
                _unlink(path)
            return RemoveResult("deleted", path)
        except OSError as exc:
            last_error = exc
            _prepare_tree_for_delete(path)
            if attempt < retries:
                time.sleep(0.05 * (attempt + 1))
                continue
            break

    if quarantine_on_failure and path.exists():
        try:
            trash = _trash_path(root, path)
            _prepare_tree_for_delete(path)
            path.rename(trash)
            # Try to remove the quarantined copy too, but do not fail if it remains.
            try:
                if trash.is_dir() and not trash.is_symlink():
                    _rmtree(trash)
                else:
                    _unlink(trash)
                return RemoveResult("deleted", path, f"quarantined then deleted {rel(root, trash)}")
            except OSError as exc:
                return RemoveResult("quarantined", path, f"moved to {rel(root, trash)}; delete later: {exc}")
        except OSError as exc:
            last_error = exc

    return RemoveResult("failed", path, str(last_error) if last_error else "unknown remove error")
