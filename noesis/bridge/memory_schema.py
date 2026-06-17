from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

MAX_NOTE_BODY_CHARS = 16_000
MAX_FLOW_BYTES = 96 * 1024
MAX_INDEX_ITEMS = 240
MAX_CACHE_ITEMS_PER_NAMESPACE = 80
MAX_SCRATCH_ITEMS = 40
MAX_CACHE_VALUE_CHARS = 48_000
MAX_STATE_VALUE_CHARS = 64_000
MAX_TASK_ITEMS = 300
MAX_TASK_EVENTS = 160
MAX_KNOWLEDGE_ITEMS = 500
MAX_KNOWLEDGE_TEXT_CHARS = 24_000
SECRET_KEY_PARTS = ("key", "token", "secret", "password", "authorization", "credential")


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

__all__ = [
    "MAX_NOTE_BODY_CHARS",
    "MAX_FLOW_BYTES",
    "MAX_INDEX_ITEMS",
    "MAX_CACHE_ITEMS_PER_NAMESPACE",
    "MAX_SCRATCH_ITEMS",
    "MAX_CACHE_VALUE_CHARS",
    "MAX_STATE_VALUE_CHARS",
    "MAX_KNOWLEDGE_TEXT_CHARS",
    "MAX_KNOWLEDGE_ITEMS",
    "MAX_TASK_EVENTS",
    "MAX_TASK_ITEMS",
    "SECRET_KEY_PARTS",
    "_digest",
    "_sanitize",
    "_compact",
]
