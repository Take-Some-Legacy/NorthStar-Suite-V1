from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List

from . import access
from .auth import forget_key, openai_env, openai_status, write_cached_key
from .console import emit
from .config_loader import load_config_json
from .contracts import BRIDGE_VERSION, DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT, BridgeContext, BridgeError
from .paths import find_root
from .mcp_routes import load_mcp_route_profile
from .host_binding import resolve_host_binding
from .workspace_config import apply_workspace_environment, load_workspace_config, resolve_tool_root, resolve_workspace_root
from .registry import build_tools
from .rpc import handle_rpc
from .server import Handler, run_http

TRUSTED_WRITE_MODES = {"write", "trusted_write", "operator_trusted_write", "autonomous", "trusted", "sudo"}
READ_ONLY_MODES = {"read", "readonly", "read_only", "safe_read"}


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _load_bridge_config(root: Path, tool_root: Path | None = None) -> Dict[str, Any]:
    loaded = load_config_json(root, "ai_bridge.v1.json", operator_root=tool_root)
    return loaded.with_metadata() if loaded.data else {}


def _truthy_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "force", "sudo"}


def _config_policy(config: Dict[str, Any]) -> Dict[str, Any]:
    policy = config.get("operator_policy")
    if isinstance(policy, dict):
        return policy
    autonomy = config.get("operator_autonomy")
    if isinstance(autonomy, dict):
        return autonomy
    return {}


def _config_requests_sudo(config: Dict[str, Any]) -> bool:
    if _truthy_value(config.get("sudo")):
        return True
    mode = str(config.get("default_mode", "")).strip().lower()
    policy = _config_policy(config)
    policy_mode = str(policy.get("mode", "")).strip().lower()
    return mode == "sudo" or policy_mode == "sudo" or _truthy_value(policy.get("sudo"))


def _config_requests_write(config: Dict[str, Any]) -> bool:
    force_write = config.get("forceWrite")
    if isinstance(force_write, bool):
        return force_write

    mode = str(config.get("default_mode", "read_only")).strip().lower()
    policy = _config_policy(config)
    policy_mode = str(policy.get("mode", "")).strip().lower()
    policy_write = _truthy_value(policy.get("write"))
    return mode in TRUSTED_WRITE_MODES or policy_mode in TRUSTED_WRITE_MODES or policy_write


def run_stdio(ctx: BridgeContext) -> int:
    tools = build_tools(ctx)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error", "data": {"message": str(exc)}}}
        else:
            response = handle_rpc(ctx, tools, request)
        if response is not None:
            sys.stdout.write(json_dumps(response) + "\n")
            sys.stdout.flush()
    return 0


