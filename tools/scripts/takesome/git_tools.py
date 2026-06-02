from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .constants import ROOT_EXCLUDED_DIRS
from .logs import TeeLog, quote_for_log
from .paths import rel


@dataclass(frozen=True)
class GitCommandResult:
    code: int
    stdout: str
    stderr: str


def _run_capture(args: Sequence[str], *, cwd: Path, timeout: float = 8.0) -> GitCommandResult:
    try:
        completed = subprocess.run(
            list(args),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=None,
            check=False,
        )
    except FileNotFoundError:
        return GitCommandResult(127, "", f"command not found: {args[0]}")
    except subprocess.TimeoutExpired as exc:
        return GitCommandResult(130, exc.stdout or "", exc.stderr or f"command wait interrupted: {' '.join(args)}")
    return GitCommandResult(completed.returncode, completed.stdout.strip(), completed.stderr.strip())


def git_available(root: Path) -> bool:
    return _run_capture(["git", "--version"], cwd=root, timeout=5.0).code == 0


def _looks_like_git_dir(path: Path) -> bool:
    marker = path / ".git"
    return marker.is_dir() or marker.is_file()


def _git_list_lines(root: Path, directory: Path, args: Sequence[str], *, limit: int = 20) -> tuple[int, list[str]]:
    result = _run_capture(["git", "-C", str(directory), *args], cwd=root)
    if result.code != 0:
        return 0, []
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return len(lines), lines[: max(0, limit)]


def git_ignored_untracked_files(root: Path, directory: Path, *, limit: int = 20) -> tuple[int, list[str]]:
    """Return untracked files ignored by .gitignore/info/excludes/global excludes."""

    return _git_list_lines(root, directory, ["ls-files", "--others", "--ignored", "--exclude-standard"], limit=limit)


def git_tracked_ignored_files(root: Path, directory: Path, *, limit: int = 20) -> tuple[int, list[str]]:
    """Return tracked files that currently match ignore rules.

    Git still tracks already-versioned files even if .gitignore later matches
    them. Reporting this makes that edge case visible instead of pretending that
    .gitignore can untrack committed artifacts by itself.
    """

    return _git_list_lines(root, directory, ["ls-files", "--cached", "--ignored", "--exclude-standard"], limit=limit)


