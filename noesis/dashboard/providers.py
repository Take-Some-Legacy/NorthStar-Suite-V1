from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from noesis.bridge.host_binding import DEFAULT_BRIDGE_PORT, DEFAULT_ENDPOINT_PATH, DEFAULT_HEALTH_PATH, resolve_host_binding
from noesis.suite.repository_index import REPOSITORY_INDEX_FILENAME, default_repos_root, load_repository_index, validate_repository_index

from .paths_registry import build_paths_payload
from .resolvers import dashboard_roots, load_runtime_config, read_json


CLUSTER_PROFILES: tuple[dict[str, str], ...] = (
    {
        "id": "single-host-first",
        "title": "Single host first",
        "intent": "Prefer one local origin, but keep cluster metadata visible and ready.",
        "recommendedFor": "local operator workstation",
    },
    {
        "id": "federated-machines",
        "title": "Federated machines",
        "intent": "Treat peers as first-class Suite machines and validate health/status endpoints.",
        "recommendedFor": "multi-machine NOESIS/Suite federation",
    },
    {
        "id": "tunnel-public",
        "title": "Tunnel public",
        "intent": "Expect public/tunnel origins and prefer advertised endpoint checks.",
        "recommendedFor": "Cloudflare/domain exposed bridge",
    },
    {
        "id": "strict-doctor",
        "title": "Strict doctor",
        "intent": "Include status validation, disabled peers and mismatch diagnostics.",
        "recommendedFor": "pre-release or infrastructure incident review",
    },
)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _truthy(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _peer_from_any(value: object, index: int) -> dict[str, Any]:
    if isinstance(value, dict):
        origin = _text(value.get("public_origin") or value.get("origin") or value.get("url") or value.get("base_origin"))
        machine_id = _text(value.get("machine_id") or value.get("host_id") or value.get("id"), f"peer-{index + 1}")
        endpoint = _text(value.get("endpoint_path") or value.get("endpoint"), DEFAULT_ENDPOINT_PATH)
        health = _text(value.get("health_path") or value.get("health"), DEFAULT_HEALTH_PATH)
        return {
            "machineId": machine_id,
            "role": _text(value.get("role"), "peer"),
            "publicOrigin": origin,
            "endpointPath": endpoint,
            "healthPath": health,
            "endpointUrl": _text(value.get("endpoint_url") or value.get("endpointUrl")),
            "healthUrl": _text(value.get("health_url") or value.get("healthUrl")),
            "enabled": _truthy(value.get("enabled"), True),
            "tags": value.get("tags") if isinstance(value.get("tags"), list) else [],
        }
    raw = _text(value)
    machine_id = raw.split("=", 1)[0] if "=" in raw else f"peer-{index + 1}"
    origin = raw.split("=", 1)[1] if "=" in raw else raw
    return {
        "machineId": machine_id,
        "role": "peer",
        "publicOrigin": origin,
        "endpointPath": DEFAULT_ENDPOINT_PATH,
        "healthPath": DEFAULT_HEALTH_PATH,
        "endpointUrl": "",
        "healthUrl": "",
        "enabled": bool(origin),
        "tags": [],
    }


def _cluster_binding(root: Path) -> dict[str, Any]:
    try:
        return resolve_host_binding(root).as_dict()
    except Exception as exc:
        return {"diagnostics": [f"binding_resolution_failed:{exc}"]}


def cluster_payload(root: Path) -> dict[str, Any]:
    cfg = load_runtime_config(root)
    roots = dashboard_roots(root)
    cluster_cfg = _dict(cfg.get("cluster"))
    bridge_cfg = _dict(cfg.get("bridge"))
    diagnostics_cfg = _dict(cluster_cfg.get("diagnostics"))
    ui_cfg = _dict(cluster_cfg.get("dashboard") or cluster_cfg.get("ui"))
    binding = _cluster_binding(root)

    raw_peers = _list(cluster_cfg.get("peers")) or _list(binding.get("peers"))
    peers = [_peer_from_any(peer, index) for index, peer in enumerate(raw_peers)]
    enabled_peer_count = len([peer for peer in peers if peer.get("enabled")])

    local = {
        "machineId": _text(cluster_cfg.get("machine_id") or binding.get("machine_id"), "local-machine"),
        "role": _text(cluster_cfg.get("role") or binding.get("role"), "operator"),
        "clusterId": _text(cluster_cfg.get("cluster_id") or binding.get("cluster_id"), "local"),
        "deploymentProfile": _text(cluster_cfg.get("deployment_profile") or cfg.get("deployment_profile") or binding.get("deployment_profile"), "single-machine"),
        "networkMode": _text(cluster_cfg.get("network_mode") or binding.get("network_mode"), "local"),
        "bindHost": _text(bridge_cfg.get("host") or binding.get("bind_host"), "127.0.0.1"),
        "bindPort": int(bridge_cfg.get("port") or binding.get("bind_port") or DEFAULT_BRIDGE_PORT),
        "publicOrigin": _text(bridge_cfg.get("public_origin") or binding.get("public_origin")),
        "advertisedOrigin": _text(binding.get("advertised_origin")),
        "endpointPath": _text(bridge_cfg.get("endpoint") or binding.get("endpoint_path"), DEFAULT_ENDPOINT_PATH),
        "endpointUrl": _text(bridge_cfg.get("public_endpoint") or binding.get("endpoint_url")),
        "healthPath": _text(binding.get("health_path"), DEFAULT_HEALTH_PATH),
        "healthUrl": _text(binding.get("health_url")),
    }

    timeout = _float(diagnostics_cfg.get("timeout_sec") or diagnostics_cfg.get("timeout"), 1.5)
    include_status = _truthy(diagnostics_cfg.get("include_status"), True)
    include_disabled = _truthy(diagnostics_cfg.get("include_disabled"), False)
    profile = _text(ui_cfg.get("profile") or cluster_cfg.get("profile") or local["networkMode"], "single-host-first")
    doctor = f"python -m noesis bridge endpoint cluster-doctor --timeout {timeout:g} --json"
    if not include_status:
        doctor += " --skip-status"
    if include_disabled:
        doctor += " --include-disabled"

    return {
        "schema": "noesis.dashboard.cluster.v1",
        "enabled": _truthy(cluster_cfg.get("enabled"), bool(peers) or local["clusterId"] not in {"", "local", "single", "standalone"}),
        "profile": profile,
        "profiles": list(CLUSTER_PROFILES),
        "config": {
            "runtimeConfig": str(roots.runtime_config),
            "source": "config/noesis/runtime.v1.json",
            "diagnostics": {
                "timeoutSec": timeout,
                "includeStatus": include_status,
                "includeDisabled": include_disabled,
            },
            "ui": {
                "viewMode": _text(ui_cfg.get("view_mode"), "topology"),
                "peerFilter": _text(ui_cfg.get("peer_filter"), ""),
                "showDisabled": _truthy(ui_cfg.get("show_disabled"), include_disabled),
            },
        },
        "topology": {
            "clusterId": local["clusterId"],
            "machineCount": 1 + enabled_peer_count,
            "enabledPeerCount": enabled_peer_count,
            "peerCount": len(peers),
            "mode": local["deploymentProfile"],
            "networkMode": local["networkMode"],
        },
        "local": local,
        "peers": peers,
        "diagnostics": list(binding.get("diagnostics") or []),
        "commands": {
            "doctor": doctor,
            "binding": "python -m noesis bridge endpoint binding --json",
            "endpoint": "python -m noesis bridge endpoint endpoint --json",
            "initHost": f"python -m noesis bridge endpoint init-host --machine-id {local['machineId']} --cluster-id {local['clusterId']} --public-origin <public-origin> --json",
        },
    }


def _repository_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _repository_row(index: Any, validation: dict[str, Any], *, current: bool = False) -> dict[str, Any]:
    payload = _dict(getattr(index, "payload", {}))
    repo = _dict(payload.get("repository"))
    tools = _dict(payload.get("tools"))
    commands = _dict(payload.get("commands"))
    required = _list(tools.get("required"))
    optional = _list(tools.get("optional"))
    repo_dir = getattr(index, "repo_dir")
    index_file = getattr(index, "index_file")
    name = _text(repo.get("name"), Path(repo_dir).name)
    return {
        "id": _text(repo.get("id"), name),
        "name": name,
        "kind": _text(repo.get("kind"), "repository"),
        "description": _text(repo.get("description")),
        "tags": _repository_tags(repo.get("tags")),
        "repoDir": str(repo_dir),
        "indexFile": str(index_file),
        "reposRoot": str(getattr(index, "repos_root")),
        "workdir": str(getattr(index, "workdir")),
        "datasetDir": str(getattr(index, "dataset_dir")),
        "artifactsDir": str(getattr(index, "artifacts_dir")),
        "logsDir": str(getattr(index, "logs_dir")),
        "tmpDir": str(getattr(index, "tmp_dir")),
        "executionCwd": str(getattr(index, "execution_cwd")),
        "status": "ok" if validation.get("ok") else "needs-attention",
        "ok": bool(validation.get("ok")),
        "current": bool(current),
        "schemaOk": payload.get("schema") == "takesome.repository_operator_index.v1",
        "diagnostics": _list(validation.get("diagnostics")),
        "requiredTools": len(required),
        "optionalTools": len(optional),
        "commandCount": len(commands),
        "commands": sorted(str(key) for key in commands.keys()),
        "openCommand": f"cd {repo_dir}",
        "doctorCommand": f"python -m noesis env status --repo-dir {repo_dir} --json",
    }


def _discover_repository_rows(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    diagnostics: list[str] = []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    current_index, current_diags = load_repository_index(root)
    diagnostics.extend(current_diags)
    current_validation = validate_repository_index(current_index, list(current_diags))
    source = {
        "currentRoot": str(root),
        "indexFilename": REPOSITORY_INDEX_FILENAME,
        "reposRoot": str(current_index.repos_root if current_index else default_repos_root()),
        "env": "TAKESOME_REPOS_ROOT",
        "mode": "static-dashboard-draft-editor",
    }

    def add(index: Any | None, diags: list[str], *, current: bool = False) -> None:
        if index is None:
            return
        key = str(index.index_file).lower()
        if key in seen:
            return
        seen.add(key)
        rows.append(_repository_row(index, validate_repository_index(index, list(diags)), current=current))

    add(current_index, current_diags, current=True)
    repos_root = current_index.repos_root if current_index else default_repos_root()
    if repos_root.exists() and repos_root.is_dir():
        try:
            candidates = sorted(path for path in repos_root.iterdir() if path.is_dir())
        except Exception as exc:
            candidates = []
            diagnostics.append(f"cannot list reposRoot {repos_root}: {exc}")
        for candidate in candidates:
            index_file = candidate / REPOSITORY_INDEX_FILENAME
            if not index_file.exists():
                continue
            index, diags = load_repository_index(candidate)
            diagnostics.extend(diags)
            add(index, diags, current=current_index is not None and index is not None and index.index_file == current_index.index_file)
    else:
        diagnostics.append(f"reposRoot is not accessible: {repos_root}")

    rows.sort(key=lambda item: (0 if item.get("current") else 1, item.get("name", "").lower(), item.get("repoDir", "").lower()))
    return rows, source, diagnostics


def repositories_payload(root: Path) -> dict[str, Any]:
    rows, source, diagnostics = _discover_repository_rows(root)
    ok_count = len([row for row in rows if row.get("ok")])
    current = next((row for row in rows if row.get("current")), None)
    return {
        "schema": "noesis.dashboard.repositories.v1",
        "source": source,
        "counts": {
            "repositories": len(rows),
            "ok": ok_count,
            "needsAttention": len(rows) - ok_count,
            "draftChanges": 0,
        },
        "current": current,
        "rows": rows,
        "diagnostics": diagnostics,
        "draft": {
            "storageKey": "noesis.dashboard.repositories.draft.v1",
            "writable": False,
            "mode": "browser-local-draft",
            "note": "Add, edit and delete are staged locally in the dashboard until an explicit repository index write action is enabled.",
        },
        "commands": {
            "refresh": "python -m noesis runs index",
            "status": "python -m noesis env status --repo-dir <repo-dir> --json",
            "doctor": "python -m noesis env doctor --repo-dir <repo-dir> --json",
        },
        "template": {
            "schema": "takesome.repository_operator_index.v1",
            "repository": {
                "name": "new-repository",
                "kind": "library",
                "description": "Repository managed by SuiteLab.",
                "tags": [],
            },
            "paths": {
                "workdir": "workspace",
                "dataset_dir": "dataset",
                "artifacts_dir": "workspace/artifacts",
                "logs_dir": "workspace/logs",
                "tmp_dir": "workspace/tmp",
            },
            "tools": {"required": [], "optional": [{"id": "git", "command": "git", "version_arg": "--version"}]},
            "commands": {},
            "operator": {"read_roots": [".", "dataset", "workspace"], "write_roots": ["workspace", "dataset"]},
        },
    }


def worker_payload(root: Path) -> dict[str, Any]:
    cluster = cluster_payload(root)
    local = cluster.get("local") or {}
    topology = cluster.get("topology") or {}
    return {
        "schema": "noesis.dashboard.worker.v1",
        "root": str(root),
        "role": str(local.get("role") or "operator"),
        "machineId": str(local.get("machineId") or "local-machine"),
        "nodeGroup": {
            "enabled": bool(cluster.get("enabled", False)),
            "id": str(topology.get("clusterId") or ""),
            "role": str(local.get("role") or "operator"),
            "mode": str(topology.get("mode") or "single-machine"),
            "networkMode": str(topology.get("networkMode") or "local"),
            "members": cluster.get("peers") or [],
            "memberCount": int(topology.get("machineCount") or 1),
        },
    }


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
    cluster = cluster_payload(root)
    recommended = [
        {"title": "Refresh dashboard index", "status": "ready", "command": "python -m noesis runs index", "kind": "dashboard"},
        {"title": "Run cluster doctor", "status": "ready", "command": (cluster.get("commands") or {}).get("doctor", "python -m noesis bridge endpoint cluster-doctor --json"), "kind": "cluster"},
        {"title": "Inspect cluster binding", "status": "ready", "command": (cluster.get("commands") or {}).get("binding", "python -m noesis bridge endpoint binding --json"), "kind": "cluster"},
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
