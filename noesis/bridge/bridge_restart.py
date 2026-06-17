from __future__ import annotations

import subprocess
import sys
import time
from typing import Any, Dict, List

from .console import emit
from .contracts import BridgeContext, BridgeError
from .paths import rel, truncate

_ALLOWED_COMMANDS = {"preflight", "status", "stop-origin", "wait-down", "wait-up"}


def _restart_helper_path(ctx: BridgeContext):
    """Resolve canonical NOESIS restart helper from the Suite root."""
    return ctx.operator_root / "noesis" / "bridge" / "restart_cli.py"


def _helper_rel(ctx: BridgeContext, helper):
    try:
        return rel(ctx.operator_root, helper)
    except Exception:
        return str(helper)


def bridge_restart(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Run safe local-origin bridge restart helper.

    This intentionally delegates only to the canonical noesis.bridge.restart_cli
    helper and only for its allow-listed commands. The helper itself refuses to kill
    cloudflared or non-bridge listeners.
    """
    command = str(args.get("command", "status")).strip().lower()
    if command not in _ALLOWED_COMMANDS:
        raise BridgeError("unsupported bridge restart command", "invalid_restart_command", {"command": command, "allowed": sorted(_ALLOWED_COMMANDS)})
    helper = _restart_helper_path(ctx)
    if not helper.exists():
        raise BridgeError("AI bridge restart helper is missing", "restart_helper_missing", {"path": _helper_rel(ctx, helper)})
    port = int(args.get("port", 8797))
    host = str(args.get("host", "127.0.0.1"))
    timeout = float(args.get("timeout", 1.0))
    wait_sec = float(args.get("wait_sec", 30.0))
    cmd: List[str] = [*ctx.python_cmd, "-m", "noesis", "bridge-restart", command, "--root", str(ctx.root), "--host", host, "--port", str(port), "--timeout", str(timeout), "--wait-sec", str(wait_sec)]
    if bool(args.get("dry_run", False)):
        cmd.append("--dry-run")
    emit("BRIDGE", "restart helper", command=command, host=host, port=port, dry_run=bool(args.get("dry_run", False)))
    started = time.time()
    proc = subprocess.run(cmd, cwd=str(ctx.operator_root), text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, timeout=max(5, int(wait_sec) + 10))
    out, ot = truncate(proc.stdout)
    err, et = truncate(proc.stderr)
    result = {"ok": proc.returncode == 0, "exit_code": proc.returncode, "elapsed_ms": int((time.time() - started) * 1000), "command": command, "stdout": out, "stderr": err, "truncated": ot or et}
    emit("BRIDGE", "restart helper result", command=command, ok=result["ok"], exit_code=proc.returncode, elapsed_ms=result["elapsed_ms"])
    return result



def bridge_reload_origin(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Schedule a safe detached reload of the local HTTP bridge origin.

    This command is designed for AI/operator clients that are currently using
    the HTTP origin they need to reload. A synchronous stop can kill the request
    before the caller receives a result and look like a stream failure. This
    schedules a detached helper with a short delay, returns a typed result, then
    stops only the recognized North Star AI Bridge HTTP origin and writes a
    report artifact. The public tunnel/cloudflared process is never stopped.
    """
    if not ctx.write_enabled:
        raise BridgeError("bridge origin reload requires write mode", "write_disabled")

    helper = _restart_helper_path(ctx)
    if not helper.exists():
        raise BridgeError("AI bridge restart helper is missing", "restart_helper_missing", {"path": _helper_rel(ctx, helper)})

    port = int(args.get("port", 8797))
    host = str(args.get("host", "127.0.0.1"))
    timeout = float(args.get("timeout", 1.0))
    wait_sec = float(args.get("wait_sec", 30.0))
    delay_sec = max(0.5, min(float(args.get("delay_sec", 1.5)), 15.0))
    dry_run = bool(args.get("dry_run", False))

    reports = ctx.root / ".takesome" / "ai-bridge" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    report = reports / f"bridge-origin-reload-{stamp}.json"

    helper_source = 'import json\nimport subprocess\nimport sys\nimport time\nfrom pathlib import Path\n\nhelper, root, host, port, timeout, wait_sec, delay_sec, dry_run, report = sys.argv[1:]\ntime.sleep(float(delay_sec))\nbase = [sys.executable, helper]\ncommon = ["--root", root, "--host", host, "--port", port, "--timeout", timeout, "--wait-sec", wait_sec]\nsteps = []\ncommands = ("preflight", "status") if dry_run == "1" else ("preflight", "status", "stop-origin", "wait-down", "wait-up")\nfor command in commands:\n    argv = [*base, command, *common]\n    started = time.time()\n    proc = subprocess.run(argv, cwd=root, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)\n    steps.append({\n        "command": command,\n        "exit_code": proc.returncode,\n        "elapsed_ms": int((time.time() - started) * 1000),\n        "stdout_tail": proc.stdout[-8192:],\n        "stderr_tail": proc.stderr[-8192:],\n    })\n    if proc.returncode != 0:\n        break\npayload = {\n    "schema": "northstar.bridge.origin_reload_report.v1",\n    "ok": all(step["exit_code"] == 0 for step in steps),\n    "host": host,\n    "port": int(port),\n    "dry_run": dry_run == "1",\n    "steps": steps,\n    "cloudflared_policy": "preserve: this helper never stops cloudflared or tunnel processes",\n    "restart_policy": "preflight -> status -> stop-origin -> wait-down -> wait-up; dry-run performs preflight -> status only",\n}\nPath(report).parent.mkdir(parents=True, exist_ok=True)\nPath(report).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")'
    command = [
        sys.executable,
        "-c",
        helper_source,
        str(helper),
        str(ctx.root),
        host,
        str(port),
        str(timeout),
        str(wait_sec),
        str(delay_sec),
        "1" if dry_run else "0",
        str(report),
    ]
    popen_kwargs: Dict[str, Any] = {
        "cwd": str(ctx.operator_root),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "shell": False,
    }
    if sys.platform.startswith("win"):
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(command, **popen_kwargs)
    emit("BRIDGE", "origin reload scheduled", pid=proc.pid, host=host, port=port, delay_sec=delay_sec, dry_run=dry_run)
    return {
        "schema": "northstar.bridge.reload_origin.v1",
        "ok": True,
        "scheduled": True,
        "pid": proc.pid,
        "host": host,
        "port": port,
        "delay_sec": delay_sec,
        "wait_sec": wait_sec,
        "dry_run": dry_run,
        "report_path": rel(ctx.root, report),
        "note": "Detached reload scheduled. The current HTTP stream may disconnect after the response; reconnect to the MCP endpoint after the supervisor restarts the origin.",
    }


def bridge_restart_sequence(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    """Run a bounded restart sequence for local HTTP origin.

    Sequence: preflight -> status -> stop-origin -> wait-down. wait-up is intentionally not
    performed unless the caller starts a new process outside this old origin;
    stopping the current process cannot also bring itself back.
    """
    if not ctx.write_enabled:
        raise BridgeError("bridge restart sequence requires write mode", "write_disabled")
    steps = []
    commands = ("preflight", "status") if dry_run else ("preflight", "status", "stop-origin", "wait-down", "wait-up")
    for command in commands:
        step = bridge_restart(ctx, {**args, "command": command})
        steps.append(step)
        if not step.get("ok"):
            break
    ok = all(bool(step.get("ok")) for step in steps)
    emit("BRIDGE", "restart requested", status="ok" if ok else "failed", steps=len(steps))
    return {"ok": ok, "steps": steps, "note": "Restart sequence verified: virtual origin preflight passed, local origin stopped, went down, then came back up; cloudflared/tunnel is preserved."}
