#!/usr/bin/env python3
"""Safe local-origin restart helper for North Star AI Bridge.

This helper intentionally touches only the local HTTP origin process bound to
127.0.0.1:8797. It must never stop cloudflared, because stopping cloudflared can
release a quick-tunnel hostname and disconnect the externally assigned domain.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8797
SAFE_MARKERS = ("northstar_ai_bridge.py", "northstar_operator_bridge.py")
FORBIDDEN_MARKERS = ("cloudflared", "cloudflared.exe")


@dataclass(frozen=True)
class Listener:
    pid: int
    local: str
    state: str
    command_line: str
    safe_bridge: bool


def _run(cmd: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        timeout=timeout,
    )


def _probe(host: str, port: int, timeout: float = 1.0) -> bool:
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 300
    except Exception:
        return False


def _netstat_listeners(port: int) -> list[tuple[int, str, str]]:
    proc = _run(["netstat", "-ano", "-p", "tcp"], timeout=10)
    rows: list[tuple[int, str, str]] = []
    needle = f":{port}"
    for raw in proc.stdout.splitlines():
        line = " ".join(raw.split())
        if not line.lower().startswith("tcp ") or needle not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[1]
        state = parts[3].upper()
        pid_text = parts[4]
        if state != "LISTENING":
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if local.endswith(needle) or local.endswith(f".{port}"):
            rows.append((pid, local, state))
    return rows


def _command_line(pid: int) -> str:
    ps = _run([
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\"; if ($p) {{ $p.CommandLine }}",
    ], timeout=10)
    text = (ps.stdout or "").strip()
    if text:
        return text
    wmic = _run(["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/VALUE"], timeout=10)
    for line in (wmic.stdout or "").splitlines():
        if line.startswith("CommandLine="):
            return line.split("=", 1)[1].strip()
    return ""


def _listeners(port: int) -> list[Listener]:
    result: list[Listener] = []
    for pid, local, state in _netstat_listeners(port):
        cmd = _command_line(pid)
        low = cmd.lower()
        forbidden = any(marker in low for marker in FORBIDDEN_MARKERS)
        safe = (not forbidden) and any(marker in low for marker in SAFE_MARKERS) and "--http" in low
        result.append(Listener(pid=pid, local=local, state=state, command_line=cmd, safe_bridge=safe))
    return result


def _kill_origin(port: int, dry_run: bool = False) -> Dict[str, Any]:
    listeners = _listeners(port)
    unsafe = [x for x in listeners if not x.safe_bridge]
    safe = [x for x in listeners if x.safe_bridge]
    killed: list[dict[str, Any]] = []
    if unsafe:
        return {
            "ok": False,
            "error": "unsafe_listener",
            "message": "Port is occupied by a process that is not recognized as North Star AI Bridge HTTP origin. Refusing to kill it.",
            "listeners": [x.__dict__ for x in listeners],
        }
    for item in safe:
        if dry_run:
            killed.append({"pid": item.pid, "dry_run": True})
            continue
        proc = _run(["taskkill", "/PID", str(item.pid), "/F"], timeout=10)
        killed.append({"pid": item.pid, "exit_code": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()})
    return {"ok": True, "killed": killed, "listeners": [x.__dict__ for x in listeners]}


def cmd_preflight(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    bridge = root / "tools" / "scripts" / "northstar_ai_bridge.py"
    if not bridge.exists():
        print(json.dumps({"ok": False, "error": "missing_bridge_entrypoint", "path": str(bridge)}, ensure_ascii=False, indent=2))
        return 1
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NORTHSTAR_SUITE_STDIO_ENCODING": "utf-8",
        "NORTHSTAR_SUITE_STDIO_ERRORS": "replace",
    })
    cmd = [sys.executable, str(bridge), "--root", str(root), "--hello"]
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        timeout=max(5.0, float(args.wait_sec)),
    )
    payload = {
        "ok": proc.returncode == 0,
        "schema": "northstar.bridge.origin_preflight.v1",
        "host": args.host,
        "port": args.port,
        "command": "preflight",
        "virtual_origin": "northstar_ai_bridge.py --hello",
        "exit_code": proc.returncode,
        "elapsed_ms": int((time.time() - started) * 1000),
        "stdout_tail": proc.stdout[-8192:],
        "stderr_tail": proc.stderr[-8192:],
        "policy": "validate new bridge code before stopping the live origin",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def cmd_status(args: argparse.Namespace) -> int:
    listeners = _listeners(args.port)
    payload = {
        "ok": True,
        "host": args.host,
        "port": args.port,
        "responding": _probe(args.host, args.port, args.timeout),
        "listeners": [x.__dict__ for x in listeners],
        "cloudflared_policy": "preserve: this helper never stops cloudflared or tunnel processes",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_stop_origin(args: argparse.Namespace) -> int:
    payload = _kill_origin(args.port, dry_run=args.dry_run)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def cmd_wait_down(args: argparse.Namespace) -> int:
    deadline = time.time() + args.wait_sec
    while time.time() < deadline:
        if not _probe(args.host, args.port, args.timeout):
            print(json.dumps({"ok": True, "state": "down", "port": args.port}, ensure_ascii=False, indent=2))
            return 0
        time.sleep(0.25)
    print(json.dumps({"ok": False, "error": "still_responding", "port": args.port}, ensure_ascii=False, indent=2))
    return 1


def cmd_wait_up(args: argparse.Namespace) -> int:
    deadline = time.time() + args.wait_sec
    while time.time() < deadline:
        if _probe(args.host, args.port, args.timeout):
            print(json.dumps({"ok": True, "state": "up", "endpoint": f"http://{args.host}:{args.port}/mcp"}, ensure_ascii=False, indent=2))
            return 0
        time.sleep(0.5)
    print(json.dumps({"ok": False, "error": "not_responding", "endpoint": f"http://{args.host}:{args.port}/mcp"}, ensure_ascii=False, indent=2))
    return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Safe local-origin restart helper for North Star AI Bridge")
    parser.add_argument("command", choices=["preflight", "status", "stop-origin", "wait-down", "wait-up"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--wait-sec", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    # Keep root validation simple; this helper intentionally operates on the
    # local port/process table, not on repository files.
    Path(args.root).resolve()
    if args.command == "preflight":
        return cmd_preflight(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "stop-origin":
        return cmd_stop_origin(args)
    if args.command == "wait-down":
        return cmd_wait_down(args)
    if args.command == "wait-up":
        return cmd_wait_up(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
