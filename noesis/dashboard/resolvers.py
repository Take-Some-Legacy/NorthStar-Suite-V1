from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DashboardRoots:
    suite_root: Path
    workspace_root: Path
    state_root: Path
    dataset_root: Path
    tools_root: Path
    config_root: Path
    runtime_config: Path


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def runtime_config_path(root: Path) -> Path:
    return root / "config" / "noesis" / "runtime.v1.json"


def load_runtime_config(root: Path) -> dict[str, Any]:
    return read_json(runtime_config_path(root))


def resolve_repo_path(root: Path, value: Any, *, fallback: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return fallback
    candidate = Path(text).expanduser()
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


def dashboard_roots(root: Path) -> DashboardRoots:
    cfg = load_runtime_config(root)
    workspace_cfg = cfg.get("workspace") if isinstance(cfg.get("workspace"), dict) else {}
    tools_cfg = cfg.get("tools") if isinstance(cfg.get("tools"), dict) else {}
    path_cfg = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    dataset_cfg = cfg.get("dataset") if isinstance(cfg.get("dataset"), dict) else {}
    local_app = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return DashboardRoots(
        suite_root=root,
        workspace_root=resolve_repo_path(root, workspace_cfg.get("root") or path_cfg.get("workspaceRoot"), fallback=root),
        state_root=resolve_repo_path(root, workspace_cfg.get("stateRoot") or path_cfg.get("stateRoot"), fallback=root / ".noesis"),
        dataset_root=resolve_repo_path(root, dataset_cfg.get("root") or path_cfg.get("datasetRoot"), fallback=local_app / "NoesisSuite" / "dataSet"),
        tools_root=resolve_repo_path(root, tools_cfg.get("root") or path_cfg.get("toolsRoot"), fallback=root / "tools"),
        config_root=resolve_repo_path(root, path_cfg.get("configRoot"), fallback=root / "config" / "noesis"),
        runtime_config=runtime_config_path(root),
    )
