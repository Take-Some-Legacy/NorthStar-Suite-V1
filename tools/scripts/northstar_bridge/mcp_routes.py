from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .config_loader import load_config_json
from .http_mounts import HTTP_MOUNTS, operator_get_paths
from .net_address import normalize_http_path, unique_http_paths

BRIDGE_PUBLIC_ORIGIN_CONFIG_NAME = "bridge_public_origin.v1.json"


@dataclass(frozen=True)
class McpRouteProfile:
    """Canonical MCP HTTP route policy.

    Routes are config-driven.  Deployment-specific paths such as /mcp-v2 belong
    to .takesome/config/bridge_public_origin.v1.json or environment overrides,
    not scattered constants.
    """

    endpoint: str = "/mcp"
    discovery_paths: tuple[str, ...] = ("/", "/mcp")
    mcp_paths: tuple[str, ...] = ("/mcp",)
    public_get_paths: tuple[str, ...] = ("/", "/mcp", HTTP_MOUNTS.health, HTTP_MOUNTS.favicon)
    operator_get_paths: tuple[str, ...] = operator_get_paths()
    direct_tool_call_path: str = "/tools/call"


DEFAULT_MCP_ROUTES = McpRouteProfile()


def _route_data_from_config(root: Path, operator_root: Path | None = None) -> dict:
    public = load_config_json(root, BRIDGE_PUBLIC_ORIGIN_CONFIG_NAME, operator_root=operator_root).data
    mcp = public.get("mcp") if isinstance(public.get("mcp"), dict) else {}
    return mcp if isinstance(mcp, dict) else {}


def load_mcp_route_profile(root: Path, operator_root: Path | None = None) -> McpRouteProfile:
    """Load MCP route policy from .takesome/config with legacy fallback."""
    data = _route_data_from_config(root, operator_root)
    endpoint = normalize_http_path(
        os.environ.get("NORTHSTAR_MCP_ENDPOINT_PATH")
        or os.environ.get("NORTHSTAR_PUBLIC_MCP_PATH")
        or data.get("endpoint")
        or data.get("endpoint_path")
        or DEFAULT_MCP_ROUTES.endpoint,
        DEFAULT_MCP_ROUTES.endpoint,
    )
    aliases = unique_http_paths(data.get("aliases") or data.get("mcp_paths") or [])
    mcp_paths = unique_http_paths((endpoint, *aliases)) or (endpoint,)
    discovery_paths = unique_http_paths(data.get("discovery_paths") or ("/", *mcp_paths))
    public_get_paths = unique_http_paths(data.get("public_get_paths") or (*discovery_paths, HTTP_MOUNTS.health, HTTP_MOUNTS.favicon))
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
        direct_tool_call_path=normalize_http_path(data.get("direct_tool_call_path"), DEFAULT_MCP_ROUTES.direct_tool_call_path),
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
