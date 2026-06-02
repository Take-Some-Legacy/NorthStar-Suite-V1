#!/usr/bin/env python3
"""Endpoint state helper for North Star AI Bridge launchers."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict

DEFAULT_ENDPOINT = "http://127.0.0.1:8797/mcp"


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _root(path: str) -> Path:
    return Path(path).resolve()


def _state_dir(root: Path) -> Path:
    return root / ".takesome" / "ai-bridge" / "state"


def _reports_dir(root: Path) -> Path:
    return root / ".takesome" / "ai-bridge" / "reports"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_report(root: Path, state: Dict[str, Any]) -> Path:
    endpoint = str(state.get("active_endpoint") or DEFAULT_ENDPOINT)
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
**Endpoint state:** .takesome/ai-bridge/state/endpoint.json
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

`aiBridge.bat tunnel` is also routed to the same supervisor. It starts the local HTTP origin and then raises the declared named tunnel/domain from `config/suite/ai_bridge.v1.json`.
"""
    path.write_text(content, encoding="utf-8")
    return path


def write_state(args: argparse.Namespace) -> int:
    root = _root(args.root)
    endpoint = args.endpoint or f"http://{args.host}:{args.port}/mcp"
    existing = _load_state(root)
    state: Dict[str, Any] = {
        "active_endpoint": endpoint,
        "mode": args.mode,
        "host": args.host,
        "port": args.port,
        "started_at": args.started_at or existing.get("started_at") or _utc_now(),
        "updated_at": _utc_now(),
        "write_enabled": bool(args.write_enabled),
        "logs_directory": ".takesome/ai-bridge/logs",
        "state_file": ".takesome/ai-bridge/state/endpoint.json",
        "report_file": ".takesome/ai-bridge/reports/CONNECT_CHATGPT.md",
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
    root = _root(args.root)
    state = _load_state(root)
    if not state:
        state = {
            "active_endpoint": DEFAULT_ENDPOINT,
            "mode": "http",
            "write_enabled": False,
            "state_file": ".takesome/ai-bridge/state/endpoint.json",
            "report_file": ".takesome/ai-bridge/reports/CONNECT_CHATGPT.md",
            "updated_at": _utc_now(),
        }
        _write_json(_state_path(root), state)
        _write_report(root, state)
    if args.print_json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(state.get("active_endpoint") or DEFAULT_ENDPOINT)
    return 0


def report(args: argparse.Namespace) -> int:
    root = _root(args.root)
    state = _load_state(root)
    if not state:
        state = {"active_endpoint": DEFAULT_ENDPOINT, "mode": "http", "write_enabled": False, "updated_at": _utc_now()}
        _write_json(_state_path(root), state)
    path = _write_report(root, state)
    print(path.relative_to(root).as_posix())
    return 0


def probe(args: argparse.Namespace) -> int:
    url = args.url or f"http://{args.host}:{args.port}/health"
    try:
        with urllib.request.urlopen(url, timeout=max(0.2, float(args.timeout))) as response:
            ok = 200 <= int(response.status) < 300
            if args.print_json:
                print(json.dumps({"ok": ok, "url": url, "status": response.status}, ensure_ascii=False, indent=2))
            return 0 if ok else 1
    except Exception as exc:
        if args.print_json:
            print(json.dumps({"ok": False, "url": url, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="North Star AI Bridge endpoint state helper")
    parser.add_argument("command", choices=["write", "endpoint", "report", "probe"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8797)
    parser.add_argument("--mode", default="http")
    parser.add_argument("--endpoint")
    parser.add_argument("--started-at")
    parser.add_argument("--write-enabled", action="store_true")
    parser.add_argument("--tunnel-kind", default="none")
    parser.add_argument("--tunnel-name", default="")
    parser.add_argument("--tunnel-target", default="http://127.0.0.1:8797")
    parser.add_argument("--url")
    parser.add_argument("--timeout", default="1.0")
    parser.add_argument("--json", dest="print_json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "write":
        return write_state(args)
    if args.command == "endpoint":
        return endpoint(args)
    if args.command == "report":
        return report(args)
    if args.command == "probe":
        return probe(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
