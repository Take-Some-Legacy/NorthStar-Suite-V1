from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Callable


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    module: str
    function: str = "main"
    description: str = "NOESIS runtime service"
    consumes_command_token: bool = True

    def load(self) -> Callable[[list[str]], int]:
        target = getattr(import_module(self.module), self.function)
        return target


SERVICE_REGISTRY: dict[str, ServiceSpec] = {
    "bridge": ServiceSpec("bridge", "noesis.bridge.cli", description="Local MCP/HTTP bridge origin"),
    "bridge-endpoint": ServiceSpec("bridge-endpoint", "noesis.bridge.endpoint", description="Read/write bridge endpoint state"),
    "bridge-restart": ServiceSpec("bridge-restart", "noesis.bridge.restart_cli", description="Safe local bridge restart helper"),
    "install-llm-runtime": ServiceSpec("install-llm-runtime", "noesis.config.install_llm_runtime", description="Install/check local LLM runtime assets"),
    "pilot-console": ServiceSpec("pilot-console", "noesis.supervisor.pilot_console", description="LLM pilot operator console"),
    "runs": ServiceSpec("runs", "noesis.dashboard.runs", description="NOESIS run dashboard and index commands"),
    "dashboard-verify": ServiceSpec("dashboard-verify", "noesis.dashboard.verify", description="Verify dashboard publication"),
    "script-env": ServiceSpec("script-env", "noesis.config.script_env", description="Generate runtime script environment"),
    "supervisor": ServiceSpec("supervisor", "noesis.supervisor.main", description="One-window local origin + tunnel supervisor"),
    "suite": ServiceSpec("suite", "noesis.suite.cli", description="NOESIS Suite command plane", consumes_command_token=False),
}

# Backward-compatible variable name for older imports inside mixed live trees.
SERVICES = SERVICE_REGISTRY

ALIASES: dict[str, str] = {
    # Alias only for CLI dispatch. It must not mean tools/scripts is supported.
    "takesome": "suite",
}


def resolve_service(name: str) -> ServiceSpec | None:
    key = ALIASES.get(name, name)
    return SERVICE_REGISTRY.get(key)


def run_service(name: str, argv: Sequence[str]) -> int:
    spec = resolve_service(name)
    if spec is None:
        raise KeyError(name)
    args = list(argv)
    if not spec.consumes_command_token:
        args = [spec.name, *args]
    return int(spec.load()(args) or 0)
