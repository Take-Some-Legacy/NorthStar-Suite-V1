from __future__ import annotations

from typing import Any

from .host_binding import SuiteHostBinding


def cluster_summary(binding: SuiteHostBinding | None) -> dict[str, Any]:
    """Return a stable, UI/API-friendly cluster topology summary.

    This is intentionally read-only. Active probing lives in cluster_doctor.py
    so passive /status never blocks on peer network calls.
    """
    if binding is None:
        return {
            "enabled": False,
            "mode": "unbound",
            "machine_count": 0,
            "local": None,
            "peers": [],
            "diagnostics": ["host_binding_missing"],
        }

    peers = [
        {
            "machine_id": peer.machine_id,
            "role": peer.role,
            "enabled": peer.enabled,
            "base_origin": peer.base_origin,
            "endpoint_url": peer.endpoint_url,
            "health_url": peer.health_url,
            "tags": list(peer.tags),
        }
        for peer in binding.peers
    ]
    return {
        "enabled": binding.is_clustered,
        "mode": binding.deployment_profile,
        "network_mode": binding.network_mode,
        "cluster_id": binding.cluster_id,
        "machine_count": 1 + len([peer for peer in binding.peers if peer.enabled]),
        "local": {
            "machine_id": binding.machine_id,
            "role": binding.role,
            "base_origin": binding.base_origin,
            "local_origin": binding.local_origin,
            "endpoint_url": binding.endpoint_url,
            "health_url": binding.health_url,
        },
        "peers": peers,
        "peer_endpoints": list(binding.peer_endpoints),
        "peer_health_urls": list(binding.peer_health_urls),
        "diagnostics": list(binding.diagnostics),
        "source": binding.source,
    }


__all__ = ["cluster_summary"]
