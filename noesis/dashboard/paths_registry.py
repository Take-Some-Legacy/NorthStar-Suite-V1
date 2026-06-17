from __future__ import annotations

from pathlib import Path
from typing import Any

from .path_rows_core import (
    CORE_ORDER,
    CORE_TARGETS,
    DERIVED_SPECS,
    clean_relative,
    path_record,
    root_attr,
    runtime_rows,
    target_value,
    value_parts,
)
from .resolvers import dashboard_roots, load_runtime_config


def _base_row(root: Path, key: str, resolved: Path, config: dict[str, Any]) -> dict[str, Any]:
    target = CORE_TARGETS.get(key, "")
    based, rel, value_path = value_parts(root, target_value(config, target) if target else "", resolved)
    locked = key == "suiteRoot"
    return {
        "id": key,
        "key": key,
        "label": key,
        "kind": "base",
        "source": "core",
        "configTarget": target,
        "builtIn": True,
        "locked": locked,
        "editable": not locked,
        "renameable": not locked,
        "removable": not locked,
        "basedOnSuiteRoot": based and not locked,
        "base": "suiteRoot" if based and not locked else "",
        "relative": rel if based and not locked else "",
        "value": rel if based and not locked else value_path,
        "path": str(resolved),
        "exists": resolved.exists(),
    }


def _materialize_custom(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    based = item.get("base") == "suiteRoot" or bool(item.get("basedOnSuiteRoot"))
    rel = clean_relative(str(item.get("relative") or item.get("value") or "")) if based else ""
    raw_path = str(item.get("path") or item.get("value") or "").strip()
    path = (root / rel).resolve() if based else Path(raw_path).expanduser()
    row_id = str(item.get("id") or item.get("key") or item.get("label") or "customPath").strip()
    return {
        "id": row_id,
        "key": row_id,
        "label": str(item.get("label") or item.get("name") or row_id or "customPath").strip(),
        "kind": str(item.get("kind") or "custom"),
        "source": "custom",
        "configTarget": "",
        "builtIn": False,
        "locked": False,
        "editable": True,
        "renameable": True,
        "removable": True,
        "basedOnSuiteRoot": based,
        "base": "suiteRoot" if based else "",
        "relative": rel,
        "value": rel if based else str(path),
        "path": str(path),
        "exists": path.exists(),
    }


def path_rows(root: Path) -> list[dict[str, Any]]:
    config = load_runtime_config(root)
    roots = dashboard_roots(root)
    core = {key: _base_row(root, key, getattr(roots, root_attr(key)), config) for key in CORE_ORDER}
    custom: list[dict[str, Any]] = []
    for item in runtime_rows(config):
        row_id = str(item.get("id") or item.get("key") or "").strip()
        if row_id in core:
            core[row_id]["label"] = str(item.get("label") or row_id).strip() or row_id
            if item.get("deleted") and row_id != "suiteRoot":
                core[row_id]["deleted"] = True
        elif not item.get("deleted"):
            custom.append(_materialize_custom(root, item))
    return [core[key] for key in CORE_ORDER if not core[key].get("deleted")] + custom


def _derived_entries(roots: Any) -> dict[str, dict[str, Any]]:
    base_paths = {key: getattr(roots, root_attr(key)) for key in CORE_ORDER}
    return {name: path_record(name, base_paths[base] / Path(rel), kind="derived", base=base, relative=rel) for name, (base, rel) in DERIVED_SPECS.items()}


def build_paths_payload(root: Path) -> dict[str, Any]:
    roots = dashboard_roots(root)
    rows = path_rows(root)
    entries = {
        row["id"]: path_record(row["label"], Path(row["path"]), kind=row["kind"], rowId=row["id"], base=row.get("base", ""), relative=row.get("relative", ""), editable=row["editable"])
        for row in rows
    }
    derived = _derived_entries(roots)
    entries.update(derived)
    base_roots = {row["id"]: entries[row["id"]] for row in rows if row.get("source") == "core"}
    edit_fields = [
        {"key": row["id"], "label": row["label"], "value": row["value"], "kind": "pathRow", "editable": row["editable"], "exists": row["exists"], "group": "pathRows", "base": row.get("base", "")}
        for row in rows
    ]
    return {
        "schema": "noesis.dashboard.paths.v3",
        "configSource": str(roots.runtime_config),
        "updateEndpoint": "/api/config/paths",
        "suiteRootKey": "suiteRoot",
        "suiteRootPath": str(roots.suite_root),
        "editableKeys": [row["id"] for row in rows if row["editable"]],
        "editModel": {"schema": "noesis.ui.editModel.v1", "target": "suitePaths", "fields": edit_fields},
        "rowRegistry": {"schema": "noesis.dashboard.pathRows.v1", "rows": rows, "canAdd": True, "suiteRootLocked": True},
        "rows": rows,
        "baseRoots": base_roots,
        "derived": derived,
        "entries": entries,
        "toolDescriptorRoots": [str(roots.tools_root / "toolbelt"), str(roots.tools_root)],
    }
