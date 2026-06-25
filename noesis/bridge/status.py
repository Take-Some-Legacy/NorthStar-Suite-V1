from __future__ import annotations

import platform
from typing import Any, Dict

from . import dataset, memory, repo
from .auth import openai_status
from .cluster_topology import cluster_summary
from .contracts import BRIDGE_VERSION, BridgeContext
from .paths import latest_existing, load_config


def _config_summary(ctx: BridgeContext) -> Dict[str, Any]:
    cfg = load_config(ctx)
    tools = cfg.get("tools") if isinstance(cfg.get("tools"), list) else []
    return {
        "version": cfg.get("version"),
        "bridge_id": cfg.get("bridge_id"),
        "display_name": cfg.get("display_name"),
        "transport": cfg.get("transport"),
        "default_mode": cfg.get("default_mode"),
        "forceWrite": cfg.get("forceWrite"),
        "write_enable_env": cfg.get("write_enable_env"),
        "safe_roots_mode": "project_root_with_denylist",
        "tool_count": len(tools),
        "mcp_route": {
            "endpoint": ctx.mcp_routes.endpoint,
            "mcp_paths": list(ctx.mcp_routes.mcp_paths),
            "discovery_paths": list(ctx.mcp_routes.discovery_paths),
        },
        "public_contract": {
            "execute_suite_command": "always_listed",
            "write_text_file": "always_listed_write_gated",
            "delete_path": "always_listed_write_gated",
            "arbitrary_shell": False,
        },
    }


def _dataset_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    archives = raw.get("newest_archives") or []
    extracted = raw.get("newest_extracted") or []
    return {
        **raw,
        "newest_archives": archives[:5],
        "newest_extracted": extracted[:10],
        "truncated": len(archives) > 5 or len(extracted) > 10,
    }


def status(ctx: BridgeContext, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    markers = {
        name: (ctx.root / name).exists()
        for name in [
            "docs/SUITE.md",
            "suite.bat",
            "aiBridge.bat",
            "noesis/suite/cli.py",
            "noesis/bridge/cli.py",
            "noesis/supervisor/main.py",
            ".takesome",
            "NewEngine/neocore2/Cargo.toml",
        ]
    }
    ds = _dataset_summary(dataset.status(ctx, {}))
    dataset_dirs = ds.get("directories") if isinstance(ds.get("directories"), dict) else {}
    workspace_root = str(ctx.root)
    suite_root = str(ctx.operator_root)
    tools_root = str(ctx.operator_root / "tools")
    runtime_root = str(ctx.suite_root)
    dataset_root = str(ds.get("dataSetDirectory") or dataset_dirs.get("root") or "")
    access_level = "sudo_write" if getattr(ctx, "sudo", False) else ("read_write" if ctx.write_enabled else "read_only")
    warnings = []
    if int(ds.get("archive_count") or 0) > 0:
        warnings.append("dataset archives still present; run diag.dataset.lifecycle or northstar.dataset_materialize_archives")
    return {
        "schema": "northstar.bridge.status.v2",
        "bridge": {
            "name": "northstar-ai-bridge",
            "version": BRIDGE_VERSION,
            "protocol": "stdio-jsonrpc-mcp-compatible + http-jsonrpc",
            "write_enabled": ctx.write_enabled,
            "layout": "canonical-noesis-package",
        },
        "workspace": {
            "root": workspace_root,
            "workspaceRoot": workspace_root,
            "kind": "projects_repository",
            "containsMultipleProjects": True,
            "projectSelectionRequired": True,
            "activeProjectRoot": None,
            "suiteRoot": suite_root,
            "toolsRoot": tools_root,
            "datasetRoot": dataset_root,
            "runtimeRoot": runtime_root,
            "tool_root": suite_root,
            "python_cmd": ctx.python_cmd,
            "platform": platform.platform(),
            "markers": markers,
        },
        "access": {
            "schema": "northstar.bridge.access.v1",
            "level": access_level,
            "write_enabled": ctx.write_enabled,
            "sudo": bool(getattr(ctx, "sudo", False)),
            "write_boundary": "selectedProjectRootWithinWorkspaceRoot",
            "toolsRoot_policy": "read_execute_default_change_only_when_explicitly_required",
            "datasetRoot_policy": "reference_orientation_data_not_project_workspace",
            "projectSelection_policy": "resolve_activeProjectRoot_before_project_scoped_work",
        },
        "host_binding": ctx.host_binding.as_dict() if ctx.host_binding else None,
        "cluster": cluster_summary(ctx.host_binding),
        "cluster_doctor": {
            "active_probe_endpoint": "/cluster/doctor",
            "active_probe_command": "python -m noesis bridge endpoint cluster-doctor --json",
            "request_outcome_schema": "noesis.suite.request_outcome.v1",
            "safe_default": "passive_status_does_not_probe_network",
        },
        "openai": openai_status(ctx),
        "dataset": ds,
        "config": _config_summary(ctx),
        "recent_diagnostics": latest_existing(ctx.root, ["last-incident.md", "last-incident.json", "buildERR-*.log", ".takesome/incidents/*/summary.md"], 6),
        "warnings": warnings,
        "truncated": True,
    }


def operator_snapshot(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    logs_limit = max(1, min(int(args.get("logs_limit", 5)), 20))
    knowledge_limit = max(1, min(int(args.get("knowledge_limit", 5)), 20))
    task_limit = max(1, min(int(args.get("task_limit", 3)), 10))
    note_limit = max(0, min(int(args.get("notes_limit", 1)), 5))
    return {
        "schema": "northstar.operator.snapshot.v2",
        "status": status(ctx, {}),
        "logs": repo.list_logs(ctx, {"limit": logs_limit}),
        "dataset": _dataset_summary(dataset.status(ctx, {})),
        "operator_state": memory.current_state(ctx, {"artifact_limit": 8}),
        "task_memory": memory.task_snapshot(ctx, {"limit": task_limit, "knowledge_limit": knowledge_limit, "include_events": False}),
        "notes": memory.note_read(ctx, {"limit": note_limit, "max_bytes": 2048}) if note_limit else {"notes": []},
        "recommended_flow": [
            "execute_suite_command:diag.dataset.lifecycle",
            "execute_suite_command:tools.operator.memory",
            "get_status",
        ],
        "truncated": True,
    }
