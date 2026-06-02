from __future__ import annotations

import datetime as dt
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

BRIDGE_VERSION = "0.4.5"
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
OPENAI_KEY_CACHE_REL = Path(".takesome") / "secrets" / "openai_api_key.local"

SAFE_TEXT_EXTENSIONS = {
    ".bat", ".cmd", ".cfg", ".conf", ".css", ".csv", ".frag", ".glsl",
    ".h", ".hpp", ".html", ".ini", ".json", ".lock", ".md", ".py",
    ".rs", ".shader", ".sql", ".toml", ".txt", ".vert", ".xml", ".yaml", ".yml",
    ".jsonl",
}
SAFE_ROOTS = (
    "docs", "tools/scripts", "config", "Importers", "Plugins",
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

    @property
    def takesome_py(self) -> Path:
        return self.root / "tools" / "scripts" / "takesome.py"

    @property
    def bridge_config(self) -> Path:
        return self.root / "config" / "suite" / "ai_bridge.v1.json"

    @property
    def ai_root(self) -> Path:
        return self.root / ".takesome" / "ai-bridge"

    @property
    def log_dir(self) -> Path:
        return self.ai_root / "logs"

    @property
    def backup_dir(self) -> Path:
        return self.ai_root / "patch-backups"

    @property
    def openai_key_cache_path(self) -> Path:
        return self.root / OPENAI_KEY_CACHE_REL

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
