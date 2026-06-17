from __future__ import annotations

from pathlib import Path
from typing import Any

from .changeset import git_status_entries, is_excluded_change
from .common import CommandResult, Phase, ProofLog, run_cmd

TEXT_EXTENSIONS = {
    ".bat", ".cmd", ".css", ".html", ".js", ".json", ".jsx",
    ".md", ".mjs", ".py", ".rs", ".toml", ".ts", ".tsx",
    ".txt", ".vue", ".xml", ".yaml", ".yml",
}


def scan_conflict_markers(repo: Path, limit: int = 50) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in repo.rglob("*"):
        if len(findings) >= limit:
            break
        if not path.is_file():
            continue
        rel = path.relative_to(repo).as_posix()
        if rel.startswith(".git/") or rel.startswith(".noesis/"):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            is_conflict_marker = line.startswith("<<<<<<< ") or line.startswith(">>>>>>> ") or stripped == "======="
            if is_conflict_marker:
                findings.append({"path": rel, "line": idx, "text": line[:160]})
                break
    return findings


def filtered_diff_check(repo: Path) -> CommandResult:
    entries = git_status_entries(repo)
    paths = [entry["path"] for entry in entries if not is_excluded_change(entry["path"])]
    paths = [
        path
        for path in paths
        if (repo / path).exists() or "D" in next((entry["status"] for entry in entries if entry["path"] == path), "")
    ]
    if not paths:
        return CommandResult(command=["git", "diff", "--check", "--", "<filtered-empty>"], cwd=str(repo), exit_code=0, duration_ms=0, stdout_tail="", stderr_tail="")
    return run_cmd(["git", "diff", "--check", "--", *paths], cwd=repo, timeout=60)


def audit_structure(repo: Path, proof: ProofLog) -> Phase:
    proof.emit("AUDIT", kind="structure", status="running")
    if (repo / ".git").exists():
        commands = [
            run_cmd(["git", "status", "--short"], cwd=repo, timeout=60),
            filtered_diff_check(repo),
        ]
    else:
        commands = [
            CommandResult(command=["git", "status", "--short"], cwd=str(repo), exit_code=0, duration_ms=0, stdout_tail="offline snapshot: no .git", stderr_tail=""),
            CommandResult(command=["git", "diff", "--check"], cwd=str(repo), exit_code=0, duration_ms=0, stdout_tail="offline snapshot: no .git", stderr_tail=""),
        ]
    conflicts = scan_conflict_markers(repo)
    blocking: list[str] = []
    if not commands[0].ok:
        blocking.append("git status failed")
    if not commands[1].ok:
        blocking.append("git diff --check failed")
    if conflicts:
        blocking.append("conflict markers found")
    status = "ok" if not blocking else "failed"
    proof.emit("AUDIT", kind="structure", status=status, issues=len(blocking), conflicts=len(conflicts))
    return Phase(
        name="audit",
        status=status,
        reason="; ".join(blocking),
        data={"commands": [c.to_json() for c in commands], "conflicts": conflicts, "blockingIssues": blocking},
    )
