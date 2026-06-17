from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .path_rows_core import CORE_TARGETS, clean_relative, relative_from, runtime_rows, set_target
from .paths_registry import build_paths_payload
from .resolvers import load_runtime_config, runtime_config_path


def _safe_id(label: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_.:-]+", "-", label.strip()).strip("-._:") or "pathRow"
    candidate = base
    index = 2
    while candidate in used or candidate == "suiteRoot":
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _normalize_relative(root: Path, value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    candidate = Path(text).expanduser()
    if candidate.is_absolute():
        rel = relative_from(root, candidate)
        return (rel, "") if rel else ("", "based_path_outside_suite_root")
    rel = clean_relative(text)
    parts = Path(rel).parts
    if not rel or rel.startswith("../") or ".." in parts:
        return "", "relative_path_must_stay_inside_suite_root"
    return rel, ""


def _row_identity(row: dict[str, Any], used: set[str]) -> tuple[str, str, str]:
    incoming_id = str(row.get("id") or row.get("key") or "").strip()
    label = str(row.get("label") or row.get("name") or incoming_id).strip()
    if not label:
        return incoming_id or "new", "", "label_required"
    if incoming_id == "suiteRoot" or label == "suiteRoot":
        return incoming_id, label, "suiteRoot_is_locked" if incoming_id != "suiteRoot" or label != "suiteRoot" or row.get("deleted") else ""
    row_id = incoming_id if incoming_id and not incoming_id.startswith("new-") else _safe_id(label, used)
    return row_id, label, ""


def _save_deleted(row_id: str, label: str, saved_rows: list[dict[str, Any]], accepted: list[str]) -> None:
    if row_id in CORE_TARGETS:
        saved_rows.append({"id": row_id, "label": label, "source": "core", "deleted": True})
    accepted.append(row_id)


def _save_active(
    config: dict[str, Any],
    root: Path,
    row_id: str,
    label: str,
    row: dict[str, Any],
    saved_rows: list[dict[str, Any]],
    *,
    fix_missing: bool,
    created_missing: list[dict[str, str]],
) -> str:
    based = bool(row.get("basedOnSuiteRoot"))
    value = str(row.get("value") or row.get("relative") or row.get("path") or "").strip()
    source = "core" if row_id in CORE_TARGETS else "custom"
    if based:
        rel, error = _normalize_relative(root, value)
        if error:
            return error
        resolved_path = (root / rel).resolve()
        record: dict[str, Any] = {"id": row_id, "label": label, "base": "suiteRoot", "relative": rel, "source": source}
        config_value = rel
    else:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return "absolute_path_required_when_not_based_on_suiteRoot"
        resolved_path = path.resolve()
        record = {"id": row_id, "label": label, "path": str(path), "source": source}
        config_value = str(path)
    if fix_missing:
        if resolved_path.exists() and not resolved_path.is_dir():
            return "path_exists_but_is_not_directory"
        if not resolved_path.exists():
            try:
                resolved_path.mkdir(parents=True, exist_ok=True)
            except OSError:
                return "fix_missing_mkdir_failed"
            created_missing.append({"id": row_id, "path": str(resolved_path)})
    if row_id in CORE_TARGETS:
        record["target"] = CORE_TARGETS[row_id]
        set_target(config, CORE_TARGETS[row_id], config_value)
    saved_rows.append(record)
    return ""


def apply_paths_registry_update(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    rows = body.get("rows") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return {"ok": False, "error": "path_rows_required", "paths": build_paths_payload(root)}
    config_path = runtime_config_path(root)
    if not config_path.is_file():
        return {"ok": False, "error": "runtime_config_not_found", "configSource": str(config_path)}
    config = load_runtime_config(root)
    accepted: list[str] = []
    rejected: list[dict[str, str]] = []
    saved_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_labels: set[str] = {"suiteroot"}
    previous_deleted = {str(item.get("id") or ""): item for item in runtime_rows(config) if item.get("deleted")}
    fix_missing = bool(body.get("fixMissing"))
    created_missing: list[dict[str, str]] = []
    for item in rows:
        row = dict(item) if isinstance(item, dict) else {}
        row_id, label, error = _row_identity(row, seen_ids)
        if error:
            rejected.append({"id": row_id or label, "error": error})
            seen_ids.add("suiteRoot")
            continue
        if row_id == "suiteRoot":
            seen_ids.add("suiteRoot")
            continue
        if row_id in seen_ids or label.lower() in seen_labels:
            rejected.append({"id": row_id, "error": "duplicate_path_row"})
            continue
        seen_ids.add(row_id)
        seen_labels.add(label.lower())
        if row.get("deleted"):
            _save_deleted(row_id, label, saved_rows, accepted)
            continue
        error = _save_active(config, root, row_id, label, row, saved_rows, fix_missing=fix_missing, created_missing=created_missing)
        if error:
            rejected.append({"id": row_id, "error": error})
            continue
        accepted.append(row_id)
    for row_id, item in previous_deleted.items():
        if row_id not in seen_ids and row_id in CORE_TARGETS:
            saved_rows.append(item)
    config.setdefault("paths", {})["rows"] = saved_rows
    backup = config_path.with_suffix(config_path.suffix + ".bak")
    shutil.copy2(config_path, backup)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": not rejected,
        "schema": "noesis.dashboard.paths.update.v2",
        "updated": accepted,
        "rejected": rejected,
        "fixMissing": fix_missing,
        "createdMissing": created_missing,
        "backup": str(backup),
        "configSource": str(config_path),
        "paths": build_paths_payload(root),
    }
