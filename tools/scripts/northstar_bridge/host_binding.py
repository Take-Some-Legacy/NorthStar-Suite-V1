from __future__ import annotations

import os
import socket
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config_loader import load_config_json
from .net_address import (
    join_origin_path,
    local_http_origin,
    normalize_http_path,
    normalize_origin,
    normalize_port,
    slug_id,
    split_csv,
    text,
    truthy,
)

HOST_BINDING_CONFIG_NAME = "host_binding.v1.json"
PUBLIC_ORIGIN_CONFIG_NAME = "bridge_public_origin.v1.json"
DEFAULT_ENDPOINT_PATH = "/mcp-v2"
DEFAULT_HEALTH_PATH = "/health"
DEFAULT_BRIDGE_PORT = 8797


@dataclass(frozen=True)
class SuitePeerBinding:
    """Remote Suite machine declared in the cluster/federation map."""

    machine_id: str
    public_origin: str
    endpoint_path: str = DEFAULT_ENDPOINT_PATH
    health_path: str = DEFAULT_HEALTH_PATH
    role: str = "peer"
    enabled: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def base_origin(self) -> str:
        return normalize_origin(self.public_origin)

    @property
    def endpoint_url(self) -> str:
        return join_origin_path(self.base_origin, self.endpoint_path, default_path=DEFAULT_ENDPOINT_PATH)

    @property
    def health_url(self) -> str:
        return join_origin_path(self.base_origin, self.health_path, default_path=DEFAULT_HEALTH_PATH)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["base_origin"] = self.base_origin
        data["endpoint_url"] = self.endpoint_url
        data["health_url"] = self.health_url
        return data


@dataclass(frozen=True)
class SuiteHostBinding:
    """Resolved identity and address binding for exactly one Suite machine.

    Scale-out uses multiple Suite machines, not multiple local Suite instances.
    This object is the contract between launcher, HTTP bridge, endpoint-state,
    diagnostics and future peer probing.
    """

    suite_id: str = "noesis-suite"
    machine_id: str = "local-machine"
    cluster_id: str = "local"
    role: str = "primary"
    deployment_profile: str = "single-machine"
    network_mode: str = "local"
    bind_host: str = "127.0.0.1"
    bind_port: int = DEFAULT_BRIDGE_PORT
    endpoint_path: str = DEFAULT_ENDPOINT_PATH
    health_path: str = DEFAULT_HEALTH_PATH
    public_origin: str = ""
    advertised_origin: str = ""
    peers: tuple[SuitePeerBinding, ...] = field(default_factory=tuple)
    diagnostics: tuple[str, ...] = field(default_factory=tuple)
    source: str = "defaults"

    @property
    def host_id(self) -> str:
        return self.machine_id

    @property
    def local_origin(self) -> str:
        return local_http_origin(self.bind_host, self.bind_port, default_port=DEFAULT_BRIDGE_PORT)

    @property
    def base_origin(self) -> str:
        return normalize_origin(self.advertised_origin) or normalize_origin(self.public_origin) or self.local_origin

    @property
    def endpoint_url(self) -> str:
        return join_origin_path(self.base_origin, self.endpoint_path, default_path=DEFAULT_ENDPOINT_PATH)

    @property
    def health_url(self) -> str:
        return join_origin_path(self.base_origin, self.health_path, default_path=DEFAULT_HEALTH_PATH)

    @property
    def enabled_peers(self) -> tuple[SuitePeerBinding, ...]:
        return tuple(peer for peer in self.peers if peer.enabled)

    @property
    def peer_endpoints(self) -> tuple[str, ...]:
        return tuple(peer.endpoint_url for peer in self.enabled_peers if peer.endpoint_url)

    @property
    def peer_health_urls(self) -> tuple[str, ...]:
        return tuple(peer.health_url for peer in self.enabled_peers if peer.health_url)

    @property
    def is_clustered(self) -> bool:
        return self.cluster_id not in {"", "local", "single", "standalone"} or bool(self.enabled_peers)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["host_id"] = self.host_id
        data["local_origin"] = self.local_origin
        data["base_origin"] = self.base_origin
        data["endpoint_url"] = self.endpoint_url
        data["health_url"] = self.health_url
        data["peer_endpoints"] = list(self.peer_endpoints)
        data["peer_health_urls"] = list(self.peer_health_urls)
        data["is_clustered"] = self.is_clustered
        data["peers"] = [peer.as_dict() for peer in self.peers]
        data["diagnostics"] = list(self.diagnostics)
        return data


