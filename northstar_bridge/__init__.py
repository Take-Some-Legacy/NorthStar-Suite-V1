"""Import alias for external MCP/tool wrappers that still reference `northstar_bridge`.

This package is not a runtime implementation and does not restore the removed
`tools/scripts` tree. All implementation lives in `noesis.bridge`; this module
only maps old import names used by generated wrappers to canonical NOESIS until
those wrappers are regenerated.
"""
from __future__ import annotations

import importlib
import sys
from typing import Any

_CANONICAL_PACKAGE = "noesis.bridge"
_EXPORTED_SUBMODULES = (
    "access", "auth", "bridge_restart", "cli", "cluster_doctor", "cluster_topology",
    "config_loader", "console", "contracts", "dataset", "dataset_archive",
    "dataset_browser", "dataset_core", "dataset_entry_value", "dataset_index",
    "dataset_maturity", "host_binding", "http_mounts", "mcp_routes", "memory",
    "memory_diagnostics", "memory_queries", "memory_schema", "memory_store",
    "net_address", "oauth", "oauth_scopes", "operator_fs", "operator_tools",
    "paths", "registry", "release_info", "repo", "rpc", "rpc_surface", "server",
    "status", "suite", "supervisor_footer", "terminal_style", "tool_registry",
    "workflow", "workspace_config",
)

_canonical = importlib.import_module(_CANONICAL_PACKAGE)

for _name in _EXPORTED_SUBMODULES:
    try:
        sys.modules[f"{__name__}.{_name}"] = importlib.import_module(f"{_CANONICAL_PACKAGE}.{_name}")
    except ModuleNotFoundError:
        pass


def __getattr__(name: str) -> Any:
    return getattr(_canonical, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_canonical)))


__all__ = [name for name in dir(_canonical) if not name.startswith("_")]
