from __future__ import annotations

from pathlib import Path
from typing import Any

from .runs_io import artifact_links, read_json, read_text


def run_payload(root: Path, run_id: str) -> dict[str, Any] | None:
    run_dir = root / ".noesis" / "runs" / run_id
    if not run_dir.exists():
        return None
    return {
        "runId": run_id,
        "runDir": str(run_dir),
        "readiness": read_json(run_dir / "merge-readiness.json"),
        "report": read_json(run_dir / "validation-report.json"),
        "fullRepoReport": read_json(run_dir / "full-repo-report.json"),
        "proofLog": read_text(run_dir / "proof-of-work.log"),
        "artifacts": artifact_links(run_dir, run_id),
    }


def patch_candidates(run_dir: Path) -> list[Path]:
    names = ["repo.patch", "changes.patch", "diff.patch"]
    found: list[Path] = []
    for name in names:
        candidate = run_dir / name
        if candidate.is_file():
            found.append(candidate)
    for candidate in sorted(run_dir.glob("*.patch")):
        if candidate not in found:
            found.append(candidate)
    return found


def patch_stats(patch_text: str) -> dict[str, Any]:
    files: set[str] = set()
    additions = 0
    deletions = 0
    hunks = 0
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                name = parts[3][2:] if parts[3].startswith("b/") else parts[3]
                files.add(name)
        elif line.startswith("@@"):
            hunks += 1
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return {"files": sorted(files), "fileCount": len(files), "additions": additions, "deletions": deletions, "hunks": hunks}


def patch_commands(run_id: str) -> dict[str, str]:
    return {
        "inspect": f"python -m noesis runs patch {run_id} --json",
        "show": f"python -m noesis runs patch {run_id} --show",
        "dryRun": f"python -m noesis runs patch {run_id} --check",
        "apply": f"python -m noesis runs patch {run_id} --apply",
    }


def patch_payload(root: Path, run_id: str, *, limit: int = 120000) -> dict[str, Any]:
    run_dir = root / ".noesis" / "runs" / run_id
    if not run_dir.exists():
        return {"ok": False, "error": "run_not_found", "runId": run_id}
    candidates = patch_candidates(run_dir)
    if not candidates:
        return {"ok": False, "error": "patch_not_found", "runId": run_id, "runDir": str(run_dir), "commands": patch_commands(run_id)}
    path = candidates[0]
    preview = read_text(path, limit=limit)
    return {
        "ok": True,
        "schema": "noesis.dashboard.patch.v1",
        "runId": run_id,
        "runDir": str(run_dir),
        "patchName": path.name,
        "patchPath": str(path),
        "stats": patch_stats(preview),
        "preview": preview,
        "commands": patch_commands(run_id),
    }
