from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional


def _truthy(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "да"}:
        return True
    if text in {"0", "false", "no", "n", "off", "нет"}:
        return False
    return default


def _section(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("dashboard") if isinstance(config, dict) else {}
    return value if isinstance(value, dict) else {}


def enabled(config: dict[str, Any]) -> bool:
    override = os.environ.get("NOESIS_DASHBOARD_AUTOSTART")
    if override is not None and override.strip() != "":
        return _truthy(override, False)
    section = _section(config)
    value = config.get("useDashboard") if isinstance(config, dict) else None
    if value is None:
        value = section.get("useDashboard") if "useDashboard" in section else section.get("enabled")
    return _truthy(value, False)


def host_port(config: dict[str, Any]) -> tuple[str, int]:
    section = _section(config)
    host = os.environ.get("NOESIS_DASHBOARD_HOST") or str(section.get("host") or "127.0.0.1")
    raw_port = os.environ.get("NOESIS_DASHBOARD_PORT") or section.get("port") or 8798
    try:
        port = int(raw_port)
    except Exception:
        port = 8798
    return host.strip() or "127.0.0.1", max(1, min(65535, port))


def open_on_start(config: dict[str, Any]) -> bool:
    override = os.environ.get("NOESIS_DASHBOARD_OPEN_ON_START")
    if override is not None and override.strip() != "":
        return _truthy(override, False)
    section = _section(config)
    value = section.get("openOnStart") if "openOnStart" in section else section.get("open_on_start")
    return _truthy(value, False)


def url(config: dict[str, Any]) -> str:
    host, port = host_port(config)
    return f"http://{host}:{port}/"


def health_url(config: dict[str, Any]) -> str:
    return url(config).rstrip("/") + "/api/health"


def spawn(root: Path, tool_root: Path, config: dict[str, Any], *, q: Any, emit: Any, probe: Any, start_process: Any, drain_logs: Any, stop_processes: Any, utc_now: Any) -> Optional[subprocess.Popen[str]]:
    if not enabled(config):
        emit("STATE", "NOESIS Dashboard autostart disabled", config="useDashboard=false")
        return None
    target = url(config)
    health = health_url(config)
    if probe(health, timeout=1.0):
        emit("OK", "NOESIS Dashboard already responds", url=target)
        return None
    host, port = host_port(config)
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "NORTHSTAR_WORKSPACE_ROOT": str(root),
        "NORTHSTAR_SUITE_WORKSPACE_ROOT": str(root),
        "NORTHSTAR_TOOL_ROOT": str(tool_root),
        "NORTHSTAR_SUITE_TOOL_ROOT": str(tool_root),
    })
    cmd = [sys.executable, "-m", "noesis", "runs", "serve", "--host", host, "--port", str(port)]
    if open_on_start(config):
        cmd.append("--open")
    emit("INFO", "starting NOESIS Dashboard", command="python -m noesis runs serve", url=target, config="useDashboard=true")
    proc = start_process("dashboard", cmd, tool_root, env, q)
    deadline = time.time() + 12
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"dashboard exited before readiness, exit_code={proc.returncode}")
        if probe(health, timeout=1.0):
            try:
                state_dir = root / ".noesis" / "dashboard"
                state_dir.mkdir(parents=True, exist_ok=True)
                (state_dir / "server.json").write_text(json.dumps({
                    "schema": "noesis.dashboard.server.v1",
                    "url": target,
                    "health": health,
                    "pid": proc.pid,
                    "started_at": utc_now(),
                    "source": "serverBridge",
                    "useDashboard": True,
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except Exception:
                pass
            emit("OK", "NOESIS Dashboard is ready", url=target)
            return proc
        drain_logs(q, nonblocking=True)
        time.sleep(0.25)
    stop_processes([proc])
    raise RuntimeError(f"dashboard did not become ready at {health}")


def ensure_alive(root: Path, tool_root: Path, proc: Optional[subprocess.Popen[str]], config: dict[str, Any], *, q: Any, emit: Any, probe: Any, spawn_func: Any) -> Optional[subprocess.Popen[str]]:
    if not enabled(config):
        return proc
    if proc is not None and proc.poll() is None:
        return proc
    if probe(health_url(config), timeout=1.0):
        return proc
    if proc is not None:
        emit("WARN", "NOESIS Dashboard exited; restarting", exit_code=proc.returncode)
    return spawn_func(root, tool_root, config, q=q)
