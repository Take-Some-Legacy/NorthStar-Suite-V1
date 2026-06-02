from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .contracts import BridgeContext, BridgeError, now_utc
from .paths import rel
from .memory_schema import MAX_FLOW_BYTES
from .memory_store import *
from .memory_queries import _mtime_key, _iso_mtime, collect_current_state


def _rel_or_none(ctx: BridgeContext, path: Path | None) -> str | None:
    return rel(ctx.root, path) if path is not None and path.exists() else None


def _delete_file(ctx: BridgeContext, path: Path, *, dry_run: bool, reason: str, out: list[Dict[str, Any]]) -> None:
    if not path.exists() or not path.is_file():
        return
    out.append({"path": rel(ctx.root, path), "reason": reason, "size_bytes": path.stat().st_size, "dry_run": dry_run})
    if not dry_run:
        try:
            path.unlink()
        except Exception as exc:
            out[-1]["error"] = str(exc)


def _trim_json_index(
    ctx: BridgeContext,
    *,
    index_path: Path,
    dir_path: Path,
    id_key: str,
    max_items: int,
    keep_ids: set[str],
    dry_run: bool,
    removed: list[Dict[str, Any]],
    file_reason: str,
) -> Dict[str, Any]:
    index = _json_file(index_path, {})
    if not isinstance(index, dict):
        index = {"schema": "northstar.generatedIndex.v1", "items": []}
    items = [item for item in list(index.get("items", [])) if isinstance(item, dict)]
    selected: list[Dict[str, Any]] = []
    dropped: list[Dict[str, Any]] = []
    for item in items:
        item_id = str(item.get(id_key) or "")
        if item_id in keep_ids or len(selected) < max_items:
            selected.append(item)
        else:
            dropped.append(item)
    keep_paths: set[Path] = set()
    for item in selected:
        raw_path = str(item.get("path") or "")
        if raw_path:
            keep_paths.add((ctx.root / raw_path).resolve())
    for item in dropped:
        raw_path = str(item.get("path") or "")
        if raw_path:
            candidate = (ctx.root / raw_path).resolve()
            try:
                candidate.relative_to(dir_path.resolve())
            except Exception:
                continue
            _delete_file(ctx, candidate, dry_run=dry_run, reason=file_reason, out=removed)
    for path in sorted(dir_path.glob("*.json"), key=_mtime_key, reverse=True):
        if path.resolve() == index_path.resolve() or path.resolve() in keep_paths:
            continue
        if path.name in {"current-engine-state.json"}:
            continue
        # Delete orphan files only after keeping the same retention window by mtime.
        retained_orphans = sorted(
            [p for p in dir_path.glob("*.json") if p.resolve() not in keep_paths and p.resolve() != index_path.resolve()],
            key=_mtime_key,
            reverse=True,
        )[: max_items]
        if path not in retained_orphans:
            _delete_file(ctx, path, dry_run=dry_run, reason=f"orphan-{file_reason}", out=removed)
    if not dry_run:
        index["items"] = selected
        index["updated_at"] = now_utc()
        index["hygiene"] = {"max_items": max_items, "kept": len(selected), "dropped": len(dropped), "updated_at": now_utc()}
        _write_json(index_path, index)
    return {"kept": len(selected), "dropped": len(dropped), "index_path": rel(ctx.root, index_path)}


