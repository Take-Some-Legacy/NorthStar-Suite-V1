from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import RuntimePaths


DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "schema": "noesis.runtime.v1",
    "workspace": {"root": ".", "kind": "suite"},
    "bridge": {"host": "127.0.0.1", "port": 8797, "endpoint": "/mcp-v2"},
    "security": {"writeEnabled": True, "sudoEnabled": False, "policy": "config-driven"},
    "cluster": {
        "enabled": True,
        "cluster_id": "noesis-cluster",
        "machine_id": "suite-node-01",
        "role": "operator",
        "network_mode": "single-host-first",
        "peers": [],
    },
    "services": {"discovery": {"enabled": True, "roots": ["noesis.services", "noesis.bridge", "noesis.suite"]}},
    "tools": {"discovery": {"enabled": True, "descriptorRoots": ["tools/toolbelt", "tools"]}},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass(frozen=True)
class RuntimeConfig:
    paths: RuntimePaths
    data: dict[str, Any]

    @property
    def host(self) -> str:
        return str(self.data.get("bridge", {}).get("host", "127.0.0.1"))

    @property
    def port(self) -> int:
        return int(self.data.get("bridge", {}).get("port", 8797))

    @property
    def endpoint(self) -> str:
        endpoint = str(self.data.get("bridge", {}).get("endpoint", "/mcp-v2"))
        return endpoint if endpoint.startswith("/") else "/" + endpoint

    @property
    def write_enabled(self) -> bool:
        return bool(self.data.get("security", {}).get("writeEnabled", False))

    @property
    def sudo_enabled(self) -> bool:
        return bool(self.data.get("security", {}).get("sudoEnabled", False))


def load_runtime_config(start: Path | None = None, explicit: str | Path | None = None) -> RuntimeConfig:
    paths = RuntimePaths.resolve(start)
    config_path = Path(explicit).expanduser().resolve() if explicit else paths.config
    data = DEFAULT_RUNTIME_CONFIG
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = deep_merge(data, loaded)
        except Exception:
            data = DEFAULT_RUNTIME_CONFIG
    return RuntimeConfig(paths=RuntimePaths(root=paths.root, config=config_path, package=paths.package), data=data)


def write_default_runtime_config(root: Path) -> Path:
    path = root / "config" / "noesis" / "runtime.v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_RUNTIME_CONFIG, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