def run_once(ctx: BridgeContext, tool_name: str, tool_args: Dict[str, Any]) -> int:
    tools = build_tools(ctx)
    if tool_name not in tools:
        print(json.dumps({"ok": False, "error": "unknown_tool", "tool": tool_name, "available": sorted(tools)}, ensure_ascii=False, indent=2))
        return 2
    try:
        emit("TOOL", "one-shot call", tool=tool_name, write=ctx.write_enabled)
        result = tools[tool_name].handler(tool_args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except BridgeError as exc:
        print(json.dumps({"ok": False, "error": exc.code, "message": str(exc), **exc.data}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


def run_hello(ctx: BridgeContext) -> int:
    tools = build_tools(ctx)
    print("North Star AI Bridge")
    print(f"  version       : {BRIDGE_VERSION}")
    print("  layout        : split package")
    print(f"  write_enabled : {ctx.write_enabled}")
    print(f"  root          : {ctx.root}")
    if ctx.host_binding:
        print(f"  machine       : {ctx.host_binding.machine_id}")
        print(f"  cluster       : {ctx.host_binding.cluster_id}")
        print(f"  endpoint      : {ctx.host_binding.endpoint_url}")
        print(f"  peers         : {len(ctx.host_binding.peers)}")
    print(f"  tools         : {len(tools)}")
    print()
    print("Operator mode:")
    print("  default       : trusted write, no per-edit prompt")
    print("  safety        : safe roots + no parent traversal + backups")
    print("  read-only     : aiBridge.bat read")
    print()
    print("Use:")
    print("  aiBridge.bat stdio")
    print("  aiBridge.bat http")
    print("  aiBridge.bat status")
    print("  aiBridge.bat read")
    print("  aiBridge.bat --tool northstar.status")
    return 0


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="North Star AI Bridge split-package CLI")
    parser.add_argument("--root", default="auto")
    parser.add_argument("--workspace-config", default="")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("-sudo", action="store_true", help="Run in sudo mode: enable bridge writes and Suite-owned confirmations.")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--machine-id", default="", help="Stable identity of this Suite machine for cluster membership.")
    parser.add_argument("--host-id", default="", help="Alias for --machine-id kept for older launchers.")
    parser.add_argument("--cluster-id", default="", help="Cluster/federation id. One Suite still runs on one machine.")
    parser.add_argument("--machine-role", default="", help="Role of this Suite machine inside a federated cluster, e.g. primary or worker.")
    parser.add_argument("--public-origin", default="", help="Externally reachable origin for this machine, for example a tunnel/domain.")
    parser.add_argument("--advertised-origin", default="", help="Origin advertised to peers/clients when different from public-origin.")
    parser.add_argument("--endpoint-path", default="", help="MCP endpoint path exposed by this machine.")
    parser.add_argument("--peer", action="append", default=[], help="Remote Suite peer as machine-id=https://origin or https://origin. Repeatable.")
    parser.add_argument("--status-interval", type=int, default=30)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--hello", action="store_true")
    parser.add_argument("--tool")
    parser.add_argument("--args-json", default="{}")
    parser.add_argument("--openai-login", action="store_true")
    parser.add_argument("--openai-forget", action="store_true")
    parser.add_argument("--require-openai-key", action="store_true")

    ns, extras = parser.parse_known_args(argv)
    aliases = {
        "http": "http",
        "server": "http",
        "mcp": "http",
        "stdio": "stdio",
        "status": "hello",
        "hello": "hello",
        "write": "write",
        "trusted": "write",
        "sudo": "sudo",
        "read": "read_only",
        "readonly": "read_only",
        "read-only": "read_only",
    }
    unexpected: List[str] = []
    for item in extras:
        target = aliases.get(item.lower().lstrip("-"))
        if target:
            setattr(ns, target, True)
        else:
            unexpected.append(item)
    if unexpected:
        parser.error("unrecognized arguments: " + " ".join(unexpected))
    return ns



def _confirm_trusted_connection(root: Path, *, requested_write: bool, interactive: bool) -> bool:
    if not requested_write:
        return False
    if access.token_path(root).exists():
        token = access.ensure_token(root)
        print(f"[OK] Trusted bridge token found: {access.token_fingerprint(token)}")
        return True
    auto_trust = _truthy_value(os.environ.get("NORTHSTAR_BRIDGE_AUTO_TRUST"))
    if auto_trust:
        token = access.ensure_token(root)
        print(f"[OK] Trusted bridge token auto-created for local operator session: {access.token_fingerprint(token)}")
        return True
    if not interactive:
        print("[WARN] Bridge write/sudo requested but no trusted token exists and stdin is not interactive; write mode disabled.")
        return False
    print("North Star Bridge requests trusted local workspace access.")
    print("This will create .takesome/authority/bridge_access_token.txt for future connections.")
    answer = input("Trust this connection? (y/n) > ").strip().lower()
    if answer not in {"y", "yes"}:
        print("[WARN] Connection not trusted; write mode disabled.")
        return False
    token = access.ensure_token(root)
    print(f"[OK] Trusted bridge connection recorded: {access.token_fingerprint(token)}")
    return True

def _console_command_loop(ctx: BridgeContext) -> None:
    """Tiny operator console loop for the local bridge window.

    It intentionally uses a simple Linux-style prompt so the owner can approve
    local trust and inspect bridge state without restarting the origin.
    """
    print("North Star Bridge console ready. Type 'help' for commands.")
    while True:
        try:
            print("> ", end="", flush=True)
            line = sys.stdin.readline()
        except Exception as exc:
            emit("WARN", "console input stopped", error=f"{type(exc).__name__}: {exc}")
            return
        if not line:
            return
        command = line.strip().lower()
        if not command:
            continue
        if command in {"help", "?"}:
            print("commands: help, status, trust, token, read, write, quit")
            continue
        if command == "status":
            token = access.ensure_token(ctx.root)
            print(json.dumps({
                "ok": True,
                "write_enabled": ctx.write_enabled,
                "sudo": ctx.sudo,
                "token": access.token_fingerprint(token),
                "root": str(ctx.root),
                "host_binding": ctx.host_binding.as_dict() if ctx.host_binding else None,
            }, ensure_ascii=False, indent=2))
            continue
        if command in {"trust", "authorize", "auth"}:
            token = access.ensure_token(ctx.root)
            ctx.write_enabled = True
            ctx.sudo = True
            os.environ["NORTHSTAR_SUITE_SUDO"] = "1"
            os.environ.setdefault("NORTHSTAR_SUITE_SUDO_REASON", "console")
            print(f"[OK] trusted local connection: {access.token_fingerprint(token)}")
            continue
        if command == "token":
            token = access.ensure_token(ctx.root)
            print(f"bridge token: {access.token_fingerprint(token)}")
            continue
        if command in {"read", "readonly", "read-only"}:
            ctx.write_enabled = False
            ctx.sudo = False
            print("[OK] bridge switched to read-only for this session")
            continue
        if command in {"write", "sudo"}:
            token = access.ensure_token(ctx.root)
            ctx.write_enabled = True
            ctx.sudo = True
            os.environ["NORTHSTAR_SUITE_SUDO"] = "1"
            os.environ.setdefault("NORTHSTAR_SUITE_SUDO_REASON", "console")
            print(f"[OK] bridge write/sudo enabled: {access.token_fingerprint(token)}")
            continue
        if command in {"quit", "exit"}:
            print("[INFO] console loop stopped; bridge keeps running")
            return
        print(f"[WARN] unknown command: {command}")


def make_context(ns: argparse.Namespace) -> BridgeContext:
    launch_root = Path.cwd().resolve()
    workspace_config = load_workspace_config(launch_root, getattr(ns, "workspace_config", ""))
    resolved_root = resolve_workspace_root(launch_root, getattr(ns, "root", "auto"), workspace_config)
    resolved_tool_root = resolve_tool_root(launch_root, workspace_config)
    apply_workspace_environment(resolved_root, workspace_config, resolved_tool_root)
    root = find_root(resolved_root)
    tool_root = find_root(resolved_tool_root)
    host_binding = resolve_host_binding(
        root,
        tool_root,
        cli_host=getattr(ns, "host", None),
        cli_port=getattr(ns, "port", None),
        cli_machine_id=getattr(ns, "machine_id", "") or getattr(ns, "host_id", ""),
        cli_cluster_id=getattr(ns, "cluster_id", ""),
        cli_machine_role=getattr(ns, "machine_role", ""),
        cli_public_origin=getattr(ns, "public_origin", ""),
        cli_advertised_origin=getattr(ns, "advertised_origin", ""),
        cli_endpoint_path=getattr(ns, "endpoint_path", ""),
        cli_peer=getattr(ns, "peer", []),
    )
    os.environ["NORTHSTAR_SUITE_MACHINE_ID"] = host_binding.machine_id
    os.environ["NORTHSTAR_SUITE_CLUSTER_ID"] = host_binding.cluster_id
    os.environ["NORTHSTAR_BRIDGE_BIND_HOST"] = host_binding.bind_host
    os.environ["NORTHSTAR_BRIDGE_BIND_PORT"] = str(host_binding.bind_port)
    os.environ["NORTHSTAR_MCP_ENDPOINT_PATH"] = host_binding.endpoint_path
    os.environ["NORTHSTAR_BRIDGE_PUBLIC_ORIGIN"] = host_binding.public_origin
    os.environ["NORTHSTAR_BRIDGE_ADVERTISED_ORIGIN"] = host_binding.advertised_origin
    os.environ["NORTHSTAR_SUITE_MACHINE_ROLE"] = host_binding.role
    mcp_routes = load_mcp_route_profile(root, operator_root=tool_root)
    config = _load_bridge_config(root, tool_root)
    env_write = os.environ.get("NORTHSTAR_AI_BRIDGE_WRITE") == "1"
    env_read = os.environ.get("NORTHSTAR_AI_BRIDGE_READ_ONLY") == "1"
    env_sudo = os.environ.get("NORTHSTAR_SUITE_SUDO", "").strip().lower() in {"1", "true", "yes", "y", "on", "force", "sudo"}
    env_bridge_sudo = os.environ.get("NORTHSTAR_BRIDGE_SUDO", "").strip().lower() in {"1", "true", "yes", "y", "on", "force", "sudo"}
    config_sudo = _config_requests_sudo(config)
    sudo = bool(getattr(ns, "sudo", False) or env_sudo or env_bridge_sudo or config_sudo)
    if sudo:
        os.environ["NORTHSTAR_SUITE_SUDO"] = "1"
        os.environ.setdefault("NORTHSTAR_SUITE_SUDO_REASON", "bridge")
        os.environ.setdefault("NORTHSTAR_BRIDGE_SUDO", "1")
    trusted_by_config = _config_requests_write(config)
    requested_write = bool(ns.write or sudo or env_write or trusted_by_config)
    interactive = (not ns.stdio) and sys.stdin.isatty()
    trusted_connection = _confirm_trusted_connection(root, requested_write=requested_write, interactive=interactive)
    write_enabled = requested_write and trusted_connection
    if bool(ns.read_only or env_read):
        write_enabled = False
    return BridgeContext(root=root, write_enabled=write_enabled, python_cmd=[sys.executable], interactive=interactive, sudo=sudo and trusted_connection, mcp_routes=mcp_routes, tool_root=tool_root, host_binding=host_binding)


def main(argv: List[str]) -> int:
    ns = parse_args(argv)
    ctx = make_context(ns)

    if ns.openai_login:
        key = getpass.getpass("Enter OpenAI API key: ").strip()
        write_cached_key(ctx, key)
        print(json.dumps({"ok": True, "source": "cache", "cache_path": ".takesome/secrets/openai_api_key.local"}, ensure_ascii=False, indent=2))
        return 0
    if ns.openai_forget:
        print(json.dumps(forget_key(ctx), ensure_ascii=False, indent=2))
        return 0
    if ns.require_openai_key:
        openai_env(ctx, True)
        print(json.dumps({"ok": True, **openai_status(ctx)}, ensure_ascii=False, indent=2))
        return 0
    if ns.tool:
        try:
            tool_args = json.loads(ns.args_json)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": "invalid_args_json", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
        return run_once(ctx, ns.tool, tool_args)
    if ns.stdio:
        return run_stdio(ctx)
    if ns.http:
        if ctx.interactive:
            threading.Thread(target=_console_command_loop, args=(ctx,), daemon=True).start()
        binding = ctx.host_binding
        return run_http(ctx, binding.bind_host if binding else DEFAULT_HTTP_HOST, binding.bind_port if binding else DEFAULT_HTTP_PORT, ns.status_interval)
    return run_hello(ctx)


__all__ = ["main", "run_stdio", "run_once", "run_hello", "run_http", "Handler", "build_tools"]
