from __future__ import annotations

import shutil
from pathlib import Path

from .common import CommandResult, ProofLog, run_cmd


def _empty_failed_result(command: list[str], cwd: Path, reason: str) -> CommandResult:
    return CommandResult(
        command=command,
        cwd=str(cwd),
        exit_code=1,
        duration_ms=0,
        stdout_tail="",
        stderr_tail=reason,
    )


def _copy_snapshot(source_root: Path, workspace_repo: Path, proof: ProofLog, *, reason: str) -> CommandResult:
    command = ["snapshot-copy", str(source_root), str(workspace_repo)]
    try:
        if workspace_repo.exists():
            shutil.rmtree(workspace_repo.parent, ignore_errors=True)
        workspace_repo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source_root,
            workspace_repo,
            ignore=shutil.ignore_patterns(".git", ".noesis", "__pycache__", "*.pyc", "*.pyo"),
        )
        result = CommandResult(command=command, cwd=str(source_root), exit_code=0, duration_ms=0, stdout_tail=reason, stderr_tail="")
    except Exception as exc:  # noqa: BLE001 - report exact offline snapshot failure.
        result = _empty_failed_result(command, source_root, f"snapshot copy failed: {exc}")
    proof.emit(
        "WORKSPACE_CREATE",
        path=workspace_repo.as_posix(),
        source="snapshot",
        strategy="filesystem-snapshot",
        status="ok" if result.ok else "failed",
        duration_ms=result.duration_ms,
        reason=reason,
    )
    return result


def create_worktree(source_root: Path, workspace_repo: Path, proof: ProofLog) -> CommandResult:
    """Create an isolated testDevRepo working copy.

    Prefer a local shared clone when a Git repository is available. Offline zip
    builds do not carry `.git`, so they fall back to a clean filesystem snapshot.
    This keeps the verifier usable for patch artifacts without reintroducing
    unbounded `git worktree` registry growth.
    """
    if not (source_root / ".git").exists():
        return _copy_snapshot(source_root, workspace_repo, proof, reason="source has no .git; offline snapshot mode")

    if workspace_repo.exists():
        shutil.rmtree(workspace_repo.parent, ignore_errors=True)
    workspace_repo.parent.mkdir(parents=True, exist_ok=True)

    clone_cmd = [
        "git",
        "clone",
        "--shared",
        "--quiet",
        "--no-tags",
        str(source_root),
        str(workspace_repo),
    ]
    try:
        result = run_cmd(clone_cmd, cwd=source_root, timeout=60)
    except Exception as exc:
        result = _empty_failed_result(clone_cmd, source_root, f"git clone failed: {exc}")
    if not result.ok:
        return _copy_snapshot(source_root, workspace_repo, proof, reason="git clone failed; fallback snapshot mode")
    proof.emit(
        "WORKSPACE_CREATE",
        path=workspace_repo.as_posix(),
        source="HEAD",
        strategy="git-clone-shared",
        status="ok",
        duration_ms=result.duration_ms,
    )
    return result
