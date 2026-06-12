from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .http_mounts import HTTP_MOUNTS, direct_tool_call_paths, operator_get_paths

BRIDGE_PUBLIC_ORIGIN_CONFIG_REL = Path("config") / "suite" / "bridge_public_origin.v1.json"


def _normalize_path(value: object, default: str = "/mcp") -> str:
    text = str(value or "").strip()
    if not text:
        text = default
    if not text.startswith("/"):
        text = "/" + text
    if len(text) > 1:
        text = text.rstrip("/")
    return text or default


def _unique_paths(values: Iterable[object]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        path = _normalize_path(value, "")
        if path and path not in out:
            out.append(path)
    return tuple(out)


@dataclass(frozen=True)
class McpRouteProfile:
    """Canonical MCP HTTP route policy.

    Route names are data-driven.  The default profile is intentionally minimal;
    deployment-specific paths such as /mcp-v2 must come from config or env.
    """

    endpoint: str = "/mcp"
    discovery_paths: tuple[str, ...] = ("/", "/mcp")
    mcp_paths: tuple[str, ...] = ("/mcp",)
    public_get_paths: tuple[str, ...] = ("/", "/mcp", HTTP_MOUNTS.health, HTTP_MOUNTS.favicon)
    operator_get_paths: tuple[str, ...] = operator_get_paths()
    direct_tool_call_path: str = "/tools/call"


DEFAULT_MCP_ROUTES = McpRouteProfile()


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _route_data_from_config(root: Path) -> dict:
    public = _read_json(root / BRIDGE_PUBLIC_ORIGIN_CONFIG_REL)
    mcp = public.get("mcp") if isinstance(public.get("mcp"), dict) else {}
    return mcp if isinstance(mcp, dict) else {}


def load_mcp_route_profile(root: Path) -> McpRouteProfile:
    """Load MCP route policy from config with environment override.

    Supported config shape in config/suite/bridge_public_origin.v1.json:
      "mcp": {
        "endpoint": "/mcp-v2",
        "aliases": ["/mcp"],
        "discovery_paths": ["/", "/mcp-v2", "/mcp"],
        "public_get_paths": ["/", "/mcp-v2", "/mcp", "/health", "/favicon.ico"],
        "direct_tool_call_path": "/tools/call"
      }
    """
    data = _route_data_from_config(root)
    endpoint = _normalize_path(
        os.environ.get("NORTHSTAR_MCP_ENDPOINT_PATH")
        or os.environ.get("NORTHSTAR_PUBLIC_MCP_PATH")
        or data.get("endpoint")
        or data.get("endpoint_path")
        or DEFAULT_MCP_ROUTES.endpoint,
        DEFAULT_MCP_ROUTES.endpoint,
    )
    aliases = _unique_paths(data.get("aliases") or data.get("mcp_paths") or [])
    mcp_paths = _unique_paths((endpoint, *aliases)) or (endpoint,)
    discovery_paths = _unique_paths(data.get("discovery_paths") or ("/", *mcp_paths))
    public_get_paths = _unique_paths(data.get("public_get_paths") or (*discovery_paths, HTTP_MOUNTS.health, HTTP_MOUNTS.favicon))
    if HTTP_MOUNTS.health not in public_get_paths:
        public_get_paths = (*public_get_paths, HTTP_MOUNTS.health)
    if HTTP_MOUNTS.favicon not in public_get_paths:
        public_get_paths = (*public_get_paths, HTTP_MOUNTS.favicon)
    return McpRouteProfile(
        endpoint=endpoint,
        discovery_paths=discovery_paths,
        mcp_paths=mcp_paths,
        public_get_paths=public_get_paths,
        operator_get_paths=operator_get_paths(),
        direct_tool_call_path=_normalize_path(data.get("direct_tool_call_path"), DEFAULT_MCP_ROUTES.direct_tool_call_path),
    )


def is_discovery_path(path: str, routes: McpRouteProfile = DEFAULT_MCP_ROUTES) -> bool:
    return path in routes.discovery_paths


def is_mcp_path(path: str, routes: McpRouteProfile = DEFAULT_MCP_ROUTES) -> bool:
    return path in routes.mcp_paths


def is_operator_get_path(path: str, routes: McpRouteProfile = DEFAULT_MCP_ROUTES) -> bool:
    return path in routes.operator_get_paths


def is_direct_tool_call_path(path: str, routes: McpRouteProfile = DEFAULT_MCP_ROUTES) -> bool:
    return path == routes.direct_tool_call_path


def all_head_paths(routes: McpRouteProfile = DEFAULT_MCP_ROUTES) -> set[str]:
    return set(routes.public_get_paths) | set(routes.operator_get_paths) | {routes.direct_tool_call_path}


def route_label(path: str, routes: McpRouteProfile = DEFAULT_MCP_ROUTES) -> str:
    if path == HTTP_MOUNTS.favicon:
        return "asset"
    if path == HTTP_MOUNTS.health:
        return "health"
    if is_mcp_path(path, routes) or is_discovery_path(path, routes):
        return "mcp"
    if is_direct_tool_call_path(path, routes):
        return "tool-call"
    if path.startswith("/tools"):
        return "tools"
    if path.startswith("/dataset"):
        return "dataset"
    if path.startswith("/logs"):
        return "logs"
    if path.startswith("/status"):
        return "status"
    if path.startswith("/.well-known") or path.startswith("/oauth"):
        return "oauth"
    return "http"
