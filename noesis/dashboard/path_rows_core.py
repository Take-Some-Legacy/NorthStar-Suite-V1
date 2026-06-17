from __future__ import annotations

from pathlib import Path
from typing import Any

CORE_ORDER = ["suiteRoot", "workspaceRoot", "stateRoot", "datasetRoot", "toolsRoot", "configRoot"]
CORE_TARGETS = {
    "workspaceRoot": "workspace.root",
    "stateRoot": "workspace.stateRoot",
    "datasetRoot": "dataset.root",
    "toolsRoot": "tools.root",
    "configRoot": "paths.configRoot",
}
DERIVED_SPECS = {
    "toolbeltRoot": ("toolsRoot", "toolbelt"),
    "suiteActionsRoot": ("toolsRoot", "suite/actions"),
    "runtimeConfig": ("configRoot", "runtime.v1.json"),
    "dashboardRoot": ("stateRoot", "dashboard"),
    "runsRoot": ("stateRoot", "runs"),
    "indexRoot": ("stateRoot", "index"),
    "datasetArchivesRoot": ("datasetRoot", "archives"),
    "datasetExtractedRoot": ("datasetRoot", "extracted"),
    "datasetIndexRoot": ("datasetRoot", "index"),
}


def target_value(config: dict[str, Any], target: str) -> str:
    node: Any = config
    for part in target.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return str(node or "").strip()


def set_target(config: dict[str, Any], target: str, value: str) -> None:
    node = config
    parts = target.split(".")
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def path_record(name: str, path: Path, **extra: Any) -> dict[str, Any]:
    data = {"name": name, "path": str(path), "exists": path.exists()}
    data.update(extra)
    return data


def clean_relative(value: str) -> str:
    text = value.replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text or "."


def relative_from(root: Path, path: Path) -> str:
    try:
        return clean_relative(path.resolve().relative_to(root.resolve()).as_posix())
    except Exception:
        return ""


def value_parts(root: Path, raw: str, resolved: Path) -> tuple[bool, str, str]:
    text = str(raw or "").strip()
    if text:
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            return True, clean_relative(text), str((root / candidate).resolve())
        rel = relative_from(root, candidate)
        return (True, rel, str(candidate)) if rel else (False, "", str(candidate))
    rel = relative_from(root, resolved)
    return (True, rel, str(resolved)) if rel else (False, "", str(resolved))


def runtime_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    paths = config.get("paths") if isinstance(config.get("paths"), dict) else {}
    rows = paths.get("rows") if isinstance(paths.get("rows"), list) else []
    return [dict(item) for item in rows if isinstance(item, dict)]


def root_attr(key: str) -> str:
    return {
        "suiteRoot": "suite_root",
        "workspaceRoot": "workspace_root",
        "stateRoot": "state_root",
        "datasetRoot": "dataset_root",
        "toolsRoot": "tools_root",
        "configRoot": "config_root",
    }[key]
