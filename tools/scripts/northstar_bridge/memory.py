from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from .contracts import BridgeContext, BridgeError, MAX_READ_BYTES_DEFAULT, now_utc
from .paths import read_text_file, rel, slug

MAX_NOTE_BODY_CHARS = 16_000
MAX_FLOW_BYTES = 96 * 1024
MAX_INDEX_ITEMS = 240
MAX_CACHE_ITEMS_PER_NAMESPACE = 80
MAX_CACHE_VALUE_CHARS = 48_000
MAX_STATE_VALUE_CHARS = 64_000
SECRET_KEY_PARTS = ("key", "token", "secret", "password", "authorization", "credential")


def _json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _digest(value: Any) -> str:
    text = json.dumps(_sanitize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(part in key_text.lower() for part in SECRET_KEY_PARTS):
                out[key_text] = "***"
            else:
                out[key_text] = _sanitize(item)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:80]] + (["…"] if len(value) > 80 else [])
    if isinstance(value, str) and len(value) > MAX_CACHE_VALUE_CHARS:
        return value[:MAX_CACHE_VALUE_CHARS] + "…"
    return value


def _compact(value: Any, max_chars: int) -> Any:
    safe = _sanitize(value)
    text = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text) <= max_chars:
        return safe
    return {"_truncated": True, "_digest": _digest(safe), "preview": text[:max_chars] + "…"}


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

# ---------------------------------------------------------------------------
# Persistent task memory / project knowledge
# ---------------------------------------------------------------------------
# This layer is intentionally stored under .takesome/ai-bridge generated state.
# It is not source code and not an engine runtime dependency. It gives the Suite
# a durable memory of requested work, current state, decisions, findings and
# artifact links so future AI/API calls can reason from structured state instead
# of stale console scrollback.

MAX_TASK_ITEMS = 300
MAX_TASK_EVENTS = 160
MAX_KNOWLEDGE_ITEMS = 500
MAX_KNOWLEDGE_TEXT_CHARS = 24_000


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

# ---------------------------------------------------------------------------
# Operator memory hygiene / current-state refresh
# ---------------------------------------------------------------------------
# The memory layer must not grow forever. These maintenance tools keep generated
# operator memory bounded, keep current task/state authoritative, and refresh a
# compact knowledge record that future model/API calls can trust before reading
# older notes.

MAX_SCRATCH_ITEMS = 40


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


def _rel_or_none(ctx: BridgeContext, path: Path | None) -> str | None:
    return rel(ctx.root, path) if path is not None and path.exists() else None


def _count_json_files(path: Path) -> int:
    return len(list(path.glob("*.json"))) if path.exists() else 0


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
