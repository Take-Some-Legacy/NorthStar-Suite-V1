from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from ...paths import utc_iso
from ...status_cache import write_status_snapshot


@dataclass(frozen=True)
class GitHealthSnapshot:
    available: bool
    dirty: bool
    changed_files: int
    branch: str
    error: str = ""

    @property
    def health(self) -> str:
        if not self.available:
            return "warn"
        return "warn" if self.dirty else "ok"

    def line(self) -> str:
        if not self.available:
            return self.error or "not a git workspace"
        state = "dirty" if self.dirty else "clean"
        suffix = f" · {self.branch}" if self.branch else ""
        return f"{state} · {self.changed_files} changed files{suffix}"


def _run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=None)


def _cache_git_health(root: Path, snapshot: GitHealthSnapshot) -> GitHealthSnapshot:
    write_status_snapshot(
        root,
        "git-health",
        {
            "schema": "takesome.gitHealth.v1",
            "generated_utc": utc_iso(),
            "available": snapshot.available,
            "dirty": snapshot.dirty,
            "changed_files": snapshot.changed_files,
            "branch": snapshot.branch,
            "error": snapshot.error,
        },
        source="suite.status.git_health.collect_git_health",
    )
    return snapshot


def collect_git_health(root: Path) -> GitHealthSnapshot:
    try:
        probe = _run_git(root, ["rev-parse", "--is-inside-work-tree"])
    except Exception as exc:
        return _cache_git_health(root, GitHealthSnapshot(False, False, 0, "", f"git unavailable: {exc}"))
    if probe.returncode != 0 or probe.stdout.strip().lower() != "true":
        return _cache_git_health(root, GitHealthSnapshot(False, False, 0, "", "not a git workspace"))
    status = _run_git(root, ["status", "--porcelain"])
    if status.returncode != 0:
        return _cache_git_health(root, GitHealthSnapshot(False, False, 0, "", status.stderr.strip() or "git status failed"))
    branch = ""
    branch_result = _run_git(root, ["branch", "--show-current"])
    if branch_result.returncode == 0:
        branch = branch_result.stdout.strip()
    changed = [line for line in status.stdout.splitlines() if line.strip()]
    return _cache_git_health(root, GitHealthSnapshot(True, bool(changed), len(changed), branch))