def _env(*names: str) -> str:
    for name in names:
        raw = os.environ.get(name, "").strip()
        if raw:
            return raw
    return ""


def _hostname() -> str:
    try:
        return socket.gethostname() or "local-machine"
    except Exception:
        return "local-machine"


def _public_from_bridge_config(root: Path, tool_root: Path | None) -> dict[str, Any]:
    result = load_config_json(root, PUBLIC_ORIGIN_CONFIG_NAME, operator_root=tool_root)
    public = result.data
    mcp = public.get("mcp") if isinstance(public.get("mcp"), dict) else {}
    return {
        "public_origin": public.get("public_origin"),
        "endpoint_path": mcp.get("endpoint"),
        "local_origin": public.get("local_origin"),
    }


def _peer_from_string(value: str, *, default_endpoint: str, default_health: str) -> SuitePeerBinding | None:
    raw = text(value)
    if not raw:
        return None
    if "=" in raw:
        machine_id, origin = raw.split("=", 1)
    else:
        origin = raw
        machine_id = urlparse(origin).hostname or origin
    origin = normalize_origin(origin)
    if not origin:
        return None
    return SuitePeerBinding(
        machine_id=slug_id(machine_id, "peer"),
        public_origin=origin,
        endpoint_path=default_endpoint,
        health_path=default_health,
    )


def _peer_from_dict(value: dict[str, Any], *, default_endpoint: str, default_health: str) -> SuitePeerBinding | None:
    origin = normalize_origin(value.get("public_origin") or value.get("origin") or value.get("url") or value.get("base_origin"))
    if not origin:
        return None
    machine_id = slug_id(value.get("machine_id") or value.get("host_id") or value.get("id"), urlparse(origin).hostname or "peer")
    return SuitePeerBinding(
        machine_id=machine_id,
        public_origin=origin,
        endpoint_path=normalize_http_path(value.get("endpoint_path") or value.get("endpoint"), default_endpoint),
        health_path=normalize_http_path(value.get("health_path") or value.get("health"), default_health),
        role=slug_id(value.get("role"), "peer"),
        enabled=truthy(value.get("enabled"), True),
        tags=split_csv(value.get("tags")),
    )


def _peers(value: object, *, default_endpoint: str, default_health: str) -> tuple[SuitePeerBinding, ...]:
    result: list[SuitePeerBinding] = []
    if isinstance(value, dict):
        value = value.get("nodes") or value.get("peers") or []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = split_csv(value)
    for item in items:
        peer = _peer_from_dict(item, default_endpoint=default_endpoint, default_health=default_health) if isinstance(item, dict) else _peer_from_string(str(item), default_endpoint=default_endpoint, default_health=default_health)
        if peer:
            result.append(peer)
    return tuple(result)


def _validate(binding: SuiteHostBinding) -> tuple[str, ...]:
    issues: list[str] = []
    if binding.bind_host in {"0.0.0.0", "::"} and not binding.public_origin and not binding.advertised_origin:
        issues.append("wildcard_bind_without_public_origin")
    if binding.is_clustered and not (binding.public_origin or binding.advertised_origin):
        issues.append("clustered_node_without_public_origin")
    if binding.bind_port <= 0:
        issues.append("invalid_bind_port")
    seen: set[str] = set()
    origins: set[str] = set()
    for peer in binding.peers:
        if peer.machine_id == binding.machine_id:
            issues.append("self_declared_as_peer")
        if peer.machine_id in seen:
            issues.append(f"duplicate_peer:{peer.machine_id}")
        if peer.base_origin in origins:
            issues.append(f"duplicate_peer_origin:{peer.base_origin}")
        seen.add(peer.machine_id)
        origins.add(peer.base_origin)
    return tuple(issues)


