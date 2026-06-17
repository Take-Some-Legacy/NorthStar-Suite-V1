from __future__ import annotations

from pathlib import Path
from typing import Any

from noesis.web.adapters import WebAdapterSpec

from . import release_info

MCP_ADAPTER_SPEC = WebAdapterSpec(
    adapter_id="mcp",
    surface="bridge.mcp",
    title=f"{release_info.BRIDGE_SHORT_TITLE} MCP",
    mount_paths=("/mcp",),
    routes=("/mcp", "/health", "/status", "/tools"),
    policy="compatibility MCP transport adapter",
    description="Compatibility MCP adapter hosted by the NOESIS bridge web surface.",
    metadata={"protocol": "mcp", "compatibility": True},
)

MCP_V2_ADAPTER_SPEC = WebAdapterSpec(
    adapter_id="mcp-v2",
    surface="bridge.mcp-v2",
    title=release_info.BRIDGE_PUBLIC_TITLE,
    mount_paths=("/mcp-v2",),
    routes=("/mcp-v2", "/health", "/status", "/cluster", "/cluster/doctor", "/tools", "/dataset", "/logs"),
    policy="canonical MCP v2 transport adapter",
    description="Canonical NOESIS MCP v2 adapter hosted by the bridge web surface.",
    metadata={"protocol": "mcp", "canonical": True, "transport": release_info.BRIDGE_TRANSPORT},
)

BRIDGE_WEB_ADAPTERS = (MCP_ADAPTER_SPEC, MCP_V2_ADAPTER_SPEC)


def bridge_web_adapters_metadata(*, root: Path | None = None) -> list[dict[str, Any]]:
    return [spec.as_dict(root=root) for spec in BRIDGE_WEB_ADAPTERS]


def adapter_for_path(path: str) -> WebAdapterSpec:
    normalized = str(path or "/")
    if normalized == "/mcp-v2" or normalized.startswith("/mcp-v2/"):
        return MCP_V2_ADAPTER_SPEC
    if normalized == "/mcp" or normalized.startswith("/mcp/"):
        return MCP_ADAPTER_SPEC
    return MCP_V2_ADAPTER_SPEC