def git_repo_info(root: Path, directory: Path) -> dict[str, Any]:
    """Return stable git facts for a directory without assuming it is a repo.

    The result distinguishes three useful states:
      - is_git_repo: directory is the top-level worktree root;
      - is_inside_work_tree: directory is somewhere inside a worktree;
      - marker_present: the directory directly contains a .git dir/file.
    """
    directory = directory.resolve()
    marker_present = _looks_like_git_dir(directory)
    base: dict[str, Any] = {
        "is_git_repo": False,
        "is_inside_work_tree": False,
        "marker_present": marker_present,
        "repo_root": "",
        "relative_repo_root": "",
        "branch": "",
        "upstream": "",
        "remote_origin_url": "",
        "head": "",
        "status": "not_repo",
        "dirty_files": 0,
        "staged_files": 0,
        "unstaged_files": 0,
        "untracked_files": 0,
        "ignored_untracked_files": 0,
        "tracked_ignored_files": 0,
        "ignored_untracked_sample": [],
        "tracked_ignored_sample": [],
        "ahead": 0,
        "behind": 0,
        "git_error": "",
    }
    if not directory.exists() or not directory.is_dir():
        base["status"] = "missing"
        return base
    if not git_available(root):
        base["status"] = "git_unavailable_marker_present" if marker_present else "git_unavailable"
        base["git_error"] = "git executable is not available"
        return base

    inside = _run_capture(["git", "-C", str(directory), "rev-parse", "--is-inside-work-tree"], cwd=root)
    if inside.code != 0 or inside.stdout.lower() != "true":
        base["status"] = "git_marker_only" if marker_present else "not_repo"
        base["git_error"] = inside.stderr
        return base

    top = _run_capture(["git", "-C", str(directory), "rev-parse", "--show-toplevel"], cwd=root)
    repo_root = Path(top.stdout).resolve() if top.code == 0 and top.stdout else directory
    base["is_inside_work_tree"] = True
    base["repo_root"] = str(repo_root)
    base["relative_repo_root"] = rel(root, repo_root)
    base["is_git_repo"] = repo_root == directory
    base["status"] = "repo" if base["is_git_repo"] else "inside_repo"

    branch = _run_capture(["git", "-C", str(directory), "branch", "--show-current"], cwd=root)
    if branch.code == 0:
        base["branch"] = branch.stdout
    head = _run_capture(["git", "-C", str(directory), "rev-parse", "--short", "HEAD"], cwd=root)
    if head.code == 0:
        base["head"] = head.stdout
    upstream = _run_capture(["git", "-C", str(directory), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=root)
    if upstream.code == 0:
        base["upstream"] = upstream.stdout
    origin = _run_capture(["git", "-C", str(directory), "config", "--get", "remote.origin.url"], cwd=root)
    if origin.code == 0:
        base["remote_origin_url"] = origin.stdout

    status = _run_capture(["git", "-C", str(directory), "status", "--porcelain=v1", "--branch"], cwd=root)
    if status.code == 0:
        dirty = staged = unstaged = untracked = 0
        for line in status.stdout.splitlines():
            if line.startswith("## "):
                if "ahead " in line:
                    try:
                        base["ahead"] = int(line.split("ahead ", 1)[1].split("]", 1)[0].split(",", 1)[0].strip())
                    except ValueError:
                        pass
                if "behind " in line:
                    try:
                        base["behind"] = int(line.split("behind ", 1)[1].split("]", 1)[0].split(",", 1)[0].strip())
                    except ValueError:
                        pass
                continue
            if not line:
                continue
            dirty += 1
            xy = line[:2]
            if xy == "??":
                untracked += 1
            else:
                if xy[0] != " ":
                    staged += 1
                if xy[1] != " ":
                    unstaged += 1
        base["dirty_files"] = dirty
        base["staged_files"] = staged
        base["unstaged_files"] = unstaged
        base["untracked_files"] = untracked
    elif status.stderr:
        base["git_error"] = status.stderr

    ignored_count, ignored_sample = git_ignored_untracked_files(root, directory)
    tracked_ignored_count, tracked_ignored_sample = git_tracked_ignored_files(root, directory)
    base["ignored_untracked_files"] = ignored_count
    base["ignored_untracked_sample"] = ignored_sample
    base["tracked_ignored_files"] = tracked_ignored_count
    base["tracked_ignored_sample"] = tracked_ignored_sample
    return base


def _is_excluded_dir(path: Path) -> bool:
    name = path.name
    if name in ROOT_EXCLUDED_DIRS:
        return True
    if name in {".git", ".hg", ".svn", "target", "node_modules", "__pycache__"}:
        return True
    return False


def _walk_candidate_dirs(root: Path, *, max_depth: int) -> Iterable[Path]:
    root = root.resolve()
    yield root
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        if depth >= max_depth:
            continue
        try:
            children = sorted((p for p in directory.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
        except OSError:
            continue
        for child in reversed(children):
            if _is_excluded_dir(child):
                continue
            stack.append((child, depth + 1))
            if _looks_like_git_dir(child):
                yield child


def discover_git_repositories(root: Path, *, max_depth: int = 4, paths: Sequence[Path] | None = None) -> list[Path]:
    """Discover distinct Git worktree roots under root.

    When git metadata is absent, this returns an empty list instead of guessing.
    """
    candidates = [p.resolve() for p in paths] if paths else list(_walk_candidate_dirs(root, max_depth=max_depth))
    seen: set[str] = set()
    repos: list[Path] = []
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_dir():
            continue
        info = git_repo_info(root, candidate)
        if not info.get("is_inside_work_tree"):
            continue
        repo_root = Path(str(info.get("repo_root") or candidate)).resolve()
        try:
            repo_root.relative_to(root.resolve())
        except ValueError:
            continue
        key = str(repo_root).lower()
        if key in seen:
            continue
        seen.add(key)
        repos.append(repo_root)
    repos.sort(key=lambda p: rel(root, p).lower())
    return repos


def run_git_stream(args: Sequence[str], *, cwd: Path, log: TeeLog, dry_run: bool = False) -> int:
    display = " ".join(quote_for_log(a) for a in args)
    if dry_run:
        log.emit(f"[DRY] {display}")
        return 0
    log.emit(f"[CMD] {display}")
    try:
        process = subprocess.Popen(
            list(args),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        log.emit(f"[ERROR] Command not found: {args[0]}")
        return 127
    assert process.stdout is not None
    for line in process.stdout:
        log.write_raw(line)
    return process.wait()


