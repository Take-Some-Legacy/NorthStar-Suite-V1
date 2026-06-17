from __future__ import annotations

import datetime as dt
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config_loader import first_existing_config_path
from .mcp_routes import DEFAULT_MCP_ROUTES, McpRouteProfile

BRIDGE_VERSION = "dev mode"
PROTOCOL_VERSION = "2025-03-26"
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8797
MAX_TOOL_OUTPUT_BYTES = 128 * 1024
# Public MCP responses must stay bounded. Large Suite/status payloads can break
# streamable HTTP / JSON-RPC clients before they become useful diagnostics.
MAX_PUBLIC_RESPONSE_BYTES = 96 * 1024
MAX_PUBLIC_STRING_BYTES = 32 * 1024
MAX_EXEC_STDOUT_BYTES = 24 * 1024
MAX_EXEC_STDERR_BYTES = 12 * 1024
MAX_READ_BYTES_DEFAULT = 128 * 1024
MAX_SEARCH_FILE_BYTES = 512 * 1024
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
SUITE_ROOT_ENVS = (
    "NOESIS_SUITE_RUNTIME_ROOT",
    "NOESIS_SUITE_ROOT",
    "NORTHSTAR_SUITE_RUNTIME_ROOT",
    "NORTHSTAR_SUITE_ROOT",
    "NEWENGINE_SUITE_ROOT",
    "TAKESOME_SUITE_ROOT",
)
OPENAI_KEY_CACHE_REL = Path("secrets") / "openai_api_key.local"


def _default_machine_runtime_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "NoesisSuite"
    return Path.home() / ".local" / "state" / "noesis-suite"


def bridge_suite_root(project_root: Path) -> Path:
    """Return machine-local Suite runtime root, not workspace-local state.

    One Suite runs on one machine.  Runtime state, OAuth tokens, access tokens,
    logs and endpoint reports belong to the machine-local Suite runtime, while
    project files remain under the workspace root.
    """
    for name in SUITE_ROOT_ENVS:
        env = os.environ.get(name)
        if env:
            return Path(env).expanduser().resolve()
    return _default_machine_runtime_root().resolve()

SAFE_TEXT_EXTENSIONS = {
    ".bat", ".cmd", ".cfg", ".conf", ".css", ".csv", ".frag", ".glsl",
    ".h", ".hpp", ".html", ".ini", ".json", ".lock", ".md", ".py",
    ".rs", ".shader", ".sql", ".toml", ".txt", ".vert", ".xml", ".yaml", ".yml",
    ".jsonl",
}
SAFE_ROOTS = (
    "docs", "noesis", "tools", "config", "Importers", "Plugins",
    "NewEngine/neocore2/scripts", "NewEngine/neocore2/crates", "NewEngine/neocore2/apps",
    "NewEngine/neocore2/config", "NewEngine/neocore2/docs", "NewEngine/neocore2/assets", "NewEngine/neocore2/logs",
    ".takesome/buildLog", ".takesome/build-state", ".takesome/incidents",
    ".takesome/ai-bridge/logs", ".takesome/ai-bridge/notes", ".takesome/ai-bridge/state",
    ".takesome/ai-bridge/cache", ".takesome/ai-bridge/scratch", ".takesome/ai-bridge/reports",
    ".takesome/ai-bridge/tasks", ".takesome/ai-bridge/knowledge",
    ".takesome/dataSet", ".takesome/dataSet/archives", ".takesome/dataSet/extracted", ".takesome/dataSet/index",
)
# The bridge has project-root write/delete freedom, but it must never escape the
# repository or expose/destroy trust roots and local secrets. Build outputs,
# logs, dataset objects and normal source directories are intentionally allowed.
DENY_PARTS = {
    ".git",
    ".takesome/secrets",
    ".takesome/authority",
    ".takesome/ai-bridge/patch-backups",
}

class BridgeError(Exception):
    def __init__(self, message: str, code: str = "bridge_error", data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    output_schema: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BridgeContext:
    root: Path
    write_enabled: bool
    python_cmd: List[str]
    interactive: bool = False
    sudo: bool = False
    mcp_routes: McpRouteProfile = DEFAULT_MCP_ROUTES
    tool_root: Optional[Path] = None
    host_binding: Any = None

    @property
    def operator_root(self) -> Path:
        return (self.tool_root or self.root).resolve()

    @property
    def suite_module_args(self) -> List[str]:
        return ["-m", "noesis", "suite"]

    @property
    def takesome_py(self) -> Path:
        # Historical property retained for diagnostics only; execution uses python -m noesis suite.
        return self.operator_root / "noesis" / "suite" / "cli.py"

    @property
    def bridge_config(self) -> Path:
        found = first_existing_config_path(self.root, "ai_bridge.v1.json", operator_root=self.operator_root)
        return found or (self.operator_root / ".takesome" / "config" / "ai_bridge.v1.json")

    @property
    def suite_root(self) -> Path:
        return bridge_suite_root(self.root)

    @property
    def ai_root(self) -> Path:
        return self.suite_root / "ai-bridge"

    @property
    def log_dir(self) -> Path:
        return self.ai_root / "logs"

    @property
    def backup_dir(self) -> Path:
        return self.ai_root / "patch-backups"

    @property
    def openai_key_cache_path(self) -> Path:
        return self.suite_root / OPENAI_KEY_CACHE_REL

def configure_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

def now_utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

configure_stdio()
