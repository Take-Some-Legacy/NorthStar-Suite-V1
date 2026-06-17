from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CANONICAL_RUNTIME_CONFIG = Path("config") / "noesis" / "runtime.v1.json"


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "noesis").is_dir() and ((candidate / "suite.bat").exists() or (candidate / "docs").exists()):
            return candidate
        if (candidate / "docs" / "SUITE.md").exists() or (candidate / "NewEngine" / "neocore2" / "Cargo.toml").exists():
            return candidate
    return current


def runtime_config_path(root: Path) -> Path:
    env = os.environ.get("NOESIS_RUNTIME_CONFIG") or os.environ.get("NORTHSTAR_SUITE_WORKSPACE_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return (root / CANONICAL_RUNTIME_CONFIG).resolve()


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    config: Path
    package: Path

    @classmethod
    def resolve(cls, start: Path | None = None) -> "RuntimePaths":
        root = find_repo_root(start)
        return cls(root=root, config=runtime_config_path(root), package=root / "noesis")
