from __future__ import annotations

from dataclasses import dataclass

from .http_mounts import HTTP_MOUNTS, direct_tool_call_paths, operator_get_paths
from typing import Iterable


@dataclass(frozen=True)
class McpRouteProfile:
    """Canonical MCP HTTP route policy.

    Route names live here, not scattered through server.py.  `noauth` and
    experimental aliases are intentionally not part of the default profile.
    """

    endpoint: str = "/mcp"
    # Keep all externally exposed MCP endpoint aliases here.  server.py must
    # not grow hardcoded route branches for cache-bust or OAuth variants.
    discovery_paths: tuple[str, ...] = ("/", "/mcp", "/mcp-v2")
    mcp_paths: tuple[str, ...] = ("/mcp", "/mcp-v2")
    public_get_paths: tuple[str, ...] = ("/", "/mcp", "/mcp-v2", HTTP_MOUNTS.health, HTTP_MOUNTS.favicon)
    operator_get_paths: tuple[str, ...] = operator_get_paths()
    direct_tool_call_path: str = "/tools/call"


DEFAULT_MCP_ROUTES = McpRouteProfile()


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
    if path == "/favicon.ico":
        return "asset"
    if path == "/health":
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
