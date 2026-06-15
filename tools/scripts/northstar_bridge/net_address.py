from __future__ import annotations

import re
from urllib.parse import urlparse

TRUE_VALUES = {"1", "true", "yes", "y", "on", "enabled"}
FALSE_VALUES = {"0", "false", "no", "n", "off", "disabled"}


def text(value: object) -> str:
    return str(value or "").strip()


def slug_id(value: object, default: str, *, limit: int = 80) -> str:
    raw = text(value)
    if not raw:
        return default
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-._")
    return slug[:limit] or default


def split_csv(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(text(item) for item in value if text(item))
    raw = text(value)
    return tuple(part.strip() for part in raw.split(",") if part.strip()) if raw else ()


def truthy(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    raw = text(value).lower()
    if not raw:
        return default
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    return default


def normalize_port(value: object, default: int, *, allow_zero: bool = False) -> int:
    try:
        port = int(text(value))
        low = 0 if allow_zero else 1
        if low <= port <= 65535:
            return port
    except Exception:
        pass
    return default


def normalize_origin(value: object) -> str:
    raw = text(value).rstrip("/")
    if not raw or "://" not in raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw


def normalize_http_path(value: object, default: str = "/") -> str:
    raw = text(value) or default
    if not raw:
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") if len(raw) > 1 else raw


def unique_http_paths(values: object) -> tuple[str, ...]:
    items = values if isinstance(values, (list, tuple)) else split_csv(values)
    out: list[str] = []
    for value in items:
        path = normalize_http_path(value, "")
        if path and path not in out:
            out.append(path)
    return tuple(out)


def join_origin_path(origin: object, path: object, *, default_path: str = "/") -> str:
    base = normalize_origin(origin)
    if not base:
        return ""
    return base.rstrip("/") + normalize_http_path(path, default_path)


def local_http_origin(host: object, port: object, *, default_port: int) -> str:
    raw_host = text(host) or "127.0.0.1"
    if raw_host in {"0.0.0.0", "::"}:
        raw_host = "127.0.0.1"
    if ":" in raw_host and not raw_host.startswith("["):
        raw_host = f"[{raw_host}]"
    return f"http://{raw_host}:{normalize_port(port, default_port)}"


__all__ = [
    "join_origin_path",
    "local_http_origin",
    "normalize_http_path",
    "normalize_origin",
    "normalize_port",
    "slug_id",
    "split_csv",
    "text",
    "truthy",
    "unique_http_paths",
]
