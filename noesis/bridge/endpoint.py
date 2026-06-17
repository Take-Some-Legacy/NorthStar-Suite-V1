#!/usr/bin/env python3
"""Endpoint state helper for North Star AI Bridge launchers."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict

from noesis.bridge.cluster_doctor import ProbeTarget, probe_json_url, run_cluster_doctor
from noesis.bridge.config_loader import write_json_object
from noesis.bridge.contracts import bridge_suite_root
from noesis.bridge.host_binding import host_binding_config_template, resolve_host_binding
from noesis.bridge.mcp_routes import load_mcp_route_profile
from noesis.bridge.workspace_config import apply_workspace_environment, load_workspace_config, resolve_tool_root, resolve_workspace_root

DEFAULT_MCP_ENDPOINT_PATH = "/mcp"


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _root(path: str, workspace_config_path: str = "") -> Path:
    launch_root = Path.cwd().resolve()
    config = load_workspace_config(launch_root, workspace_config_path)
    root = resolve_workspace_root(launch_root, path or "auto", config)
    apply_workspace_environment(root, config)
    return root.resolve()


def _tool_root(root: Path, workspace_config_path: str = "") -> Path:
    launch_root = Path.cwd().resolve()
    config = load_workspace_config(launch_root, workspace_config_path)
    return resolve_tool_root(launch_root, config).resolve()


def _binding(root: Path, workspace_config_path: str = "", host: object = None, port: object = None, public_origin: object = None, endpoint_path: object = None, machine_id: object = None, cluster_id: object = None, machine_role: object = None, advertised_origin: object = None, peer: object = None):
    return resolve_host_binding(root, _tool_root(root, workspace_config_path), cli_host=host, cli_port=port, cli_public_origin=public_origin, cli_endpoint_path=endpoint_path, cli_machine_id=machine_id, cli_cluster_id=cluster_id, cli_machine_role=machine_role, cli_advertised_origin=advertised_origin, cli_peer=peer)


def _default_endpoint(root: Path, host: object = None, port: object = None, workspace_config_path: str = "", public_origin: object = None, endpoint_path: object = None) -> str:
    binding = _binding(root, workspace_config_path, host, port, public_origin, endpoint_path)
    return binding.endpoint_url


def _state_dir(root: Path) -> Path:
    return bridge_suite_root(root) / "ai-bridge" / "state"


def _reports_dir(root: Path) -> Path:
    return bridge_suite_root(root) / "ai-bridge" / "reports"


def _state_path(root: Path) -> Path:
    return _state_dir(root) / "endpoint.json"


def _report_path(root: Path) -> Path:
    return _reports_dir(root) / "CONNECT_CHATGPT.md"


def _load_state(root: Path) -> Dict[str, Any]:
    path = _state_path(root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    write_json_object(path, payload)


def _write_report(root: Path, state: Dict[str, Any]) -> Path:
    endpoint = str(state.get("active_endpoint") or _default_endpoint(root))
    mode = str(state.get("mode") or "http")
    write_enabled = bool(state.get("write_enabled"))
    logs_dir = str(state.get("logs_directory") or ".takesome/ai-bridge/logs")
    tunnel = state.get("tunnel") or {}
    tunnel_kind = tunnel.get("kind") if isinstance(tunnel, dict) else None
    tunnel_name = tunnel.get("name") if isinstance(tunnel, dict) else None
    path = _report_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tunnel_line = "none"
    if tunnel_kind:
        tunnel_line = tunnel_kind if not tunnel_name else f"{tunnel_kind}:{tunnel_name}"
    content = f"""# MCP Connector Info

**Active endpoint:** {endpoint}
**Mode:** {mode}
**Write enabled:** {str(write_enabled).lower()}
**Tunnel:** {tunnel_line}
**Logs directory:** {logs_dir}
**Endpoint state:** machine-local Suite runtime `ai-bridge/state/endpoint.json`
**Machine:** {state.get('machine_id') or 'local-machine'}
**Cluster:** {state.get('cluster_id') or 'local'}
**Peer endpoints:** {len(state.get('peer_endpoints') or [])}
**Updated at:** {state.get('updated_at') or _utc_now()}

## Usage

1. For MCP/HTTP clients, use the active endpoint above.
2. For local stdio clients, run:

```bat
aiBridge.bat stdio
```

3. For stable local HTTP state after a restart, run:

```bat
aiBridge.bat up
aiBridge.bat endpoint
```

4. For write-enabled operator mode, run:

```bat
aiBridge.bat up write
```

5. For the stable Cloudflare domain tunnel, run the one-window supervisor:

```bat
serverBridge.bat
```

