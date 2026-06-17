from __future__ import annotations

from typing import Any

BRIDGE_RELEASE_NAME = "NOESIS live operator bridge"
BRIDGE_RELEASE_NOTES = "gkd-runtime-config-binding + rich-server-metadata"
BRIDGE_PUBLIC_TITLE = "NOESIS Suite Operator Bridge"
BRIDGE_SHORT_TITLE = "NOESIS Bridge"
BRIDGE_SUBTITLE = "SuiteLab canonical MCP/OAuth operator gateway"
BRIDGE_PUBLIC_DESCRIPTION = (
    "NOESIS canonical MCP bridge for SuiteLab: local operator control plane, "
    "OAuth-protected MCP tools, Suite command execution, repository diagnostics, "
    "cluster identity, and controlled workspace maintenance."
)
BRIDGE_PRODUCT_NAME = "NOESIS"
BRIDGE_SERVICE_NAME = "noesis-suite-operator-bridge"
BRIDGE_VENDOR = "Take Some / SuiteLab"
BRIDGE_RUNTIME_LAYOUT = "canonical-noesis-package"
BRIDGE_DEFAULT_ICON = "/favicon.ico"
BRIDGE_TRANSPORT = "mcp-streamable-http"
BRIDGE_PROTOCOL_FAMILY = "MCP + OAuth 2.1"
BRIDGE_AUTH_MODEL = "local-owner-oauth-token"
BRIDGE_CAPABILITY_SUMMARY = (
    "Suite command registry, repository diagnostics, bounded filesystem edits, "
    "dataset inspection, operator memory, and cluster-aware bridge status."
)


def metadata() -> dict[str, str]:
    return {
        "name": BRIDGE_SERVICE_NAME,
        "product": BRIDGE_PRODUCT_NAME,
        "vendor": BRIDGE_VENDOR,
        "release_name": BRIDGE_RELEASE_NAME,
        "release_notes": BRIDGE_RELEASE_NOTES,
        "title": BRIDGE_PUBLIC_TITLE,
        "short_title": BRIDGE_SHORT_TITLE,
        "subtitle": BRIDGE_SUBTITLE,
        "description": BRIDGE_PUBLIC_DESCRIPTION,
        "runtime_layout": BRIDGE_RUNTIME_LAYOUT,
        "icon": BRIDGE_DEFAULT_ICON,
        "transport": BRIDGE_TRANSPORT,
        "protocol_family": BRIDGE_PROTOCOL_FAMILY,
        "auth_model": BRIDGE_AUTH_MODEL,
        "capability_summary": BRIDGE_CAPABILITY_SUMMARY,
    }


def html_title(suffix: str | None = None) -> str:
    if suffix:
        suffix = str(suffix).strip()
    return f"{BRIDGE_PUBLIC_TITLE} — {suffix}" if suffix else BRIDGE_PUBLIC_TITLE


def public_meta(binding: Any = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": BRIDGE_PUBLIC_TITLE,
        "shortTitle": BRIDGE_SHORT_TITLE,
        "subtitle": BRIDGE_SUBTITLE,
        "name": BRIDGE_SERVICE_NAME,
        "product": BRIDGE_PRODUCT_NAME,
        "vendor": BRIDGE_VENDOR,
        "description": BRIDGE_PUBLIC_DESCRIPTION,
        "releaseName": BRIDGE_RELEASE_NAME,
        "releaseNotes": BRIDGE_RELEASE_NOTES,
        "runtimeLayout": BRIDGE_RUNTIME_LAYOUT,
        "transport": BRIDGE_TRANSPORT,
        "protocolFamily": BRIDGE_PROTOCOL_FAMILY,
        "authModel": BRIDGE_AUTH_MODEL,
        "capabilitySummary": BRIDGE_CAPABILITY_SUMMARY,
        "icon": BRIDGE_DEFAULT_ICON,
    }
    if binding is not None:
        data.update({
            "clusterId": getattr(binding, "cluster_id", ""),
            "machineId": getattr(binding, "machine_id", ""),
            "machineRole": getattr(binding, "role", ""),
            "endpointUrl": getattr(binding, "endpoint_url", ""),
            "healthUrl": getattr(binding, "health_url", ""),
            "isClustered": bool(getattr(binding, "is_clustered", False)),
        })
    return data
