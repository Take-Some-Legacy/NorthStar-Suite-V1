from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import parse_qs


@dataclass(frozen=True)
class WebRequest:
    """Transport-neutral request object used by local NOESIS web surfaces.

    /mcp, /mcp-v2 and dashboard are different applications. They should not
    copy HTTP boilerplate. Each surface receives a WebRequest and returns a
    WebResponse, while it keeps its own security/routing rules.
    """

    method: str
    path: str
    query: Mapping[str, list[str]]
    headers: Mapping[str, str]
    body: bytes = b""
    root: Path | None = None

    def first_query(self, key: str, default: str = "") -> str:
        values = self.query.get(key) or []
        return values[0] if values else default

    def json_body(self) -> Any:
        if not self.body:
            return {}
        return json.loads(self.body.decode("utf-8", errors="replace"))


@dataclass(frozen=True)
class WebResponse:
    status: int = 200
    body: bytes = b""
    content_type: str = "application/octet-stream"
    headers: dict[str, str] = field(default_factory=dict)


class WebSurface(Protocol):
    title: str
    name: str

    def handle(self, request: WebRequest) -> WebResponse:
        ...


def encode_json(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def json_response(payload: Any, *, status: int = 200, headers: Mapping[str, str] | None = None) -> WebResponse:
    return WebResponse(
        status=status,
        body=encode_json(payload),
        content_type="application/json; charset=utf-8",
        headers=dict(headers or {}),
    )


def html_response(html: str, *, status: int = 200, headers: Mapping[str, str] | None = None) -> WebResponse:
    return WebResponse(
        status=status,
        body=html.encode("utf-8"),
        content_type="text/html; charset=utf-8",
        headers=dict(headers or {}),
    )


def text_response(text: str, *, status: int = 200, content_type: str = "text/plain; charset=utf-8", headers: Mapping[str, str] | None = None) -> WebResponse:
    return WebResponse(
        status=status,
        body=text.encode("utf-8"),
        content_type=content_type,
        headers=dict(headers or {}),
    )


def bytes_response(data: bytes, *, status: int = 200, content_type: str = "application/octet-stream", headers: Mapping[str, str] | None = None) -> WebResponse:
    return WebResponse(status=status, body=data, content_type=content_type, headers=dict(headers or {}))


def not_found(path: str) -> WebResponse:
    return json_response({"ok": False, "error": "not_found", "path": path}, status=404)


def parse_query(query_string: str) -> dict[str, list[str]]:
    return {key: [str(item) for item in values] for key, values in parse_qs(query_string, keep_blank_values=True).items()}


def noesis_web_headers(*, title: str, surface: str, cache_control: str = "no-store") -> dict[str, str]:
    return {
        "Cache-Control": cache_control,
        "X-Noesis-Title": title,
        "X-Noesis-Web-Surface": surface,
        "X-Noesis-Web-Contract": "noesis.web.v1",
    }


def surface_metadata(*, title: str, surface: str, routes: list[str], root: Path | None = None) -> dict[str, Any]:
    return {
        "schema": "noesis.web.surface.v1",
        "title": title,
        "surface": surface,
        "contract": "noesis.web.v1",
        "root": str(root) if root else "",
        "routes": routes,
    }
