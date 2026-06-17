from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

from .contracts import BridgeContext, BridgeError, MAX_READ_BYTES_DEFAULT, now_utc
from .paths import read_text_file, rel, slug
from .memory_schema import *


def _json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _notes_dir(ctx: BridgeContext) -> Path:
    path = ctx.ai_root / "notes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _note_index_path(ctx: BridgeContext) -> Path:
    return _notes_dir(ctx) / "index.json"


def _load_note_index(ctx: BridgeContext) -> Dict[str, Any]:
    data = _json_file(_note_index_path(ctx), {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema", "northstar.operatorNotes.v2")
    data.setdefault("items", [])
    return data


def _write_note_index(ctx: BridgeContext, data: Dict[str, Any]) -> None:
    items = list(data.get("items", []))[:MAX_INDEX_ITEMS]
    data["items"] = items
    data["updated_at"] = now_utc()
    _write_json(_note_index_path(ctx), data)


def _append_current_flow(ctx: BridgeContext, entry: Dict[str, Any]) -> Path:
    notes = _notes_dir(ctx)
    current = notes / "current-flow.md"
    line = (
        f"- `{entry.get('updated_at') or entry.get('created_at')}` "
        f"phase=`{entry.get('phase', '')}` task=`{entry.get('task_id', '')}` "
        f"title={entry.get('title', '')!r} digest=`{entry.get('digest', '')}` "
        f"status={entry.get('status', 'recorded')} seen={entry.get('seen_count', 1)}\n"
    )
    if current.exists() and current.stat().st_size > MAX_FLOW_BYTES:
        text = current.read_text(encoding="utf-8", errors="replace")
        current.write_text("# Current operator flow\n\n> Compacted; retaining latest events only.\n\n" + text[-MAX_FLOW_BYTES // 2 :], encoding="utf-8")
    if not current.exists():
        current.write_text("# Current operator flow\n\n", encoding="utf-8")
    with current.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return current


def _write_note_file(ctx: BridgeContext, title: str, body: str, args: Dict[str, Any], digest: str) -> Path:
    notes = _notes_dir(ctx)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = notes / f"{stamp}-{slug(title)}-{digest}.md"
    tags = args.get("tags") or []
    tag_text = ", ".join(str(x) for x in tags) if isinstance(tags, list) else str(tags)
    if len(body) > MAX_NOTE_BODY_CHARS:
        body = body[:MAX_NOTE_BODY_CHARS] + "\n\n… truncated by operator memory hygiene …"
    content = (
        f"# {title}\n\n"
        f"- created_at: {now_utc()}\n"
        f"- task_id: {args.get('task_id', '')}\n"
        f"- phase: {args.get('phase', '')}\n"
        f"- tags: {tag_text}\n"
        f"- digest: {digest}\n\n"
        f"{body.rstrip()}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def note_append(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    title = str(args.get("title") or args.get("phase") or "operator-note")
    body = str(args.get("note") or args.get("content") or "")
    if not body.strip():
        raise BridgeError("note/content is empty", "invalid_note")
    task_id = str(args.get("task_id", ""))
    phase = str(args.get("phase", ""))
    digest = _digest({"title": title, "task_id": task_id, "phase": phase, "body": body})
    index = _load_note_index(ctx)
    items: List[Dict[str, Any]] = list(index.get("items", []))
    existing = next((item for item in items if item.get("digest") == digest), None)
    if existing:
        existing["last_seen_at"] = now_utc()
        existing["seen_count"] = int(existing.get("seen_count", 1)) + 1
        existing["status"] = "duplicate_suppressed"
        items = [existing, *[item for item in items if item.get("digest") != digest]]
        index["items"] = items
        _write_note_index(ctx, index)
        current = _append_current_flow(ctx, existing)
        return {"ok": True, "deduplicated": True, "path": existing.get("path"), "current_flow": rel(ctx.root, current), "digest": digest, "seen_count": existing["seen_count"]}

    path = _write_note_file(ctx, title, body, args, digest)
    entry = {
        "title": title,
        "task_id": task_id,
        "phase": phase,
        "tags": args.get("tags") or [],
        "digest": digest,
        "path": rel(ctx.root, path),
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "seen_count": 1,
        "status": "recorded",
        "preview": body.strip().replace("\r", " ").replace("\n", " ")[:280],
    }
    index["items"] = [entry, *items][:MAX_INDEX_ITEMS]
    _write_note_index(ctx, index)
    current = _append_current_flow(ctx, entry)
    return {"ok": True, "deduplicated": False, "path": rel(ctx.root, path), "current_flow": rel(ctx.root, current), "digest": digest}


def note_read(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 10)), 100))
    max_bytes = int(args.get("max_bytes", 32 * 1024))
    notes = _notes_dir(ctx)
    index = _load_note_index(ctx)
    items = list(index.get("items", []))[:limit]
    include_content = bool(args.get("include_content", True))
    out: List[Dict[str, Any]] = []
    for item in items:
        row = dict(item)
        path_text = item.get("path")
        path = ctx.root / str(path_text) if path_text else None
        if include_content and path and path.exists():
            text, truncated, size = read_text_file(path, max_bytes)
            row.update({"size_bytes": size, "truncated": truncated, "content": text})
        out.append(row)
    current = notes / "current-flow.md"
    return {"notes": out, "index_path": rel(ctx.root, _note_index_path(ctx)), "current_flow_path": rel(ctx.root, current) if current.exists() else None, "current_flow_exists": current.exists(), "total_indexed": len(index.get("items", []))}


def _state_path(ctx: BridgeContext, namespace: str) -> Path:
    return ctx.ai_root / "state" / f"{slug(namespace, 'operator')}.json"


def state_get(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    namespace = str(args.get("namespace", "operator"))
    key = str(args.get("key", ""))
    path = _state_path(ctx, namespace)
    data = _json_file(path, {})
    return {"namespace": namespace, "key": key or None, "value": data.get(key) if key else data, "path": rel(ctx.root, path)}


def state_set(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("operator state writes require write mode", "write_disabled")
    namespace = str(args.get("namespace", "operator"))
    key = str(args.get("key", "")).strip()
    if not key:
        raise BridgeError("state key is empty", "invalid_key")
    path = _state_path(ctx, namespace)
    data = _json_file(path, {})
    value = _compact(args.get("value"), MAX_STATE_VALUE_CHARS)
    digest = _digest(value)
    old = data.get(key)
    old_digest = old.get("_digest") if isinstance(old, dict) else _digest(old) if old is not None else ""
    data[key] = {"updated_at": now_utc(), "_digest": digest, "value": value}
    data["_updated_at"] = now_utc()
    data["_schema"] = "northstar.operatorState.v2"
    _write_json(path, data)
    return {"ok": True, "namespace": namespace, "key": key, "path": rel(ctx.root, path), "changed": digest != old_digest, "digest": digest}


def _cache_dir(ctx: BridgeContext, namespace: str) -> Path:
    return ctx.ai_root / "cache" / slug(namespace, "default")


def _cache_path(ctx: BridgeContext, namespace: str, key: str) -> Path:
    return _cache_dir(ctx, namespace) / f"{slug(key, 'item')}.json"


def _prune_cache(namespace_dir: Path) -> None:
    files = sorted(namespace_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[MAX_CACHE_ITEMS_PER_NAMESPACE:]:
        try:
            path.unlink()
        except Exception:
            pass


def cache_get(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    path = _cache_path(ctx, str(args.get("namespace", "default")), str(args.get("key", "item")))
    return {"exists": path.exists(), "path": rel(ctx.root, path), "value": _json_file(path, None) if path.exists() else None}


def cache_set(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("operator cache writes require write mode", "write_disabled")
    namespace = str(args.get("namespace", "default"))
    key = str(args.get("key", "item"))
    path = _cache_path(ctx, namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = _compact(args.get("value"), MAX_CACHE_VALUE_CHARS)
    digest = _digest(value)
    old = _json_file(path, {}) if path.exists() else {}
    if isinstance(old, dict) and old.get("digest") == digest:
        return {"ok": True, "unchanged": True, "path": rel(ctx.root, path), "digest": digest}
    payload = {"schema": "northstar.operatorCache.v2", "updated_at": now_utc(), "digest": digest, "value": value}
    _write_json(path, payload)
    _prune_cache(path.parent)
    return {"ok": True, "unchanged": False, "path": rel(ctx.root, path), "digest": digest}


def _scratch_path(ctx: BridgeContext, name: str) -> Path:
    return ctx.ai_root / "scratch" / f"{slug(name, 'scratch')}.md"


def scratch_write(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("scratch writes require write mode", "write_disabled")
    path = _scratch_path(ctx, str(args.get("name", "scratch")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(args.get("content", "")), encoding="utf-8")
    return {"ok": True, "path": rel(ctx.root, path)}


def scratch_read(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    path = _scratch_path(ctx, str(args.get("name", "scratch")))
    if not path.exists():
        return {"exists": False, "path": rel(ctx.root, path)}
    text, truncated, size = read_text_file(path, int(args.get("max_bytes", MAX_READ_BYTES_DEFAULT)))
    return {"exists": True, "path": rel(ctx.root, path), "size_bytes": size, "truncated": truncated, "content": text}


def _tasks_dir(ctx: BridgeContext) -> Path:
    path = ctx.ai_root / "tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _task_index_path(ctx: BridgeContext) -> Path:
    return _tasks_dir(ctx) / "index.json"


def _task_record_path(ctx: BridgeContext, task_id: str) -> Path:
    return _tasks_dir(ctx) / f"{slug(task_id, 'task')}.json"


def _knowledge_dir(ctx: BridgeContext) -> Path:
    path = ctx.ai_root / "knowledge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _knowledge_index_path(ctx: BridgeContext) -> Path:
    return _knowledge_dir(ctx) / "index.json"


def _current_task_id(ctx: BridgeContext) -> str:
    state = _json_file(_state_path(ctx, "operator"), {})
    current = state.get("current_task") if isinstance(state, dict) else None
    if isinstance(current, dict):
        value = current.get("value") if isinstance(current.get("value"), dict) else current
        task_id = str(value.get("task_id") or value.get("id") or "").strip()
        if task_id:
            return task_id
    return ""


def _load_task_index(ctx: BridgeContext) -> Dict[str, Any]:
    data = _json_file(_task_index_path(ctx), {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema", "northstar.operatorTaskIndex.v1")
    data.setdefault("items", [])
    return data


def _write_task_index(ctx: BridgeContext, data: Dict[str, Any]) -> None:
    items = list(data.get("items", []))[:MAX_TASK_ITEMS]
    data["items"] = items
    data["updated_at"] = now_utc()
    _write_json(_task_index_path(ctx), data)


def _task_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": record.get("task_id"),
        "title": record.get("title"),
        "status": record.get("status"),
        "phase": record.get("phase"),
        "priority": record.get("priority"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "tags": record.get("tags") or [],
        "knowledge_count": len(record.get("knowledge_links") or []),
        "artifact_count": len(record.get("artifacts") or []),
        "event_count": len(record.get("events") or []),
        "path": record.get("path"),
    }


def task_record(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Create or refresh a durable task record for the current operator job."""

    if not ctx.write_enabled:
        raise BridgeError("operator task writes require write mode", "write_disabled")
    title = str(args.get("title") or args.get("task") or args.get("intent") or "North Star task").strip()
    raw_task_id = str(args.get("task_id") or args.get("id") or "").strip()
    task_id = raw_task_id or f"{slug(title, 'task')}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    path = _task_record_path(ctx, task_id)
    existing = _json_file(path, {}) if path.exists() else {}
    if not isinstance(existing, dict):
        existing = {}
    created_at = existing.get("created_at") or now_utc()
    record = {
        **existing,
        "schema": "northstar.operatorTask.v1",
        "task_id": task_id,
        "title": title,
        "intent": str(args.get("intent") or args.get("task") or title),
        "source": str(args.get("source") or "operator"),
        "status": str(args.get("status") or existing.get("status") or "running"),
        "phase": str(args.get("phase") or existing.get("phase") or "start"),
        "priority": str(args.get("priority") or existing.get("priority") or "normal"),
        "tags": list(args.get("tags") or existing.get("tags") or []),
        "created_at": created_at,
        "updated_at": now_utc(),
        "path": rel(ctx.root, path),
        "constraints": _compact(args.get("constraints") or existing.get("constraints") or {}, MAX_KNOWLEDGE_TEXT_CHARS),
        "requested_output": _compact(args.get("requested_output") or existing.get("requested_output") or {}, MAX_KNOWLEDGE_TEXT_CHARS),
        "state_snapshot": _compact(args.get("state_snapshot") or existing.get("state_snapshot") or {}, MAX_KNOWLEDGE_TEXT_CHARS),
        "artifacts": list(existing.get("artifacts") or []),
        "knowledge_links": list(existing.get("knowledge_links") or []),
        "events": list(existing.get("events") or []),
    }
    event = {
        "at": now_utc(),
        "type": "task.recorded" if not existing else "task.refreshed",
        "status": record["status"],
        "phase": record["phase"],
        "summary": str(args.get("summary") or "task record updated")[:1000],
    }
    record["events"] = [event, *record["events"]][:MAX_TASK_EVENTS]
    _write_json(path, record)

    index = _load_task_index(ctx)
    items = [item for item in list(index.get("items", [])) if item.get("task_id") != task_id]
    index["items"] = [_task_summary(record), *items]
    _write_task_index(ctx, index)

    state_set(ctx, {"namespace": "operator", "key": "current_task", "value": _task_summary(record)})
    _append_current_flow(ctx, {**_task_summary(record), "title": title, "task_id": task_id, "phase": record["phase"], "digest": _digest(record), "status": record["status"], "updated_at": now_utc()})
    return {"ok": True, "task_id": task_id, "path": rel(ctx.root, path), "status": record["status"], "phase": record["phase"]}


def task_update(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Append a structured event and state delta to a task record."""

    if not ctx.write_enabled:
        raise BridgeError("operator task writes require write mode", "write_disabled")
    task_id = str(args.get("task_id") or _current_task_id(ctx)).strip()
    if not task_id:
        raise BridgeError("task_id is empty and no current task is recorded", "invalid_task")
    path = _task_record_path(ctx, task_id)
    record = _json_file(path, {}) if path.exists() else {}
    if not isinstance(record, dict) or not record:
        record = {
            "schema": "northstar.operatorTask.v1",
            "task_id": task_id,
            "title": str(args.get("title") or task_id),
            "intent": str(args.get("intent") or ""),
            "source": "operator",
            "created_at": now_utc(),
            "events": [],
            "artifacts": [],
            "knowledge_links": [],
            "tags": [],
        }
    status = str(args.get("status") or record.get("status") or "running")
    phase = str(args.get("phase") or record.get("phase") or "update")
    event = {
        "at": now_utc(),
        "type": str(args.get("event_type") or "task.update"),
        "status": status,
        "phase": phase,
        "summary": str(args.get("summary") or "")[:2000],
        "diagnostics": _compact(args.get("diagnostics") or [], MAX_KNOWLEDGE_TEXT_CHARS),
        "next_actions": _compact(args.get("next_actions") or [], MAX_KNOWLEDGE_TEXT_CHARS),
        "state_delta": _compact(args.get("state_delta") or args.get("engine_state_delta") or {}, MAX_KNOWLEDGE_TEXT_CHARS),
    }
    record["status"] = status
    record["phase"] = phase
    record["updated_at"] = now_utc()
    record["events"] = [event, *list(record.get("events") or [])][:MAX_TASK_EVENTS]
    if args.get("artifacts"):
        record["artifacts"] = list(args.get("artifacts") or []) + list(record.get("artifacts") or [])
        record["artifacts"] = record["artifacts"][:80]
    if args.get("knowledge_links"):
        record["knowledge_links"] = list(args.get("knowledge_links") or []) + list(record.get("knowledge_links") or [])
        record["knowledge_links"] = record["knowledge_links"][:120]
    record["path"] = rel(ctx.root, path)
    _write_json(path, record)

    index = _load_task_index(ctx)
    items = [item for item in list(index.get("items", [])) if item.get("task_id") != task_id]
    index["items"] = [_task_summary(record), *items]
    _write_task_index(ctx, index)
    state_set(ctx, {"namespace": "operator", "key": "current_task", "value": _task_summary(record)})
    state_set(ctx, {"namespace": "operator", "key": "last_task_event", "value": {"task_id": task_id, **event}})
    return {"ok": True, "task_id": task_id, "path": rel(ctx.root, path), "event": event}


def knowledge_update(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Record a durable project knowledge item linked to tasks/artifacts."""

    if not ctx.write_enabled:
        raise BridgeError("operator knowledge writes require write mode", "write_disabled")
    subject = str(args.get("subject") or args.get("title") or "North Star knowledge").strip()
    entry_type = str(args.get("type") or args.get("entry_type") or "finding").strip()
    summary = str(args.get("summary") or args.get("content") or "").strip()
    if not subject and not summary:
        raise BridgeError("knowledge subject/summary is empty", "invalid_knowledge")
    task_id = str(args.get("task_id") or _current_task_id(ctx)).strip()
    payload = {
        "schema": "northstar.operatorKnowledge.v1",
        "knowledge_id": str(args.get("knowledge_id") or ""),
        "type": entry_type,
        "subject": subject,
        "summary": summary[:MAX_KNOWLEDGE_TEXT_CHARS],
        "confidence": str(args.get("confidence") or "observed"),
        "task_id": task_id,
        "tags": list(args.get("tags") or []),
        "engine_domains": list(args.get("engine_domains") or []),
        "artifacts": list(args.get("artifacts") or []),
        "evidence": _compact(args.get("evidence") or [], MAX_KNOWLEDGE_TEXT_CHARS),
        "next_actions": _compact(args.get("next_actions") or [], MAX_KNOWLEDGE_TEXT_CHARS),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    digest = _digest(payload)
    payload["knowledge_id"] = payload["knowledge_id"] or f"{slug(subject or entry_type, 'knowledge')}-{digest}"
    path = _knowledge_dir(ctx) / f"{slug(payload['knowledge_id'], 'knowledge')}.json"
    payload["path"] = rel(ctx.root, path)
    _write_json(path, payload)

    index = _json_file(_knowledge_index_path(ctx), {})
    if not isinstance(index, dict):
        index = {}
    index.setdefault("schema", "northstar.operatorKnowledgeIndex.v1")
    items = [item for item in list(index.get("items", [])) if item.get("knowledge_id") != payload["knowledge_id"]]
    summary_row = {
        "knowledge_id": payload["knowledge_id"],
        "type": entry_type,
        "subject": subject,
        "summary": summary[:500],
        "confidence": payload["confidence"],
        "task_id": task_id,
        "tags": payload["tags"],
        "engine_domains": payload["engine_domains"],
        "path": payload["path"],
        "updated_at": payload["updated_at"],
    }
    index["items"] = [summary_row, *items][:MAX_KNOWLEDGE_ITEMS]
    index["updated_at"] = now_utc()
    _write_json(_knowledge_index_path(ctx), index)
    if task_id:
        try:
            task_update(ctx, {"task_id": task_id, "phase": "knowledge", "summary": f"knowledge recorded: {subject}", "knowledge_links": [summary_row]})
        except Exception:
            pass
    state_set(ctx, {"namespace": "operator", "key": "engine_knowledge_last", "value": summary_row})
    return {"ok": True, "knowledge_id": payload["knowledge_id"], "path": payload["path"], "task_id": task_id}


def knowledge_read(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 20)), 100))
    index = _json_file(_knowledge_index_path(ctx), {})
    if not isinstance(index, dict):
        index = {"schema": "northstar.operatorKnowledgeIndex.v1", "items": []}
    items = list(index.get("items", []))[:limit]
    return {"index_path": rel(ctx.root, _knowledge_index_path(ctx)), "total_indexed": len(index.get("items", [])), "items": items}


def task_snapshot(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 10)), 80))
    include_events = bool(args.get("include_events", False))
    index = _load_task_index(ctx)
    items = list(index.get("items", []))[:limit]
    current_id = _current_task_id(ctx)
    current_record: Any = None
    if current_id:
        current_path = _task_record_path(ctx, current_id)
        if current_path.exists():
            current_record = _json_file(current_path, {})
            if isinstance(current_record, dict) and not include_events:
                current_record = {k: v for k, v in current_record.items() if k != "events"}
    return {
        "schema": "northstar.operatorTaskSnapshot.v1",
        "task_index": rel(ctx.root, _task_index_path(ctx)),
        "total_tasks": len(index.get("items", [])),
        "current_task_id": current_id or None,
        "current_task": current_record,
        "recent_tasks": items,
        "knowledge": knowledge_read(ctx, {"limit": args.get("knowledge_limit", 10)}),
    }

__all__ = [
    "_json_file",
    "_write_json",
    "_notes_dir",
    "_note_index_path",
    "_load_note_index",
    "_write_note_index",
    "_append_current_flow",
    "_write_note_file",
    "note_append",
    "note_read",
    "_state_path",
    "state_get",
    "state_set",
    "_cache_dir",
    "_cache_path",
    "_prune_cache",
    "cache_get",
    "cache_set",
    "_scratch_path",
    "scratch_write",
    "scratch_read",
    "_tasks_dir",
    "_task_index_path",
    "_task_record_path",
    "_knowledge_dir",
    "_knowledge_index_path",
    "_current_task_id",
    "_load_task_index",
    "_write_task_index",
    "_task_summary",
    "task_record",
    "task_update",
    "knowledge_update",
    "knowledge_read",
    "task_snapshot",
]
