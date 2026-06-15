from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict

from .contracts import BridgeContext, now_utc
from .paths import rel
from .memory_store import *


def _mtime_key(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


def _iso_mtime(path: Path) -> str | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        return None


def _count_json_files(path: Path) -> int:
    return len(list(path.glob("*.json"))) if path.exists() else 0


def _latest_existing_rel(ctx: BridgeContext, patterns: list[str], limit: int = 8) -> list[Dict[str, Any]]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(ctx.root.glob(pattern))
    out: list[Dict[str, Any]] = []
    for path in sorted(set(paths), key=_mtime_key, reverse=True)[:limit]:
        if path.exists() and path.is_file():
            out.append({"path": rel(ctx.root, path), "size_bytes": path.stat().st_size, "modified_at": _iso_mtime(path)})
    return out


def _agent_status_path(ctx: BridgeContext) -> Path:
    return ctx.ai_root / "state" / "agent-status.json"


def read_agent_status(ctx: BridgeContext) -> Dict[str, Any]:
    path = _agent_status_path(ctx)
    payload = _json_file(path, {})
    if not isinstance(payload, dict) or not payload:
        return {
            "schema": "northstar.operatorAgentStatus.v1",
            "status": "unknown",
            "exists": False,
            "path": rel(ctx.root, path),
        }
    payload = dict(payload)
    payload.setdefault("schema", "northstar.operatorAgentStatus.v1")
    payload["exists"] = True
    payload["path"] = rel(ctx.root, path)
    return payload


def collect_current_state(ctx: BridgeContext, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Collect a compact, read-only snapshot of the current Suite/engine state."""

    args = args or {}
    config = _json_file(ctx.bridge_config, {})
    suite_shell = ctx.root / "tools" / "scripts" / "takesome" / "suite" / "shell.py"
    suite_version = "unknown"
    if suite_shell.exists():
        text = suite_shell.read_text(encoding="utf-8", errors="replace")
        marker = 'SUITE_VERSION = "'
        if marker in text:
            suite_version = text.split(marker, 1)[1].split('"', 1)[0]
    dataset_index = ctx.root / ".takesome" / "dataSet" / "index" / "dataset-index.json"
    browser_index = ctx.root / ".takesome" / "dataSet" / "index" / "dataset-browser-index.json"
    knowledge_registry = ctx.root / ".takesome" / "dataSet" / "index" / "knowledge-registry.json"
    maturity_report = ctx.root / ".takesome" / "dataSet" / "index" / "dataset-maturity-report.json"
    entry_value_index = ctx.root / ".takesome" / "dataSet" / "index" / "entry-value-index.json"
    task_index = _json_file(_task_index_path(ctx), {})
    knowledge_index = _json_file(_knowledge_index_path(ctx), {})
    note_index = _load_note_index(ctx)
    current_id = _current_task_id(ctx)
    return {
        "schema": "northstar.operatorCurrentState.v1",
        "updated_at": now_utc(),
        "bridge": {
            "version": __import__("northstar_bridge.contracts", fromlist=["BRIDGE_VERSION"]).BRIDGE_VERSION,
            "write_enabled": ctx.write_enabled,
            "config_version": config.get("version"),
            "config_path": rel(ctx.root, ctx.bridge_config) if ctx.bridge_config.exists() else None,
        },
        "agent_status": read_agent_status(ctx),
        "suite": {"version": suite_version, "shell": rel(ctx.root, suite_shell) if suite_shell.exists() else None},
        "workspace": {
            "root": str(ctx.root),
            "markers": {
                "docs/SUITE.md": (ctx.root / "docs" / "SUITE.md").exists(),
                "suite.bat": (ctx.root / "suite.bat").exists(),
                "aiBridge.bat": (ctx.root / "aiBridge.bat").exists(),
                "NewEngine/neocore2/Cargo.toml": (ctx.root / "NewEngine" / "neocore2" / "Cargo.toml").exists(),
            },
        },
        "dataset": {
            "indexes": {
                "dataset_index": {"path": rel(ctx.root, dataset_index), "exists": dataset_index.exists(), "modified_at": _iso_mtime(dataset_index)},
                "browser_index": {"path": rel(ctx.root, browser_index), "exists": browser_index.exists(), "modified_at": _iso_mtime(browser_index)},
                "knowledge_registry": {"path": rel(ctx.root, knowledge_registry), "exists": knowledge_registry.exists(), "modified_at": _iso_mtime(knowledge_registry)},
                "maturity_report": {"path": rel(ctx.root, maturity_report), "exists": maturity_report.exists(), "modified_at": _iso_mtime(maturity_report)},
                "entry_value_index": {"path": rel(ctx.root, entry_value_index), "exists": entry_value_index.exists(), "modified_at": _iso_mtime(entry_value_index)},
            }
        },
        "operator_memory": {
            "current_task_id": current_id or None,
            "tasks_total": len(task_index.get("items", [])) if isinstance(task_index, dict) else 0,
            "knowledge_total": len(knowledge_index.get("items", [])) if isinstance(knowledge_index, dict) else 0,
            "notes_total": len(note_index.get("items", [])) if isinstance(note_index, dict) else 0,
            "task_files": _count_json_files(_tasks_dir(ctx)),
            "knowledge_files": _count_json_files(_knowledge_dir(ctx)),
            "cache_namespaces": len([p for p in (ctx.ai_root / "cache").iterdir() if p.is_dir()]) if (ctx.ai_root / "cache").exists() else 0,
        },
        "latest_artifacts": _latest_existing_rel(ctx, [
            ".takesome/suite/runs/*/result.json",
            ".takesome/dataSet/index/dataset-maturity-report.json",
            ".takesome/dataSet/index/entry-value-index.json",
            "docs/audits/DATASET_MATURITY_REPORT.md",
            ".takesome/incidents/*/summary.md",
        ], limit=max(1, min(int(args.get("artifact_limit", 8)), 30))),
    }


def current_state(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    return collect_current_state(ctx, args)


def agent_status(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    return read_agent_status(ctx)

__all__ = [
    "_mtime_key",
    "_iso_mtime",
    "_count_json_files",
    "_latest_existing_rel",
    "_agent_status_path",
    "read_agent_status",
    "collect_current_state",
    "current_state",
    "agent_status",
]
