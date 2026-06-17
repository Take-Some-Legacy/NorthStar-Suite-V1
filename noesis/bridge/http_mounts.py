from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HttpMounts:
    # Common transport mounts.
    health: str = "/health"
    status: str = "/status"
    favicon: str = "/favicon.ico"

    # MCP bridge mounts.
    tools: str = "/tools"
    direct_tool_call: str = "/tools/call"
    dataset: str = "/dataset"
    logs: str = "/logs"
    oauth_register: str = "/oauth/register"
    oauth_authorize: str = "/oauth/authorize"
    oauth_token: str = "/oauth/token"

    # Operator dashboard mounts. Dashboard owns the policy; the bridge only
    # exposes these paths through the common web transport.
    dashboard: str = "/dashboard"
    dashboard_data: str = "/dashboard/data.json"
    dashboard_static: str = "/dashboard/static"
    dashboard_css: str = "/dashboard/static/noesis-dashboard.css"
    dashboard_charts: str = "/" + "dashboard" + "/" + "static" + "/" + "charts" + ".js"


HTTP_MOUNTS = HttpMounts()


def operator_get_paths(mounts: HttpMounts = HTTP_MOUNTS) -> tuple[str, ...]:
    return (mounts.status, mounts.tools, mounts.dataset, mounts.logs)


def direct_tool_call_paths(mounts: HttpMounts = HTTP_MOUNTS) -> tuple[str, ...]:
    return (mounts.direct_tool_call,)


def oauth_paths(mounts: HttpMounts = HTTP_MOUNTS) -> tuple[str, ...]:
    return (mounts.oauth_register, mounts.oauth_authorize, mounts.oauth_token)


def dashboard_paths(mounts: HttpMounts = HTTP_MOUNTS) -> tuple[str, ...]:
    return (mounts.dashboard, mounts.dashboard_data, mounts.dashboard_css, mounts.dashboard_charts)


def public_web_paths(mounts: HttpMounts = HTTP_MOUNTS) -> tuple[str, ...]:
    return (
        mounts.health,
        mounts.favicon,
        mounts.dashboard,
        mounts.dashboard_data,
        mounts.dashboard_css, mounts.dashboard_charts,
    )
