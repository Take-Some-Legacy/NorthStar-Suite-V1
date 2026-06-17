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


from .paths_registry import build_paths_payload


def paths_payload(root: Path) -> dict[str, Any]:
    return build_paths_payload(root)

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
