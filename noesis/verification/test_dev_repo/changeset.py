from __future__ import annotations

import shutil
from pathlib import Path

from .common import ProofLog, relpath, run_cmd

EXCLUDED_CHANGE_PREFIXES = (
    ".git/",
    ".noesis/",
    ".takesome/suite/runs/",
    "NewEngine/neocore2/buildInfo/",
    "tools/toolbelt/third_party/",
    "tools/toolbelt/first_party/",
)


def is_excluded_change(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if ".bak_" in normalized or normalized.endswith(".tmp"):
        return True
    return any(normalized.startswith(prefix) for prefix in EXCLUDED_CHANGE_PREFIXES)


def git_status_entries(root: Path) -> list[dict[str, str]]:
    if not (root / ".git").exists():
        return []
    result = run_cmd(["git", "status", "--porcelain=v1"], cwd=root, timeout=120)
    if not result.ok:
        return []
    entries: list[dict[str, str]] = []
    for raw in result.stdout_tail.splitlines():
        if not raw:
            continue
        status = raw[:2]
        path = raw[3:] if len(raw) > 3 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        normalized = path.replace("\\", "/")
        if is_excluded_change(normalized):
            continue
        entries.append({"status": status, "path": normalized})
    return entries


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink()


def copy_path(src: Path, dst: Path) -> None:
    if src.is_dir() and not src.is_symlink():
        remove_path(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def apply_current_changes(source_root: Path, worktree_repo: Path, proof: ProofLog) -> dict[str, object]:
    entries = git_status_entries(source_root)
    applied: list[dict[str, str]] = []
    for entry in entries:
        rel = entry["path"]
        src = source_root / rel
        dst = worktree_repo / rel
        if entry["status"].strip() == "D" or not src.exists():
            remove_path(dst)
            applied.append({**entry, "operation": "delete"})
        else:
            copy_path(src, dst)
            applied.append({**entry, "operation": "copy"})

    # Directory removals are reported by Git as per-file deletions.  After
    # deleting every tracked file, the empty parent directory may still exist in
    # the cloned verification workspace.  Prune forbidden runtime roots that no
    # longer exist in the source tree so boundary checks evaluate the intended
    # post-change tree, not stale empty directories from HEAD.
    for rel in ("tools/scripts", "config/suite"):
        if not (source_root / rel).exists():
            target = worktree_repo / rel
            if target.exists():
                remove_path(target)
                applied.append({"status": "D ", "path": rel, "operation": "delete-tree"})

    proof.emit("APPLY", changeset="current_worktree_copy", status="ok", changed_files=len(applied))
    return {
        "mode": "current_worktree_copy",
        "changedFiles": len(applied),
        "applied": applied,
        "sourceRoot": str(source_root),
        "workspace": str(worktree_repo),
    }
