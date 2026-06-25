from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import rel

REPOSITORY_INDEX_SCHEMA = "takesome.repository_operator_index.v1"
REPOSITORY_INDEX_FILENAME = "indexFile.v1.json"
DEFAULT_WINDOWS_REPOS_ROOT = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "Repos"


@dataclass(frozen=True)
class RepositoryIndex:
    """Resolved repository-local operator contract.

    Layout default:

    repos_root/
      repoDir/
        indexFile.v1.json
        dataset/
        workspace/
    """

    repo_dir: Path
    index_file: Path
    payload: dict[str, Any]
    workdir: Path
    dataset_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    tmp_dir: Path
    execution_cwd: Path
    repos_root: Path

    def rel(self, path: Path) -> str:
        return rel(self.repo_dir, path)

    def command(self, name: str) -> list[str]:
        commands = self.payload.get("commands") if isinstance(self.payload.get("commands"), dict) else {}
        raw = commands.get(name) if isinstance(commands, dict) else None
        return resolve_command(raw)

    def as_record(self) -> dict[str, Any]:
        return {
            "schema": "takesome.repository_index.resolved.v1",
            "repo_dir": str(self.repo_dir),
            "index_file": str(self.index_file),
            "repos_root": str(self.repos_root),
            "paths": {
                "workdir": self.rel(self.workdir),
                "dataset_dir": self.rel(self.dataset_dir),
                "artifacts_dir": self.rel(self.artifacts_dir),
                "logs_dir": self.rel(self.logs_dir),
                "tmp_dir": self.rel(self.tmp_dir),
                "execution_cwd": self.rel(self.execution_cwd),
            },
            "repository": self.payload.get("repository", {}),
            "bootstrap": self.payload.get("bootstrap", {}),
            "operator": self.payload.get("operator", {}),
        }


def default_repos_root() -> Path:
    """Canonical root for repository-local artifacts and working repos."""
    return DEFAULT_WINDOWS_REPOS_ROOT.resolve()


def _resolve_child(repo_dir: Path, value: Any, default: str) -> Path:
    raw = str(value or default).strip() or default
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    return (repo_dir / path).resolve()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, str(exc)
    return (data if isinstance(data, dict) else {}), ""


def find_repository_index(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        index = candidate / REPOSITORY_INDEX_FILENAME
        if index.exists() and index.is_file():
            return index
    return None


def load_repository_index(repo_dir: Path) -> tuple[RepositoryIndex | None, list[str]]:
    repo_dir = repo_dir.resolve()
    index_file = repo_dir / REPOSITORY_INDEX_FILENAME
    if not index_file.exists():
        found = find_repository_index(repo_dir)
        if found is None:
            return None, [f"repository index not found from {repo_dir}"]
        index_file = found
        repo_dir = found.parent.resolve()

    payload, error = _read_json(index_file)
    diagnostics: list[str] = []
    if error:
        return None, [f"cannot read {index_file}: {error}"]
    if payload.get("schema") != REPOSITORY_INDEX_SCHEMA:
        diagnostics.append(f"unexpected schema: {payload.get('schema')!r}")

    paths = payload.get("paths") if isinstance(payload.get("paths"), dict) else {}
    repos_root = _resolve_repos_root(repo_dir, payload)
    workdir = _resolve_child(repo_dir, paths.get("workdir"), "workspace")
    dataset_dir = _resolve_child(repo_dir, paths.get("dataset_dir"), "dataset")
    artifacts_dir = _resolve_child(repo_dir, paths.get("artifacts_dir"), "workspace/artifacts")
    logs_dir = _resolve_child(repo_dir, paths.get("logs_dir"), "workspace/logs")
    tmp_dir = _resolve_child(repo_dir, paths.get("tmp_dir"), "workspace/tmp")

    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    execution_cwd = _resolve_child(repo_dir, execution.get("cwd"), str(paths.get("workdir") or "workspace"))

    return RepositoryIndex(
        repo_dir=repo_dir,
        index_file=index_file.resolve(),
        payload=payload,
        workdir=workdir,
        dataset_dir=dataset_dir,
        artifacts_dir=artifacts_dir,
        logs_dir=logs_dir,
        tmp_dir=tmp_dir,
        execution_cwd=execution_cwd,
        repos_root=repos_root,
    ), diagnostics


def _resolve_repos_root(repo_dir: Path, payload: dict[str, Any]) -> Path:
    """Repository indexes inherit the single configured repositories root."""
    return default_repos_root()


def resolve_command(raw: Any) -> list[str]:
    """Resolve legacy array or platform-specific command map."""

    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    if isinstance(raw, dict):
        if sys.platform.startswith("win"):
            candidate = raw.get("windows") or raw.get("win")
        else:
            candidate = raw.get("posix") or raw.get("unix")
        if candidate is None:
            candidate = raw.get("default")
        if isinstance(candidate, list):
            return [str(item) for item in candidate if str(item)]
    return []


def validate_repository_index(index: RepositoryIndex | None, diagnostics: list[str]) -> dict[str, Any]:
    if index is None:
        return {
            "schema": "takesome.repository_index.validation.v1",
            "ok": False,
            "status": "missing",
            "diagnostics": diagnostics,
        }

    required_paths = {
        "repo_dir": index.repo_dir,
        "index_file": index.index_file,
        "workdir": index.workdir,
        "dataset_dir": index.dataset_dir,
        "artifacts_dir": index.artifacts_dir,
        "logs_dir": index.logs_dir,
        "tmp_dir": index.tmp_dir,
        "execution_cwd": index.execution_cwd,
    }
    path_records = []
    ok = not diagnostics
    for name, path in required_paths.items():
        exists = path.exists()
        if not exists:
            ok = False
            diagnostics.append(f"missing path {name}: {path}")
        path_records.append({"name": name, "path": str(path), "exists": exists})

    repos_root_exists = index.repos_root.exists()
    if not repos_root_exists:
        diagnostics.append(f"repos_root is not accessible: {index.repos_root}")

    return {
        "schema": "takesome.repository_index.validation.v1",
        "ok": ok,
        "status": "ok" if ok else "error",
        "repos_root": str(index.repos_root),
        "repos_root_exists": repos_root_exists,
        "index": index.as_record(),
        "paths": path_records,
        "diagnostics": diagnostics,
    }
