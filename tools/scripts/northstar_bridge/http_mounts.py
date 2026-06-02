from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HttpMounts:
    health: str = "/health"
    status: str = "/status"
    tools: str = "/tools"
    direct_tool_call: str = "/tools/call"
    dataset: str = "/dataset"
    logs: str = "/logs"
    favicon: str = "/favicon.ico"
    oauth_register: str = "/oauth/register"
    oauth_authorize: str = "/oauth/authorize"
    oauth_token: str = "/oauth/token"


HTTP_MOUNTS = HttpMounts()


def operator_get_paths(mounts: HttpMounts = HTTP_MOUNTS) -> tuple[str, ...]:
    return (mounts.status, mounts.tools, mounts.dataset, mounts.logs)


def direct_tool_call_paths(mounts: HttpMounts = HTTP_MOUNTS) -> tuple[str, ...]:
    return (mounts.direct_tool_call,)


def oauth_paths(mounts: HttpMounts = HTTP_MOUNTS) -> tuple[str, ...]:
    return (mounts.oauth_register, mounts.oauth_authorize, mounts.oauth_token)
