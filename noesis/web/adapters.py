from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .contract import WebRequest, WebResponse, json_response, noesis_web_headers, not_found, surface_metadata

WEB_SERVER_NAME = "noesis.webServer"
WEB_SERVER_TITLE = "NOESIS Web Server"
WEB_ADAPTER_CONTRACT = "noesis.web.adapter.v1"
WEB_SERVER_CONTRACT = "noesis.web.server.v1"


@dataclass(frozen=True)
class WebAdapterSpec:
    """Declarative adapter contract for a NOESIS web surface.

    The web server owns HTTP mechanics. Adapters own policy, routes and
    application semantics. Dashboard, /mcp and /mcp-v2 must therefore be
    modeled as adapters, not as independent ad-hoc server implementations.
    """

    adapter_id: str
    surface: str
    title: str
    mount_paths: tuple[str, ...]
    routes: tuple[str, ...]
    policy: str
    contract: str = WEB_ADAPTER_CONTRACT
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def normalized_mounts(self) -> tuple[str, ...]:
        mounts: list[str] = []
        for raw in self.mount_paths:
            path = normalize_path(raw)
            mounts.append(path)
        # Longest prefix first, so /api/runs wins over /.
        return tuple(sorted(dict.fromkeys(mounts), key=len, reverse=True))

    def as_dict(self, *, root: Path | None = None) -> dict[str, Any]:
        return {
            "schema": "noesis.web.adapter.spec.v1",
            "adapterId": self.adapter_id,
            "surface": self.surface,
            "title": self.title,
            "contract": self.contract,
            "serverContract": WEB_SERVER_CONTRACT,
            "mountPaths": list(self.normalized_mounts()),
            "routes": list(self.routes),
            "policy": self.policy,
            "description": self.description,
            "root": str(root) if root else "",
            "metadata": dict(self.metadata),
        }


class WebAdapter(Protocol):
    spec: WebAdapterSpec

    def can_handle(self, request: WebRequest) -> bool:
        ...

    def handle(self, request: WebRequest) -> WebResponse:
        ...


def normalize_path(path: str) -> str:
    value = str(path or "/").strip()
    if not value.startswith("/"):
        value = "/" + value
    if len(value) > 1:
        value = value.rstrip("/")
    return value or "/"


def path_matches(path: str, mounts: Iterable[str]) -> bool:
    normalized = normalize_path(path)
    for mount in mounts:
        candidate = normalize_path(mount)
        if candidate == "/":
            return True
        if normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


class PathMountedAdapter:
    """Convenience base for adapters mounted by path/prefix."""

    spec: WebAdapterSpec

    def can_handle(self, request: WebRequest) -> bool:
        return path_matches(request.path, self.spec.normalized_mounts())


class WebServerApp:
    """Router application served by noesis.web.server.

    This is the canonical runtime shape:
        webServer -> adapters[] -> application-specific policy.
    """

    name = WEB_SERVER_NAME
    title = WEB_SERVER_TITLE

    def __init__(self, *, root: Path, adapters: Iterable[WebAdapter], title: str = WEB_SERVER_TITLE, name: str = WEB_SERVER_NAME) -> None:
        self.root = root
        self.title = title
        self.name = name
        self.adapters = list(adapters)

    def handle(self, request: WebRequest) -> WebResponse:
        path = normalize_path(request.path)
        if path in {"/api/web/health", "/api/web/contract"}:
            return json_response(self.metadata())
        adapter = self.match(request)
        if adapter is None:
            return not_found(path)
        response = adapter.handle(request)
        response.headers.setdefault("X-Noesis-Web-Server", self.name)
        response.headers.setdefault("X-Noesis-Web-Adapter", adapter.spec.adapter_id)
        response.headers.setdefault("X-Noesis-Web-Surface", adapter.spec.surface)
        response.headers.setdefault("X-Noesis-Web-Adapter-Contract", adapter.spec.contract)
        return response

    def match(self, request: WebRequest) -> WebAdapter | None:
        candidates: list[tuple[int, WebAdapter]] = []
        for adapter in self.adapters:
            if adapter.can_handle(request):
                longest = max((len(mount) for mount in adapter.spec.normalized_mounts()), default=0)
                candidates.append((longest, adapter))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def metadata(self) -> dict[str, Any]:
        return {
            "ok": True,
            "schema": "noesis.web.server.metadata.v1",
            "title": self.title,
            "server": self.name,
            "contract": WEB_SERVER_CONTRACT,
            "web": surface_metadata(
                title=self.title,
                surface=self.name,
                root=self.root,
                routes=["/api/web/health", "/api/web/contract"],
            ),
            "adapters": [adapter.spec.as_dict(root=self.root) for adapter in self.adapters],
        }


def web_server_headers(*, title: str, surface: str, adapter_id: str = "") -> dict[str, str]:
    headers = noesis_web_headers(title=title, surface=surface)
    headers["X-Noesis-Web-Server"] = WEB_SERVER_NAME
    headers["X-Noesis-Web-Server-Contract"] = WEB_SERVER_CONTRACT
    if adapter_id:
        headers["X-Noesis-Web-Adapter"] = adapter_id
        headers["X-Noesis-Web-Adapter-Contract"] = WEB_ADAPTER_CONTRACT
    return headers