def resolve_host_binding(
    root: Path,
    tool_root: Path | None = None,
    *,
    cli_host: object = None,
    cli_port: object = None,
    cli_machine_id: object = None,
    cli_cluster_id: object = None,
    cli_machine_role: object = None,
    cli_public_origin: object = None,
    cli_advertised_origin: object = None,
    cli_endpoint_path: object = None,
    cli_peer: object = None,
) -> SuiteHostBinding:
    loaded = load_config_json(root, HOST_BINDING_CONFIG_NAME, operator_root=tool_root)
    config = loaded.data
    machine = config.get("machine") if isinstance(config.get("machine"), dict) else {}
    cluster = config.get("cluster") if isinstance(config.get("cluster"), dict) else {}
    binding = config.get("binding") if isinstance(config.get("binding"), dict) else {}
    public_fallback = _public_from_bridge_config(root, tool_root)

    default_machine = slug_id(_hostname(), "local-machine")
    suite_id = slug_id(_env("AURELIA_SUITE_ID", "NORTHSTAR_SUITE_ID") or config.get("suite_id"), "noesis-suite")
    machine_id = slug_id(cli_machine_id or _env("AURELIA_SUITE_MACHINE_ID", "NORTHSTAR_SUITE_MACHINE_ID", "NORTHSTAR_HOST_ID") or machine.get("id"), default_machine)
    cluster_id = slug_id(cli_cluster_id or _env("AURELIA_SUITE_CLUSTER_ID", "NORTHSTAR_SUITE_CLUSTER_ID") or cluster.get("id"), "local")

    bind_host = text(cli_host) or _env("AURELIA_BRIDGE_BIND_HOST", "NORTHSTAR_BRIDGE_BIND_HOST", "NORTHSTAR_HTTP_HOST") or text(binding.get("host")) or "127.0.0.1"
    bind_port = normalize_port(cli_port or _env("AURELIA_BRIDGE_BIND_PORT", "NORTHSTAR_BRIDGE_BIND_PORT", "NORTHSTAR_HTTP_PORT") or binding.get("port"), DEFAULT_BRIDGE_PORT)
    endpoint_path = normalize_http_path(cli_endpoint_path or _env("AURELIA_BRIDGE_ENDPOINT", "NORTHSTAR_BRIDGE_ENDPOINT", "NORTHSTAR_MCP_ENDPOINT_PATH") or binding.get("endpoint") or binding.get("endpoint_path") or public_fallback.get("endpoint_path"), DEFAULT_ENDPOINT_PATH)
    health_path = normalize_http_path(binding.get("health") or binding.get("health_path"), DEFAULT_HEALTH_PATH)
    public_origin = normalize_origin(cli_public_origin or _env("AURELIA_BRIDGE_PUBLIC_ORIGIN", "NORTHSTAR_BRIDGE_PUBLIC_ORIGIN") or binding.get("public_origin") or public_fallback.get("public_origin"))
    advertised_origin = normalize_origin(cli_advertised_origin or _env("AURELIA_BRIDGE_ADVERTISED_ORIGIN", "NORTHSTAR_BRIDGE_ADVERTISED_ORIGIN") or binding.get("advertised_origin"))
    peers = _peers(cli_peer or cluster.get("peers") or cluster.get("nodes"), default_endpoint=endpoint_path, default_health=health_path)

    resolved = SuiteHostBinding(
        suite_id=suite_id,
        machine_id=machine_id,
        cluster_id=cluster_id,
        role=slug_id(cli_machine_role or _env("AURELIA_SUITE_MACHINE_ROLE", "NORTHSTAR_SUITE_MACHINE_ROLE") or machine.get("role"), "primary"),
        deployment_profile=slug_id(config.get("deployment_profile") or cluster.get("deployment_profile") or machine.get("deployment_profile"), "single-machine"),
        network_mode=slug_id(binding.get("network_mode") or cluster.get("network_mode"), "local"),
        bind_host=bind_host,
        bind_port=bind_port,
        endpoint_path=endpoint_path,
        health_path=health_path,
        public_origin=public_origin,
        advertised_origin=advertised_origin,
        peers=peers,
        source=str(loaded.path) if loaded.path is not None else loaded.source,
    )
    return replace(resolved, diagnostics=_validate(resolved))


def host_binding_config_template(*, machine_id: str = "suite-node-01", cluster_id: str = "noesis-cluster", public_origin: str = "") -> dict[str, Any]:
    return {
        "schema": "noesis.suite.host_binding.v1",
        "suite_id": "noesis-suite",
        "deployment_profile": "federated-machines",
        "machine": {
            "id": machine_id,
            "role": "primary",
        },
        "binding": {
            "host": "127.0.0.1",
            "port": DEFAULT_BRIDGE_PORT,
            "endpoint": DEFAULT_ENDPOINT_PATH,
            "health": DEFAULT_HEALTH_PATH,
            "public_origin": public_origin,
            "network_mode": "tunnel",
        },
        "cluster": {
            "id": cluster_id,
            "network_mode": "federated-machines",
            "peers": [],
        },
    }


__all__ = [
    "DEFAULT_BRIDGE_PORT",
    "DEFAULT_ENDPOINT_PATH",
    "DEFAULT_HEALTH_PATH",
    "SuiteHostBinding",
    "SuitePeerBinding",
    "host_binding_config_template",
    "resolve_host_binding",
]
