from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .paths_registry import build_paths_payload
from .paths_registry_update import apply_paths_registry_update
from .runs import read_json

EDITABLE_PATH_KEYS = {"workspaceRoot", "stateRoot", "datasetRoot", "toolsRoot", "configRoot"}


def _legacy_update_dashboard_paths(root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    requested = {str(key): str(value).strip() for key, value in dict(updates or {}).items()}
    accepted = {key: value for key, value in requested.items() if key in EDITABLE_PATH_KEYS and value}
    rejected = sorted(key for key in requested if key not in EDITABLE_PATH_KEYS)
    config_path = root / "config" / "noesis" / "runtime.v1.json"
    if not accepted:
        return {"ok": False, "error": "no_editable_paths_supplied", "rejected": rejected, "paths": build_paths_payload(root)}
    if not config_path.is_file():
        return {"ok": False, "error": "runtime_config_not_found", "configSource": str(config_path)}
    config = read_json(config_path)
    backup = config_path.with_suffix(config_path.suffix + ".bak")
    shutil.copy2(config_path, backup)
    config.setdefault("workspace", {})
    config.setdefault("dataset", {})
    config.setdefault("tools", {})
    config.setdefault("paths", {})
    if "workspaceRoot" in accepted:
        config["workspace"]["root"] = accepted["workspaceRoot"]
    if "stateRoot" in accepted:
        config["workspace"]["stateRoot"] = accepted["stateRoot"]
    if "datasetRoot" in accepted:
        config["dataset"]["root"] = accepted["datasetRoot"]
    if "toolsRoot" in accepted:
        config["tools"]["root"] = accepted["toolsRoot"]
    if "configRoot" in accepted:
        config["paths"]["configRoot"] = accepted["configRoot"]
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, "schema": "noesis.dashboard.paths.update.v1", "updated": sorted(accepted), "rejected": rejected, "backup": str(backup), "configSource": str(config_path), "paths": build_paths_payload(root)}


def update_dashboard_paths(root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    body = dict(updates or {})
    if isinstance(body.get("rows"), list):
        return apply_paths_registry_update(root, body)
    return _legacy_update_dashboard_paths(root, body)
