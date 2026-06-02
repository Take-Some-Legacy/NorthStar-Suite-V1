from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from .auth import forget_key, openai_env, openai_status, write_cached_key
from .console import emit
from .contracts import BRIDGE_VERSION, DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT, BridgeContext, BridgeError
from .paths import find_root
from .registry import build_tools
from .rpc import handle_rpc
from .server import Handler, run_http

TRUSTED_WRITE_MODES = {"write", "trusted_write", "operator_trusted_write", "autonomous", "trusted"}
READ_ONLY_MODES = {"read", "readonly", "read_only", "safe_read"}


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _load_bridge_config(root: Path) -> Dict[str, Any]:
    path = root / "config" / "suite" / "ai_bridge.v1.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception as exc:
        return {"_config_error": str(exc)}


def _config_requests_write(config: Dict[str, Any]) -> bool:
    force_write = config.get("forceWrite")
    if isinstance(force_write, bool):
        return force_write

    mode = str(config.get("default_mode", "read_only")).strip().lower()
    autonomy = config.get("operator_autonomy") or {}
    autonomy_mode = str(autonomy.get("mode", "")).strip().lower() if isinstance(autonomy, dict) else ""
    return mode in TRUSTED_WRITE_MODES or autonomy_mode in TRUSTED_WRITE_MODES


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
    parser.add_argument("--root", default=".")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("-y", "--yes", "--assume-yes", action="store_true", help="Run in sudo mode: enable bridge writes and assume yes for Suite-owned confirmations.")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--host", default=DEFAULT_HTTP_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT)
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
        "yes": "yes",
        "assume-yes": "yes",
        "sudo": "yes",
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


def make_context(ns: argparse.Namespace) -> BridgeContext:
    root = find_root(Path(ns.root))
    config = _load_bridge_config(root)
    env_write = os.environ.get("NORTHSTAR_AI_BRIDGE_WRITE") == "1"
    env_read = os.environ.get("NORTHSTAR_AI_BRIDGE_READ_ONLY") == "1"
    env_yes = os.environ.get("NORTHSTAR_SUITE_YES", "").strip().lower() in {"1", "true", "yes", "y", "on", "force"}
    assume_yes = bool(getattr(ns, "yes", False) or env_yes)
    if assume_yes:
        os.environ["NORTHSTAR_SUITE_YES"] = "1"
        os.environ.setdefault("NORTHSTAR_SUITE_YES_REASON", "bridge")
    trusted_by_config = _config_requests_write(config)
    write_enabled = bool(ns.write or assume_yes or env_write or trusted_by_config)
    if bool(ns.read_only or env_read):
        write_enabled = False
    interactive = (not ns.stdio) and sys.stdin.isatty()
    return BridgeContext(root=root, write_enabled=write_enabled, python_cmd=[sys.executable], interactive=interactive, assume_yes=assume_yes)


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
        return run_http(ctx, ns.host, ns.port, ns.status_interval)
    return run_hello(ctx)


__all__ = ["main", "run_stdio", "run_once", "run_hello", "run_http", "Handler", "build_tools"]
