from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .resolvers import dashboard_roots, load_runtime_config, read_json


def worker_payload(root: Path) -> dict[str, Any]:
    cfg = load_runtime_config(root)
    key = "cl" + "uster"
    group = cfg.get(key) if isinstance(cfg.get(key), dict) else {}
    members = group.get("peers") if isinstance(group.get("peers"), list) else []
    return {
        "schema": "noesis.dashboard.worker.v1",
        "root": str(root),
        "role": str(group.get("role") or "operator"),
        "nodeGroup": {
            "enabled": bool(group.get("enabled", False)),
            "id": str(group.get(key + "_id") or ""),
            "role": str(group.get("role") or "operator"),
            "members": members,
            "memberCount": len(members),
        },
    }


def _path_record(name: str, path: Path, *, kind: str, base: str = "", rel: str = "", editable: bool = False) -> dict[str, Any]:
    return {"name": name, "path": str(path), "exists": path.exists(), "kind": kind, "base": base, "relative": rel, "editable": editable}


def paths_payload(root: Path) -> dict[str, Any]:
    roots = dashboard_roots(root)
    base_paths = {
        "suiteRoot": roots.suite_root,
        "workspaceRoot": roots.workspace_root,
        "stateRoot": roots.state_root,
        "datasetRoot": roots.dataset_root,
        "toolsRoot": roots.tools_root,
        "configRoot": roots.config_root,
    }
    base_roots = {
        "suiteRoot": _path_record("suiteRoot", roots.suite_root, kind="base", editable=False),
        "workspaceRoot": _path_record("workspaceRoot", roots.workspace_root, kind="base", editable=True),
        "stateRoot": _path_record("stateRoot", roots.state_root, kind="base", editable=True),
        "datasetRoot": _path_record("datasetRoot", roots.dataset_root, kind="base", editable=True),
        "toolsRoot": _path_record("toolsRoot", roots.tools_root, kind="base", editable=True),
        "configRoot": _path_record("configRoot", roots.config_root, kind="base", editable=True),
    }
    derived_specs = {
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
    derived = {name: _path_record(name, base_paths[base] / Path(rel), kind="derived", base=base, rel=rel) for name, (base, rel) in derived_specs.items()}
    entries = {**base_roots, **derived}
    editable_keys = ["workspaceRoot", "stateRoot", "datasetRoot", "toolsRoot", "configRoot"]
    edit_fields = [
        {"key": name, "label": name, "value": item["path"], "kind": "path", "editable": item["editable"], "exists": item["exists"], "group": "baseRoots"}
        for name, item in base_roots.items()
    ] + [
        {"key": name, "label": name, "value": item["relative"], "kind": "computedPath", "editable": False, "exists": item["exists"], "group": "derived", "base": item["base"], "expression": "${" + item["base"] + "}/" + item["relative"]}
        for name, item in derived.items()
    ]
    return {
        "schema": "noesis.dashboard.paths.v2",
        "configSource": str(roots.runtime_config),
        "updateEndpoint": "/api/config/paths",
        "editableKeys": editable_keys,
        "editModel": {"schema": "noesis.ui.editModel.v1", "target": "suitePaths", "fields": edit_fields},
        "baseRoots": base_roots,
        "derived": derived,
        "entries": entries,
        "toolDescriptorRoots": [str(roots.tools_root / "toolbelt"), str(roots.tools_root)],
    }


def load_suite_actions(root: Path, *, limit: int = 240) -> list[dict[str, Any]]:
    actions_root = dashboard_roots(root).tools_root / "suite" / "actions"
    actions: list[dict[str, Any]] = []
    if not actions_root.exists():
        return actions
    for path in sorted(actions_root.rglob("*.json")):
        data = read_json(path)
        action_id = str(data.get("action_id") or data.get("id") or "").strip()
        if not action_id:
            continue
        args = data.get("args") if isinstance(data.get("args"), list) else []
        command = str(data.get("command") or "").strip()
        actions.append({
            "id": action_id,
            "title": str(data.get("title") or action_id),
            "group": str(data.get("group") or path.parent.name),
            "description": str(data.get("description") or ""),
            "dangerLevel": str(data.get("danger_level") or data.get("dangerLevel") or "normal"),
            "safeForMenu": bool(data.get("safe_for_menu", False)),
            "descriptor": str(path),
            "command": command,
            "args": [str(item) for item in args],
            "suiteCommand": f"python -m noesis suite --run {action_id} --json",
        })
        if len(actions) >= limit:
            break
    return actions


def operator_tasks_payload(root: Path, runs: Iterable[Any]) -> dict[str, Any]:
    run_list = list(runs)
    actions = load_suite_actions(root)
    action_ids = {item["id"] for item in actions}
    latest_core = next((run for run in reversed(run_list) if getattr(run, "scope", "") == "noesis-core"), None)
    latest_full = next((run for run in reversed(run_list) if getattr(run, "scope", "") == "full-repo"), None)
    recommended = [
        {"title": "Refresh dashboard index", "status": "ready", "command": "python -m noesis runs index", "kind": "dashboard"},
        {"title": "Verify dashboard publication", "status": "ready" if "noesis.dashboard.verify" in action_ids else "missing-action", "actionId": "noesis.dashboard.verify", "command": "python -m noesis suite --run noesis.dashboard.verify --json", "kind": "suite-action"},
        {"title": "Run focused NOESIS-core gate", "status": "ready", "actionId": "noesis.test_dev_repo.verify.core", "command": "python -m noesis suite --run noesis.test_dev_repo.verify.core --json", "kind": "suite-action"},
        {"title": "Run full-repo gate skeleton", "status": "ready", "actionId": "noesis.test_dev_repo.verify.full", "command": "python -m noesis suite --run noesis.test_dev_repo.verify.full --json", "kind": "suite-action"},
        {"title": "Inspect operator memory", "status": "ready" if "diag.operator.memory" in action_ids else "missing-action", "actionId": "diag.operator.memory", "command": "python -m noesis suite --run diag.operator.memory --json", "kind": "suite-action"},
    ]
    active = []
    if latest_core:
        active.append({"name": "latest-core-gate", "status": latest_core.status, "runId": latest_core.run_id, "reason": latest_core.reason or latest_core.failed_phase})
    if latest_full:
        active.append({"name": "latest-full-gate", "status": latest_full.status, "runId": latest_full.run_id, "reason": latest_full.reason or latest_full.failed_phase})
    groups: dict[str, int] = {}
    for action in actions:
        groups[action["group"]] = groups.get(action["group"], 0) + 1
    return {
        "schema": "noesis.dashboard.operator_tasks.v1",
        "summary": {"activeObserved": len(active), "availableActions": len(actions), "recommended": len(recommended), "groups": groups, "submissionMode": "suite-cli"},
        "activeObserved": active,
        "recommended": recommended,
        "availableActions": actions,
        "submission": {"mode": "suite-cli", "commandTemplate": "python -m noesis suite --run <action_id> --json", "note": "Dashboard composes and executes Suite actions through the NOESIS operation API."},
    }