`aiBridge.bat tunnel` is also routed to the same supervisor. It starts the local HTTP origin and then raises the declared named tunnel/domain from `.takesome/config/ai_bridge.v1.json`.
"""
    path.write_text(content, encoding="utf-8")
    return path


def write_state(args: argparse.Namespace) -> int:
    root = _root(args.root, args.workspace_config)
    binding = _binding(root, args.workspace_config, args.host, args.port, args.public_origin, args.endpoint_path, args.machine_id, args.cluster_id, args.machine_role, args.advertised_origin, args.peer)
    endpoint = args.endpoint or binding.endpoint_url
    existing = _load_state(root)
    state: Dict[str, Any] = {
        "active_endpoint": endpoint,
        "mode": args.mode,
        "machine_id": binding.machine_id,
        "cluster_id": binding.cluster_id,
        "machine_role": binding.role,
        "deployment_profile": binding.deployment_profile,
        "network_mode": binding.network_mode,
        "host": binding.bind_host,
        "port": binding.bind_port,
        "started_at": args.started_at or existing.get("started_at") or _utc_now(),
        "updated_at": _utc_now(),
        "write_enabled": bool(args.write_enabled),
        "runtime_root": bridge_suite_root(root).as_posix(),
        "logs_directory": (bridge_suite_root(root) / "ai-bridge" / "logs").as_posix(),
        "state_file": _state_path(root).as_posix(),
        "report_file": _report_path(root).as_posix(),
        "host_binding": binding.as_dict(),
        "peer_endpoints": list(binding.peer_endpoints),
        "peer_health_urls": list(binding.peer_health_urls),
        "tunnel": {
            "kind": args.tunnel_kind,
            "name": args.tunnel_name,
            "target": args.tunnel_target,
        },
    }
    _write_json(_state_path(root), state)
    report = _write_report(root, state)
    if args.print_json:
        print(json.dumps({"ok": True, "state": state, "report": str(report)}, ensure_ascii=False, indent=2))
    else:
        print(endpoint)
    return 0


def endpoint(args: argparse.Namespace) -> int:
    root = _root(args.root, args.workspace_config)
    state = _load_state(root)
    if not state:
        binding = _binding(root, args.workspace_config, args.host, args.port, args.public_origin, args.endpoint_path, args.machine_id, args.cluster_id, args.machine_role, args.advertised_origin, args.peer)
        state = {
            "active_endpoint": binding.endpoint_url,
            "mode": "http",
            "machine_id": binding.machine_id,
            "cluster_id": binding.cluster_id,
            "machine_role": binding.role,
            "write_enabled": False,
            "state_file": _state_path(root).as_posix(),
            "report_file": _report_path(root).as_posix(),
            "host_binding": binding.as_dict(),
            "peer_endpoints": list(binding.peer_endpoints),
            "peer_health_urls": list(binding.peer_health_urls),
            "updated_at": _utc_now(),
        }
        _write_json(_state_path(root), state)
        _write_report(root, state)
    if args.print_json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(state.get("active_endpoint") or _default_endpoint(root, workspace_config_path=args.workspace_config))
    return 0


def report(args: argparse.Namespace) -> int:
    root = _root(args.root, args.workspace_config)
    state = _load_state(root)
    if not state:
        state = {"active_endpoint": _default_endpoint(root, workspace_config_path=args.workspace_config), "mode": "http", "write_enabled": False, "updated_at": _utc_now()}
        _write_json(_state_path(root), state)
    path = _write_report(root, state)
    try:
        print(path.relative_to(root).as_posix())
    except ValueError:
        print(path.as_posix())
    return 0



def print_binding(args: argparse.Namespace) -> int:
    root = _root(args.root, args.workspace_config)
    binding = _binding(root, args.workspace_config, args.host, args.port, args.public_origin, args.endpoint_path, args.machine_id, args.cluster_id, args.machine_role, args.advertised_origin, args.peer)
    print(json.dumps({"ok": True, "host_binding": binding.as_dict()}, ensure_ascii=False, indent=2))
    return 0


def init_host(args: argparse.Namespace) -> int:
    root = _root(args.root, args.workspace_config)
    suite_root = _tool_root(root, args.workspace_config)
    config_dir = suite_root / ".takesome" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    machine_id = args.machine_id or "suite-node-01"
    cluster_id = args.cluster_id or "noesis-cluster"
    public_origin = args.public_origin or ""
    payload = host_binding_config_template(machine_id=machine_id, cluster_id=cluster_id, public_origin=public_origin)
    machine = payload.setdefault("machine", {})
    if args.machine_role:
        machine["role"] = args.machine_role
    bind = payload.setdefault("binding", {})
    if args.host:
        bind["host"] = args.host
    if args.port is not None:
        bind["port"] = args.port
    if args.endpoint_path:
        bind["endpoint"] = args.endpoint_path
    if args.public_origin:
        bind["public_origin"] = args.public_origin
    if args.advertised_origin:
        bind["advertised_origin"] = args.advertised_origin
    if args.peer:
        cluster = payload.setdefault("cluster", {})
        cluster["peers"] = list(args.peer)
    path = config_dir / "host_binding.v1.json"
    write_json_object(path, payload)
    binding = resolve_host_binding(root, suite_root)
    result = {"ok": True, "path": str(path), "host_binding": binding.as_dict()}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

def probe(args: argparse.Namespace) -> int:
    if args.url:
        target = ProbeTarget(
            machine_id=args.machine_id or "ad-hoc",
            role=args.machine_role or "probe",
            base_origin=args.url,
            health_url=args.url,
            status_url=args.url,
            expected_cluster_id=args.cluster_id or "",
        )
        url = args.url
    else:
        root = _root(args.root, args.workspace_config)
        binding = _binding(root, args.workspace_config, args.host, args.port, args.public_origin, args.endpoint_path, args.machine_id, args.cluster_id, args.machine_role, args.advertised_origin, args.peer)
        target = ProbeTarget(
            machine_id=binding.machine_id,
            role=binding.role,
            base_origin=binding.base_origin,
            health_url=binding.health_url,
            status_url=binding.health_url,
            expected_cluster_id=binding.cluster_id,
        )
        url = binding.health_url
    outcome, _body = probe_json_url(target, stage="health", url=url, timeout_sec=args.timeout, request_id=f"{target.machine_id}:health")
    if args.print_json:
        print(json.dumps({"ok": bool(outcome.get("ok")), "request": outcome}, ensure_ascii=False, indent=2))
    else:
        print(f"{outcome.get('outcome')} {outcome.get('http', {}).get('status')} {url} {outcome.get('elapsed_ms')}ms")
    return 0 if outcome.get("ok") else 1


def cluster_doctor(args: argparse.Namespace) -> int:
    root = _root(args.root, args.workspace_config)
    binding = _binding(root, args.workspace_config, args.host, args.port, args.public_origin, args.endpoint_path, args.machine_id, args.cluster_id, args.machine_role, args.advertised_origin, args.peer)
    report = run_cluster_doctor(binding, timeout_sec=args.timeout, include_status=not bool(args.skip_status), include_disabled=bool(args.include_disabled))
    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report.get("summary") or {}
        print(f"{report.get('result')} peers={summary.get('ready_peer_count')}/{summary.get('enabled_peer_count')} requests={summary.get('ok_request_count')}/{summary.get('request_count')}")
        for request in report.get("requests") or []:
            http = request.get("http") or {}
            err = request.get("error") or {}
            print(f"- {request.get('request_id')} {request.get('stage')} {request.get('outcome')} http={http.get('status')} elapsed={request.get('elapsed_ms')}ms error={err.get('type') or ''}")
    return 0 if report.get("ok") else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="North Star AI Bridge endpoint state helper")
    parser.add_argument("command", choices=["write", "endpoint", "report", "probe", "binding", "init-host", "cluster-doctor"])
    parser.add_argument("--root", default="auto")
    parser.add_argument("--workspace-config", default="")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--machine-id", default="")
    parser.add_argument("--cluster-id", default="")
    parser.add_argument("--machine-role", default="")
    parser.add_argument("--public-origin", default="")
    parser.add_argument("--advertised-origin", default="")
    parser.add_argument("--endpoint-path", default="")
    parser.add_argument("--peer", action="append", default=[])
    parser.add_argument("--mode", default="http")
    parser.add_argument("--endpoint")
    parser.add_argument("--started-at")
    parser.add_argument("--write-enabled", action="store_true")
    parser.add_argument("--tunnel-kind", default="none")
    parser.add_argument("--tunnel-name", default="")
    parser.add_argument("--tunnel-target", default="")
    parser.add_argument("--url")
    parser.add_argument("--timeout", default="1.0")
    parser.add_argument("--json", dest="print_json", action="store_true")
    parser.add_argument("--skip-status", action="store_true")
    parser.add_argument("--include-disabled", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "write":
        return write_state(args)
    if args.command == "endpoint":
        return endpoint(args)
    if args.command == "report":
        return report(args)
    if args.command == "probe":
        return probe(args)
    if args.command == "cluster-doctor":
        return cluster_doctor(args)
    if args.command == "binding":
        return print_binding(args)
    if args.command == "init-host":
        return init_host(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