def _compact_current_flow_file(ctx: BridgeContext, *, dry_run: bool, max_bytes: int = MAX_FLOW_BYTES) -> Dict[str, Any]:
    path = _notes_dir(ctx) / "current-flow.md"
    if not path.exists():
        return {"exists": False, "path": rel(ctx.root, path)}
    size = path.stat().st_size
    if size <= max_bytes:
        return {"exists": True, "path": rel(ctx.root, path), "size_bytes": size, "compacted": False}
    if not dry_run:
        text = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(
            "# Current operator flow\n\n> Compacted by operator memory hygiene; retaining latest events only.\n\n" + text[-max_bytes // 2 :],
            encoding="utf-8",
        )
    return {"exists": True, "path": rel(ctx.root, path), "size_bytes": size, "compacted": True, "dry_run": dry_run}


def _prune_cache_dirs(ctx: BridgeContext, *, max_items: int, dry_run: bool) -> Dict[str, Any]:
    root = ctx.ai_root / "cache"
    removed: list[Dict[str, Any]] = []
    namespaces: list[Dict[str, Any]] = []
    if not root.exists():
        return {"root": rel(ctx.root, root), "namespaces": [], "removed": []}
    for ns in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        files = sorted(ns.glob("*.json"), key=_mtime_key, reverse=True)
        namespaces.append({"namespace": ns.name, "items_before": len(files), "items_after": min(len(files), max_items)})
        for path in files[max_items:]:
            _delete_file(ctx, path, dry_run=dry_run, reason="cache-retention-overflow", out=removed)
        if not dry_run:
            try:
                next(ns.iterdir())
            except StopIteration:
                ns.rmdir()
            except Exception:
                pass
    return {"root": rel(ctx.root, root), "namespaces": namespaces, "removed": removed}


def _prune_scratch(ctx: BridgeContext, *, max_items: int, dry_run: bool) -> Dict[str, Any]:
    root = ctx.ai_root / "scratch"
    removed: list[Dict[str, Any]] = []
    if not root.exists():
        return {"root": rel(ctx.root, root), "items_before": 0, "removed": []}
    files = sorted([p for p in root.glob("*.md") if p.is_file()], key=_mtime_key, reverse=True)
    for path in files[max_items:]:
        _delete_file(ctx, path, dry_run=dry_run, reason="scratch-retention-overflow", out=removed)
    return {"root": rel(ctx.root, root), "items_before": len(files), "items_after": min(len(files), max_items), "removed": removed}


def memory_maintain(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Prune generated operator memory overflow and refresh current state."""

    dry_run = bool(args.get("dry_run", False))
    refresh_current = bool(args.get("refresh_current", True))
    if (not dry_run or refresh_current) and not ctx.write_enabled:
        raise BridgeError("operator memory maintenance requires write mode", "write_disabled")

    max_tasks = max(20, min(int(args.get("max_tasks", 160)), 1000))
    max_knowledge = max(40, min(int(args.get("max_knowledge", 260)), 2000))
    max_notes = max(20, min(int(args.get("max_notes", 160)), 1000))
    max_cache_items = max(10, min(int(args.get("max_cache_items_per_namespace", 50)), 500))
    max_scratch = max(5, min(int(args.get("max_scratch_items", MAX_SCRATCH_ITEMS)), 200))

    current_id = _current_task_id(ctx)
    removed: list[Dict[str, Any]] = []
    task_result = _trim_json_index(
        ctx,
        index_path=_task_index_path(ctx),
        dir_path=_tasks_dir(ctx),
        id_key="task_id",
        max_items=max_tasks,
        keep_ids={current_id} if current_id else set(),
        dry_run=dry_run,
        removed=removed,
        file_reason="task-retention-overflow",
    )
    knowledge_keep_ids: set[str] = {"current-engine-state"}
    current_path = _task_record_path(ctx, current_id) if current_id else None
    if current_path and current_path.exists():
        current = _json_file(current_path, {})
        for item in current.get("knowledge_links", []) if isinstance(current, dict) else []:
            if isinstance(item, dict) and item.get("knowledge_id"):
                knowledge_keep_ids.add(str(item["knowledge_id"]))
    knowledge_result = _trim_json_index(
        ctx,
        index_path=_knowledge_index_path(ctx),
        dir_path=_knowledge_dir(ctx),
        id_key="knowledge_id",
        max_items=max_knowledge,
        keep_ids=knowledge_keep_ids,
        dry_run=dry_run,
        removed=removed,
        file_reason="knowledge-retention-overflow",
    )
    note_result = _trim_json_index(
        ctx,
        index_path=_note_index_path(ctx),
        dir_path=_notes_dir(ctx),
        id_key="digest",
        max_items=max_notes,
        keep_ids=set(),
        dry_run=dry_run,
        removed=removed,
        file_reason="note-retention-overflow",
    )
    flow_result = _compact_current_flow_file(ctx, dry_run=dry_run)
    cache_result = _prune_cache_dirs(ctx, max_items=max_cache_items, dry_run=dry_run)
    scratch_result = _prune_scratch(ctx, max_items=max_scratch, dry_run=dry_run)

    current_state_payload = collect_current_state(ctx, args)
    if refresh_current and not dry_run:
        state_set(ctx, {"namespace": "operator", "key": "engine_current_state", "value": current_state_payload})
        knowledge_update(ctx, {
            "knowledge_id": "current-engine-state",
            "type": "current_state",
            "subject": "Current North Star operator state",
            "summary": "Auto-refreshed compact state snapshot for future Suite/API reasoning.",
            "confidence": "observed",
            "tags": ["operator-memory", "current-state", "auto-refresh"],
            "artifacts": current_state_payload.get("latest_artifacts", []),
            "evidence": current_state_payload,
            "next_actions": ["Read operator.engine_current_state before stale notes", "Run diag.dataset.maturity after dataset index changes"],
        })

    result = {
        "schema": "northstar.operatorMemoryMaintenance.v1",
        "ok": True,
        "dry_run": dry_run,
        "updated_at": now_utc(),
        "retention": {
            "max_tasks": max_tasks,
            "max_knowledge": max_knowledge,
            "max_notes": max_notes,
            "max_cache_items_per_namespace": max_cache_items,
            "max_scratch_items": max_scratch,
        },
        "cleanup": {
            "tasks": task_result,
            "knowledge": knowledge_result,
            "notes": note_result,
            "current_flow": flow_result,
            "cache": cache_result,
            "scratch": scratch_result,
            "removed": removed + cache_result.get("removed", []) + scratch_result.get("removed", []),
        },
        "current_state": current_state_payload,
    }
    if not dry_run:
        state_set(ctx, {"namespace": "operator", "key": "memory_hygiene_last", "value": result})
    return result

__all__ = [
    "_rel_or_none",
    "_delete_file",
    "_trim_json_index",
    "_compact_current_flow_file",
    "_prune_cache_dirs",
    "_prune_scratch",
    "memory_maintain",
]
