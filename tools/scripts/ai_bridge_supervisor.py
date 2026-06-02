#!/usr/bin/env python3
"""One-window North Star MCP origin + Cloudflare tunnel supervisor.

serverBridge.bat is the user-facing entrypoint. This supervisor owns both the
local HTTP MCP origin and the public tunnel process, writes endpoint state, and
keeps diagnostics in one console.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from northstar_bridge.terminal_style import (
    LOG_LEVEL_COLORS,
    bracket as _bracket,
    color,
    enable_windows_ansi as _enable_windows_ansi,
    level_color as _level_color,
    strip_ansi as _strip_ansi,
    style,
)
from northstar_bridge.supervisor_footer import (
    bind as _footer_bind,
    clear as _footer_clear_locked,
    mark as _footer_mark,
    observe_stream as _footer_observe_stream,
    observe_supervisor_event as _footer_observe_supervisor_event,
    print_line as _footer_print,
    restore_layout as _footer_restore_layout_locked,
    tick as _footer_tick,
)

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 8797
LOCAL_ORIGIN = f"http://{LOCAL_HOST}:{LOCAL_PORT}"
LOCAL_MCP = f"{LOCAL_ORIGIN}/mcp"
LOCAL_HEALTH = f"{LOCAL_ORIGIN}/health"
BRIDGE_CONFIG_REL = Path("config") / "suite" / "ai_bridge.v1.json"
BRIDGE_PUBLIC_ORIGIN_CONFIG_REL = Path("config") / "suite" / "bridge_public_origin.v1.json"
URL_RE = re.compile(r"https://[-a-zA-Z0-9]+\.trycloudflare\.com")
SUPERVISOR_VERSION = "0.2.1"
QUICK_ROUTE_TERMINAL_PATTERNS = (
    "unauthorized: tunnel not found",
    "register tunnel error from server side",
)
QUICK_ROUTE_TERMINAL_ERROR_THRESHOLD = 2


def _json_syntax_highlight(raw: str) -> str:
    token_re = re.compile(
        r'("(?:\\.|[^"\\])*"\s*:?)|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|([{}\[\],:])'
    )

    def repl(match: re.Match[str]) -> str:
        string_token, literal, number, punctuation = match.groups()
        if string_token is not None:
            return color(string_token, "cyan") if string_token.rstrip().endswith(":") else color(string_token, "green")
        if literal is not None:
            return color(literal, "magenta")
        if number is not None:
            return color(number, "yellow")
        return color(punctuation, "gray")

    return token_re.sub(repl, raw)


def _find_balanced_json_end(text: str, start: int) -> int | None:
    if start >= len(text) or text[start] not in "[{":
        return None
    stack = [text[start]]
    quote = False
    escape = False
    for index in range(start + 1, len(text)):
        ch = text[index]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                quote = False
            continue
        if ch == '"':
            quote = True
        elif ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            if not stack:
                return None
            opener = stack.pop()
            if (opener, ch) not in {("{", "}"), ("[", "]")}:
                return None
            if not stack:
                return index + 1
    return None


def _highlight_inline_json(text: str) -> str:
    fields = ("result", "args", "error_details", "payload", "response", "body")
    out: list[str] = []
    i = 0
    while i < len(text):
        best: tuple[int, str] | None = None
        for field in fields:
            pos = text.find(field + "=", i)
            if pos >= 0 and (best is None or pos < best[0]):
                best = (pos, field)
        if best is None:
            out.append(text[i:])
            break
        pos, field = best
        value_start = pos + len(field) + 1
        out.append(text[i:pos])
        out.append(color(field, "gray") + color("=", "dim"))
        if value_start < len(text) and text[value_start] in "[{":
            end = _find_balanced_json_end(text, value_start)
            if end is not None:
                out.append(_json_syntax_highlight(text[value_start:end]))
                i = end
                continue
        i = value_start
    return "".join(out)


def _highlight_key_values(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        value = match.group(2)
        value_color = "cyan" if key in {"endpoint", "url", "target", "protocol", "tool", "route", "path"} else "white"
        if key in {"status", "response_status"}:
            value_color = "green" if value.lower() in {"ok", "200", "true"} else "yellow"
        return color(key, "gray") + color("=", "dim") + color(value, value_color)

    return re.sub(r"\b([A-Za-z_][A-Za-z0-9_:-]*)=([^\s]+)", repl, text)


def _colorize_bracket_tokens(line: str) -> str:
    def repl(match: re.Match[str]) -> str:
        token = match.group(1)
        clean = token.strip()
        level = clean.split()[0].upper() if clean else ""
        if level in LOG_LEVEL_COLORS:
            return _bracket(token, _level_color(level), strong=True)
        if re.match(r"\d{2}:\d{2}:\d{2}", clean):
            return _bracket(token, "dim")
        return _bracket(token, "gray")

    return re.sub(r"\[([^\]]+)\]", repl, line)


def _colorize_origin_line(line: str) -> str:
    text = _highlight_inline_json(line)
    text = _highlight_key_values(text)
    text = _colorize_bracket_tokens(text)
    text = re.sub(r"\b(GET|POST|OPTIONS|PUT|DELETE)\b", lambda m: style(m.group(1), "blue", "bold"), text)
    text = re.sub(
        r"(->\s*)(\d{3})",
        lambda m: m.group(1) + color(m.group(2), "green" if m.group(2).startswith("2") else "yellow" if m.group(2).startswith("3") else "red"),
        text,
    )
    return text


def _colorize_cloudflared_line(line: str) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2}T\S+Z)\s+(\w+)\s+(.*)", line)
    if not match:
        return _highlight_key_values(_highlight_inline_json(_colorize_bracket_tokens(line)))
    stamp, level, message = match.groups()
    level_color = _level_color(level)
    message = _highlight_key_values(_highlight_inline_json(_colorize_bracket_tokens(message)))
    return color(stamp, "dim") + " " + style(level.ljust(3), level_color, "bold") + " " + message


def _colorize_stream_line(name: str, line: str) -> str:
    if name == "origin":
        return _colorize_origin_line(line)
    if name == "cloudflared":
        return _colorize_cloudflared_line(line)
    return _highlight_key_values(_highlight_inline_json(_colorize_bracket_tokens(line)))



def emit(level: str, message: str, **fields: object) -> None:
    _footer_observe_supervisor_event(level, message, fields)
    now = dt.datetime.now().strftime("%H:%M:%S")
    level_color = _level_color(level)
    msg_color = level_color if level.upper() in {"ERROR", "WARN"} else "bright_white"
    parts = [
        _bracket(now, "dim"),
        _bracket(level.ljust(5), level_color, strong=True),
        color(message, msg_color),
    ]
    for k, v in fields.items():
        if v is not None:
            if isinstance(v, (dict, list)):
                rendered = _json_syntax_highlight(json.dumps(v, ensure_ascii=False, separators=(",", ":")))
                parts.append(color(k, "gray") + color("=", "dim") + rendered)
            else:
                value_color = "cyan" if k in {"endpoint", "url", "mode", "target", "protocol", "tool"} else "white"
                value = str(v).replace("\r", "\\r").replace("\n", "\\n")
                parts.append(color(k, "gray") + color("=", "dim") + color(value, value_color))
    _footer_print(" ".join(parts))


_enable_windows_ansi()


@dataclass
class StableTunnelConfig:
    tunnel_name: str = ""
    tunnel_id: str = ""
    public_endpoint: str = ""
    local_origin: str = LOCAL_ORIGIN
    protocol: str = "quic"
    fallback_protocols: tuple[str, ...] = ("auto", "http2")
    source: str = ""
    route_mode: str = "named"
    quick_protocol: str = "quic"
    quick_fallback_protocols: tuple[str, ...] = ("auto", "http2")
    quick_tunnel_fallback: bool = True

    @property
    def public_url(self) -> str:
        return self.public_endpoint.rsplit("/mcp", 1)[0].rstrip("/") if self.public_endpoint else ""



@dataclass
class SuspendedCloudflaredConfig:
    original: Path
    backup: Path


class SupervisorError(RuntimeError):
    pass


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on", "force", "sudo"}


def _sudo_active() -> bool:
    return _env_truthy("NORTHSTAR_SUITE_YES") or _env_truthy("NORTHSTAR_SUITE_SUDO") or _env_truthy("NORTHSTAR_BRIDGE_SUDO")


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _as_endpoint(hostname_or_endpoint: str) -> str:
    value = (hostname_or_endpoint or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value if value.endswith("/mcp") else value + "/mcp"
    return "https://" + value + "/mcp"


def _protocol_list(value: object) -> tuple[str, ...]:
    allowed = {"auto", "http2", "quic"}
    if isinstance(value, str):
        items = [part.strip().lower() for part in value.replace(";", ",").split(",")]
    elif isinstance(value, list):
        items = [str(part).strip().lower() for part in value]
    else:
        items = []
    result: list[str] = []
    for item in items:
        if item in allowed and item not in result:
            result.append(item)
    return tuple(result)


def _normalize_route_mode(value: object) -> str:
    mode = str(value or "named").strip().lower()
    if mode in {"cloudflare_route", "cloudflare-route", "quick_route", "quick-route", "trycloudflare", "quick"}:
        return "quick"
    if mode in {"named", "stable", "named_tunnel", "named-tunnel", "cloudflare_named_tunnel"}:
        return "named"
    return "named"



def _bool_config(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"1", "true", "yes", "y", "on", "да"}:
            return True
        if clean in {"0", "false", "no", "n", "off", "нет"}:
            return False
    return default


def _as_origin(value: object, default: str = LOCAL_ORIGIN) -> str:
    text = str(value or "").strip().rstrip("/")
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return default


def _hostname_from_endpoint(endpoint: str) -> str:
    try:
        return urllib.parse.urlparse(endpoint.rsplit("/mcp", 1)[0]).hostname or ""
    except Exception:
        return ""


def load_declared_tunnel_config(root: Path) -> StableTunnelConfig:
    public_data = read_json(root / BRIDGE_PUBLIC_ORIGIN_CONFIG_REL)
    if public_data:
        mode = str(public_data.get("mode") or "").strip().lower()
        if mode in {"cloudflare_named_tunnel", "named", "stable", "named_tunnel", "named-tunnel"}:
            public_endpoint = _as_endpoint(str(public_data.get("public_origin") or public_data.get("public_endpoint") or ""))
            return StableTunnelConfig(
                tunnel_name=str(public_data.get("tunnel_name") or public_data.get("tunnel_id") or ""),
                tunnel_id=str(public_data.get("tunnel_id") or ""),
                public_endpoint=public_endpoint,
                local_origin=_as_origin(public_data.get("local_origin"), LOCAL_ORIGIN),
                protocol=str(public_data.get("protocol") or "quic").lower() if str(public_data.get("protocol") or "quic").lower() in {"auto", "http2", "quic"} else "quic",
                fallback_protocols=_protocol_list(public_data.get("fallback_protocols")) or ("auto", "http2"),
                source=str(BRIDGE_PUBLIC_ORIGIN_CONFIG_REL).replace(chr(92), "/"),
                route_mode="named",
                quick_protocol=str(public_data.get("quick_protocol") or "quic").lower() if str(public_data.get("quick_protocol") or "quic").lower() in {"auto", "http2", "quic"} else "quic",
                quick_fallback_protocols=_protocol_list(public_data.get("quick_fallback_protocols")) or ("auto", "http2"),
                quick_tunnel_fallback=_bool_config(public_data.get("quick_tunnel_fallback"), True),
            )
        if mode in {"quick", "quick_tunnel", "cloudflare_route", "trycloudflare"}:
            return StableTunnelConfig(
                route_mode="quick",
                source=str(BRIDGE_PUBLIC_ORIGIN_CONFIG_REL).replace(chr(92), "/"),
                local_origin=_as_origin(public_data.get("local_origin"), LOCAL_ORIGIN),
                quick_tunnel_fallback=_bool_config(public_data.get("quick_tunnel_fallback"), True),
            )

    data = read_json(root / BRIDGE_CONFIG_REL)
    tunnel = data.get("cloudflare_tunnel") if isinstance(data, dict) else None
    if not isinstance(tunnel, dict) or tunnel.get("enabled") is False:
        return StableTunnelConfig(route_mode="quick")

    route_mode = _normalize_route_mode(tunnel.get("route_mode") or tunnel.get("mode") or "named")

    hostname = str(tunnel.get("hostname") or "")
    endpoint = _as_endpoint(str(tunnel.get("public_endpoint") or hostname))
    protocol = str(tunnel.get("protocol") or "quic").lower()
    if protocol not in {"auto", "http2", "quic"}:
        protocol = "quic"
    fallbacks = _protocol_list(tunnel.get("fallback_protocols")) or ("auto", "http2")

    quick_protocol = str(tunnel.get("quick_protocol") or tunnel.get("protocol") or "quic").lower()
    if quick_protocol not in {"auto", "http2", "quic"}:
        quick_protocol = "quic"
    quick_fallbacks = _protocol_list(tunnel.get("quick_fallback_protocols")) or ("auto", "http2")

    return StableTunnelConfig(
        tunnel_name=str(tunnel.get("tunnel_name") or ""),
        tunnel_id=str(tunnel.get("tunnel_id") or ""),
        public_endpoint=endpoint,
        local_origin=_as_origin(tunnel.get("local_origin"), LOCAL_ORIGIN),
        protocol=protocol,
        fallback_protocols=fallbacks,
        source=str(BRIDGE_CONFIG_REL).replace(chr(92), "/"),
        route_mode=route_mode,
        quick_protocol=quick_protocol,
        quick_fallback_protocols=quick_fallbacks,
        quick_tunnel_fallback=_bool_config(tunnel.get("quick_tunnel_fallback"), True),
    )


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def state_paths(root: Path) -> tuple[Path, Path, Path]:
    base = root / ".takesome" / "ai-bridge"
    return base / "state" / "endpoint.json", base / "reports" / "CONNECT_CHATGPT.md", base / "state" / "stable-tunnel.json"


def write_endpoint_state(root: Path, endpoint: str, mode: str, write_enabled: bool, tunnel_kind: str, tunnel_name: str = "", protocol: str = "") -> None:
    state_path, report_path, _ = state_paths(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_endpoint": endpoint,
        "mode": mode,
        "host": LOCAL_HOST,
        "port": LOCAL_PORT,
        "started_at": utc_now(),
        "updated_at": utc_now(),
        "write_enabled": write_enabled,
        "logs_directory": ".takesome/ai-bridge/logs",
        "state_file": ".takesome/ai-bridge/state/endpoint.json",
        "report_file": ".takesome/ai-bridge/reports/CONNECT_CHATGPT.md",
        "tunnel": {"kind": tunnel_kind, "name": tunnel_name, "target": LOCAL_ORIGIN, "protocol": protocol},
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = f"""# MCP Connector Info

**Active endpoint:** {endpoint}
**Mode:** {mode}
**Write enabled:** {str(write_enabled).lower()}
**Tunnel:** {tunnel_kind if not tunnel_name else tunnel_kind + ':' + tunnel_name}
**Tunnel transport:** {protocol or 'default'}
**Local origin:** {LOCAL_MCP}
**Updated at:** {payload['updated_at']}

## How to run

```bat
serverBridge.bat
```

## Important

- If tunnel is `quick`, Cloudflare owns the generated `trycloudflare.com` URL and it can change after a tunnel restart.
- If tunnel is `named`, the public endpoint is stable and the ChatGPT connector does not need to be recreated after every restart.
"""
    report_path.write_text(report, encoding="utf-8")


def probe(url: str, timeout: float = 1.0) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NorthStarBridgeSupervisor/1"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return 200 <= int(response.status) < 300
    except Exception:
        return False


def wait_probe(url: str, timeout_sec: float, label: str) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if probe(url, timeout=2.0):
            return True
        time.sleep(0.5)
    emit("WARN", "probe did not become ready", target=label, url=url)
    return False


def quick_verify_timeout(default: float = 120.0) -> float:
    raw = os.environ.get("NORTHSTAR_CLOUDFLARED_QUICK_VERIFY_TIMEOUT_SEC", "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(20.0, min(240.0, value))


def find_cloudflared() -> str:
    candidates = [
        Path("C:/Cloudflared/bin/cloudflared.exe"),
        Path(os.environ.get("USERPROFILE", "")) / "Tools" / "cloudflared" / "cloudflared.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages" / "Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe" / "cloudflared.exe",
        Path(os.environ.get("ProgramFiles", "")) / "cloudflared" / "cloudflared.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Cloudflared" / "bin" / "cloudflared.exe",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    found = shutil.which("cloudflared")
    if found:
        return found
    raise SupervisorError("cloudflared.exe was not found. Put it in C:\\Cloudflared\\bin\\cloudflared.exe, %USERPROFILE%\\Tools\\cloudflared\\cloudflared.exe, or add it to PATH.")


def stream_reader(name: str, proc: subprocess.Popen[str], out: "queue.Queue[tuple[str, str]]") -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        out.put((name, line.rstrip("\r\n")))


def start_process(name: str, cmd: list[str], cwd: Path, env: dict[str, str], q: "queue.Queue[tuple[str, str]]") -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        shell=False,
    )
    threading.Thread(target=stream_reader, args=(name, proc, q), daemon=True).start()
    return proc


def spawn_origin(root: Path, write: bool, q: "queue.Queue[tuple[str, str]]", *, assume_yes: bool = False) -> subprocess.Popen[str]:
    bridge = root / "tools" / "scripts" / "northstar_ai_bridge.py"
    if not bridge.exists():
        raise SupervisorError(f"missing bridge entrypoint: {bridge}")
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NORTHSTAR_SUITE_STDIO_ENCODING": "utf-8",
        "NORTHSTAR_SUITE_STDIO_ERRORS": "replace",
    })
    if assume_yes:
        env["NORTHSTAR_SUITE_YES"] = "1"
        env.setdefault("NORTHSTAR_SUITE_YES_REASON", "serverBridge")
    if write:
        env["NORTHSTAR_AI_BRIDGE_WRITE"] = "1"
    else:
        env.setdefault("NORTHSTAR_AI_BRIDGE_WRITE", "0")
    cmd = [sys.executable, str(bridge), "--root", str(root), "--http"]
    if assume_yes:
        cmd.append("--yes")
    emit("INFO", "starting local MCP origin", endpoint=LOCAL_MCP, write=write, yes=assume_yes)
    proc = start_process("origin", cmd, root, env, q)
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SupervisorError(f"local origin exited before readiness, exit_code={proc.returncode}")
        if probe(LOCAL_HEALTH, timeout=1.0):
            emit("OK", "local origin is ready", url=LOCAL_HEALTH)
            return proc
        drain_logs(q, nonblocking=True)
        time.sleep(0.25)
    stop_processes([proc])
    raise SupervisorError(f"local origin did not become ready at {LOCAL_HEALTH}")


def start_origin(root: Path, write: bool, q: "queue.Queue[tuple[str, str]]", *, assume_yes: bool = False) -> Optional[subprocess.Popen[str]]:
    if probe(LOCAL_HEALTH, timeout=1.0):
        emit("OK", "local origin already responds", url=LOCAL_HEALTH)
        emit("STATE", "external local origin adopted; supervisor will restart it if health is lost", url=LOCAL_HEALTH)
        return None
    return spawn_origin(root, write, q, assume_yes=assume_yes)


def ensure_origin_alive(root: Path, write: bool, origin: Optional[subprocess.Popen[str]], q: "queue.Queue[tuple[str, str]]", *, assume_yes: bool = False) -> Optional[subprocess.Popen[str]]:
    if origin is not None and origin.poll() is not None:
        emit("WARN", "owned local origin exited; restarting", exit_code=origin.returncode)
        return spawn_origin(root, write, q, assume_yes=assume_yes)

    if probe(LOCAL_HEALTH, timeout=1.0):
        return origin

    if origin is not None:
        emit("WARN", "owned local origin stopped responding; restarting", url=LOCAL_HEALTH)
        stop_processes([origin])
    else:
        emit("WARN", "adopted local origin stopped responding; starting owned origin", url=LOCAL_HEALTH)
    return spawn_origin(root, write, q, assume_yes=assume_yes)


def load_stable_tunnel(root: Path) -> StableTunnelConfig:
    declared = load_declared_tunnel_config(root)
    _, _, stable_path = state_paths(root)
    data = read_json(stable_path)

    # Priority matters. The local .takesome stable-tunnel file can be stale
    # after a patch, so source-controlled config wins over local state for route
    # mode and transport policy. Environment variables remain the only higher
    # priority operator override.
    route_mode = _normalize_route_mode(
        os.environ.get("NORTHSTAR_CLOUDFLARE_ROUTE_MODE")
        or declared.route_mode
        or data.get("route_mode")
        or data.get("mode")
        or "named"
    )

    env_fallbacks = _protocol_list(os.environ.get("NORTHSTAR_CLOUDFLARED_FALLBACK_PROTOCOLS"))
    state_fallbacks = _protocol_list(data.get("fallback_protocols"))
    fallbacks = env_fallbacks or declared.fallback_protocols or state_fallbacks or ("auto", "http2")

    protocol = str(os.environ.get("NORTHSTAR_CLOUDFLARED_PROTOCOL") or declared.protocol or data.get("protocol") or "quic").lower()
    if protocol not in {"auto", "http2", "quic"}:
        protocol = "quic"

    tunnel_name = str(os.environ.get("NORTHSTAR_CLOUDFLARE_TUNNEL") or declared.tunnel_name or data.get("tunnel_name") or "")
    public_endpoint = _as_endpoint(str(os.environ.get("NORTHSTAR_PUBLIC_MCP_ENDPOINT") or declared.public_endpoint or data.get("public_endpoint") or ""))
    source = "environment" if os.environ.get("NORTHSTAR_CLOUDFLARE_TUNNEL") or os.environ.get("NORTHSTAR_PUBLIC_MCP_ENDPOINT") or os.environ.get("NORTHSTAR_CLOUDFLARE_ROUTE_MODE") else (declared.source or ("local-state" if data else ""))

    quick_protocol = str(os.environ.get("NORTHSTAR_CLOUDFLARED_QUICK_PROTOCOL") or declared.quick_protocol or data.get("quick_protocol") or protocol or "quic").lower()
    if quick_protocol not in {"auto", "http2", "quic"}:
        quick_protocol = "quic"
    quick_fallbacks = _protocol_list(os.environ.get("NORTHSTAR_CLOUDFLARED_QUICK_FALLBACK_PROTOCOLS")) or declared.quick_fallback_protocols or _protocol_list(data.get("quick_fallback_protocols")) or ("auto", "http2")

    return StableTunnelConfig(
        tunnel_name=tunnel_name,
        public_endpoint=public_endpoint,
        protocol=protocol,
        fallback_protocols=fallbacks,
        source=source,
        route_mode=route_mode,
        quick_protocol=quick_protocol,
        quick_fallback_protocols=quick_fallbacks,
    )


def _looks_like_hostname(value: str) -> bool:
    host = (value or "").strip().lower().rstrip(".")
    if not host or host in {".", "localhost"} or " " in host:
        return False
    if "/" in host or ":" in host:
        return False
    if "." not in host:
        return False
    labels = host.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        return False
    label_re = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    return all(label_re.match(label) for label in labels)

def _default_cloudflared_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    return home / ".cloudflared"


def _cloudflared_default_config_files() -> list[Path]:
    base = _default_cloudflared_dir()
    return [base / "config.yml", base / "config.yaml"]


def suspend_default_cloudflared_configs_for_quick_tunnel() -> list[SuspendedCloudflaredConfig]:
    r"""Hide default config files while starting a TryCloudflare quick tunnel.

    Cloudflare quick tunnels are not compatible with a default config file in
    %USERPROFILE%\.cloudflared. If that file is present, cloudflared can mix
    quick tunnel URL allocation with the named-tunnel credentials/ingress from
    config.yml, which creates a public URL that later returns 1033. The file is
    moved only for the short startup window and restored after cloudflared has
    printed the trycloudflare URL.
    """
    suspended: list[SuspendedCloudflaredConfig] = []
    for original in _cloudflared_default_config_files():
        if not original.exists():
            continue
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = original.with_name(f"{original.name}.northstar-quick-disabled-{os.getpid()}-{stamp}.bak")
        suffix = 0
        while backup.exists():
            suffix += 1
            backup = original.with_name(f"{original.name}.northstar-quick-disabled-{os.getpid()}-{stamp}-{suffix}.bak")
        try:
            original.replace(backup)
            suspended.append(SuspendedCloudflaredConfig(original=original, backup=backup))
            emit("WARN", "temporarily hiding default cloudflared config for quick tunnel", config=original, backup=backup)
        except Exception as exc:
            emit("WARN", "could not hide default cloudflared config; quick tunnel may fail with 1033", config=original, error=f"{type(exc).__name__}: {exc}")
    return suspended


def restore_default_cloudflared_configs(suspended: Iterable[SuspendedCloudflaredConfig]) -> None:
    for item in suspended:
        try:
            if item.original.exists():
                emit("WARN", "cloudflared config restore skipped because target already exists", config=item.original, backup=item.backup)
                continue
            if item.backup.exists():
                item.backup.replace(item.original)
                emit("OK", "cloudflared config restored", config=item.original)
        except Exception as exc:
            emit("WARN", "could not restore cloudflared config automatically", config=item.original, backup=item.backup, error=f"{type(exc).__name__}: {exc}")


def has_cloudflare_login() -> bool:
    return (_default_cloudflared_dir() / "cert.pem").exists()


def run_interactive(cmd: list[str], cwd: Path) -> int:
    emit("INFO", "running command", command=" ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), shell=False)
    return int(proc.returncode)


def run_capture(cmd: list[str], cwd: Path, timeout_sec: int = 120) -> tuple[int, str]:
    emit("INFO", "running command", command=" ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_sec,
    )
    text = proc.stdout or ""
    for line in text.splitlines():
        if line.strip():
            print(color("[cloudflared-setup]", "gray"), line, flush=True)
    return int(proc.returncode), text


def prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(color("? ", "yellow") + prompt + suffix + ": ").strip()
    return value or default


def setup_named_tunnel_interactive(root: Path, cloudflared: str) -> StableTunnelConfig | None:
    emit("WARN", "stable named tunnel is not configured", config=".takesome/ai-bridge/state/stable-tunnel.json")
    print()
    print("North Star can create a stable Cloudflare named tunnel now.")
    print("This requires a Cloudflare account and a domain/zone already added to Cloudflare.")
    print("If you do not have that, press Enter on hostname later and serverBridge will use quick tunnel fallback.")
    print()

    if not has_cloudflare_login():
        answer = prompt_text("Run 'cloudflared tunnel login' now? This opens a browser", "Y").lower()
        if answer not in {"y", "yes", "д", "да"}:
            emit("WARN", "operator skipped Cloudflare login; quick tunnel fallback will be used")
            return None
        rc = run_interactive([cloudflared, "tunnel", "login"], root)
        if rc != 0 or not has_cloudflare_login():
            emit("WARN", "cloudflared login did not produce cert.pem; quick tunnel fallback will be used", exit_code=rc)
            return None

    tunnel_name = prompt_text("Tunnel name", "northstar-suite")
    hostname = prompt_text("Stable public hostname, for example northstar-suite.example.com. Leave empty for quick tunnel fallback", "")
    if not hostname or not _looks_like_hostname(hostname):
        emit("WARN", "valid hostname was not provided; quick tunnel fallback will be used", hostname=hostname or "<empty>")
        return None
    public_endpoint = "https://" + hostname.rstrip("/") + "/mcp"

    rc, output = run_capture([cloudflared, "tunnel", "create", tunnel_name], root)
    already_exists = "already exists" in output.lower() or "tunnel with name" in output.lower()
    if rc != 0 and not already_exists:
        emit("WARN", "could not create named tunnel; quick tunnel fallback will be used", tunnel=tunnel_name, exit_code=rc)
        return None

    rc, route_output = run_capture([cloudflared, "tunnel", "route", "dns", tunnel_name, hostname], root)
    route_exists = "already exists" in route_output.lower() or "already configured" in route_output.lower()
    if rc != 0 and not route_exists:
        emit("WARN", "could not create DNS route; quick tunnel fallback will be used", hostname=hostname, exit_code=rc)
        return None

    _, _, stable_path = state_paths(root)
    stable_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tunnel_name": tunnel_name,
        "hostname": hostname,
        "public_endpoint": public_endpoint,
        "protocol": "quic",
        "fallback_protocols": ["auto", "http2"],
        "created_at": utc_now(),
        "created_by": "serverBridge.bat",
        "mode": "named",
        "local_origin": LOCAL_ORIGIN,
        "notes": [
            "This file makes serverBridge.bat restart-safe.",
            "ChatGPT connector should use public_endpoint and does not need to be recreated after local restarts.",
            "Transport policy is QUIC primary for ChatGPT connector compatibility, with auto/HTTP2 as startup fallback. Use NORTHSTAR_CLOUDFLARED_PROTOCOL=http2 only on restrictive networks where UDP/QUIC is blocked.",
        ],
    }
    stable_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit("OK", "stable named tunnel config saved", endpoint=public_endpoint, tunnel=tunnel_name)
    return StableTunnelConfig(tunnel_name=tunnel_name, public_endpoint=public_endpoint, local_origin=LOCAL_ORIGIN, protocol="quic", fallback_protocols=("auto", "http2"), source="interactive-setup")


def _protocol_sequence(primary: str, fallbacks: Iterable[str]) -> list[str]:
    allowed = {"auto", "http2", "quic"}
    seq: list[str] = []
    for item in [primary, *list(fallbacks)]:
        value = (item or "").strip().lower()
        if value in allowed and value not in seq:
            seq.append(value)
    return seq or ["quic", "auto", "http2"]



def _yaml_scalar(value: str) -> str:
    text = str(value)
    if re.match(r"^[A-Za-z0-9:/._-]+$", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def write_named_tunnel_ingress_config(root: Path, cfg: StableTunnelConfig) -> Path:
    """Write a generated Cloudflare named-tunnel config with ingress rules.

    `cloudflared tunnel run <name>` can connect without a config file, but then
    Cloudflare has no ingress mapping and returns 503 for the hostname. This
    generated file gives the named tunnel the same service mapping as quick
    tunnel mode while preserving quick_tunnel_fallback as emergency fallback.
    """

    hostname = _hostname_from_endpoint(cfg.public_endpoint)
    tunnel_ref = cfg.tunnel_id or cfg.tunnel_name
    if not tunnel_ref:
        raise SupervisorError("named tunnel config requires tunnel_id or tunnel_name")
    if not hostname:
        raise SupervisorError("named tunnel config requires a hostname/public_origin")
    local_origin = (cfg.local_origin or LOCAL_ORIGIN).rstrip("/")
    config_dir = root / ".takesome" / "ai-bridge" / "cloudflared"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "named-tunnel.yml"
    lines = [
        f"tunnel: {_yaml_scalar(tunnel_ref)}",
        "ingress:",
        f"  - hostname: {_yaml_scalar(hostname)}",
        f"    service: {_yaml_scalar(local_origin)}",
        "  - service: http_status:404",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    emit("INFO", "named tunnel ingress config ready", config=path, hostname=hostname, service=local_origin)
    return path


def start_named_tunnel_once(root: Path, cloudflared: str, cfg: StableTunnelConfig, protocol: str, q: "queue.Queue[tuple[str, str]]") -> subprocess.Popen[str]:
    ingress_config = write_named_tunnel_ingress_config(root, cfg)
    tunnel_ref = cfg.tunnel_name or cfg.tunnel_id
    emit(
        "INFO",
        "starting named Cloudflare tunnel",
        mode="cloudflare_named_tunnel",
        endpoint=cfg.public_endpoint,
        tunnel=tunnel_ref,
        tunnel_id=cfg.tunnel_id,
        protocol=protocol,
        config=ingress_config,
        service=cfg.local_origin,
    )
    env = os.environ.copy()
    cmd = [cloudflared, "tunnel", "--config", str(ingress_config), "--protocol", protocol, "run", tunnel_ref]
    proc = start_process("cloudflared", cmd, root, env, q)
    write_endpoint_state(root, cfg.public_endpoint, "http", True, "named", tunnel_ref, protocol=protocol)
    return proc


def start_named_tunnel(root: Path, cloudflared: str, cfg: StableTunnelConfig, q: "queue.Queue[tuple[str, str]]") -> tuple[subprocess.Popen[str], str]:
    if not (cfg.tunnel_name or cfg.tunnel_id) or not cfg.public_endpoint:
        raise SupervisorError("stable tunnel config requires tunnel_name and public_endpoint")
    health = cfg.public_url + "/health" if cfg.public_url else ""
    emit("INFO", "Bridge local origin:", endpoint=cfg.local_origin)
    emit("INFO", "Bridge public origin:", endpoint=cfg.public_endpoint.rsplit("/mcp", 1)[0])
    emit("INFO", "Tunnel mode:", mode="cloudflare_named_tunnel")
    emit("INFO", "Tunnel id:", tunnel=cfg.tunnel_id or cfg.tunnel_name)
    protocols = _protocol_sequence(cfg.protocol, cfg.fallback_protocols)
    last_error = ""
    for index, protocol in enumerate(protocols):
        proc = start_named_tunnel_once(root, cloudflared, cfg, protocol, q)
        deadline = time.time() + 20
        while time.time() < deadline:
            for _, line in drain_logs_collect(q, nonblocking=True):
                if "No ingress rules were defined" in line:
                    last_error = "cloudflared started named tunnel without ingress rules; generated config was not accepted"
                    emit("WARN", "named tunnel has no ingress rules; stopping it before Cloudflare returns 503", protocol=protocol)
                    stop_processes([proc])
                    break
            if last_error:
                break
            if proc.poll() is not None:
                last_error = f"cloudflared exited during {protocol} startup, exit_code={proc.returncode}"
                emit("WARN", "named tunnel startup failed", protocol=protocol, exit_code=proc.returncode)
                break
            if health and probe(health, timeout=2.0):
                emit("OK", "named tunnel public health is reachable", endpoint=cfg.public_endpoint, protocol=protocol)
                emit("OK", "Stable public URL active", endpoint=cfg.public_endpoint)
                return proc, protocol
            time.sleep(0.5)
        else:
            # The process is alive but public health is not reachable yet. Keep the
            # tunnel instead of killing it: DNS/Access/public propagation can lag.
            emit("WARN", "named tunnel is running but public health is not verified yet", endpoint=cfg.public_endpoint, protocol=protocol)
            return proc, protocol

        stop_processes([proc])
        if index + 1 < len(protocols):
            emit("WARN", "retrying named tunnel with fallback transport", next_protocol=protocols[index + 1])

    raise SupervisorError(last_error or "could not start named Cloudflare tunnel")


def _isolated_quick_env(root: Path) -> dict[str, str]:
    r"""Build a cloudflared environment that cannot inherit named tunnel config.

    TryCloudflare quick tunnels must not load the operator's default
    %USERPROFILE%\.cloudflared\config.yml. Using an isolated HOME/USERPROFILE is
    more reliable than temporarily renaming the real config, and it avoids
    mixing account-bound named tunnel credentials into an account-less quick URL.
    """
    env = os.environ.copy()
    quick_home = root / ".takesome" / "ai-bridge" / "cloudflared-quick-home"
    (quick_home / ".cloudflared").mkdir(parents=True, exist_ok=True)
    env["USERPROFILE"] = str(quick_home)
    env["HOME"] = str(quick_home)
    env["CLOUDFLARED_QUICK_TUNNEL"] = "1"
    for key in [
        "TUNNEL_CONFIG",
        "TUNNEL_CRED_FILE",
        "TUNNEL_CREDENTIALS_FILE",
        "TUNNEL_ORIGIN_CERT",
        "TUNNEL_TRANSPORT_PROTOCOL",
        "CLOUDFLARED_CONFIG",
        "CLOUDFLARED_TUNNEL_TOKEN",
        "CLOUDFLARED_TUNNEL_CRED_FILE",
        "CLOUDFLARED_TUNNEL_CREDENTIALS_FILE",
        "CLOUDFLARED_ORIGIN_CERT",
    ]:
        env.pop(key, None)
    return env


def start_quick_tunnel_once(root: Path, cloudflared: str, q: "queue.Queue[tuple[str, str]]", protocol: str = "quic") -> tuple[subprocess.Popen[str], str, list[SuspendedCloudflaredConfig]]:
    emit("INFO", "requesting Cloudflare quick tunnel domain", target=LOCAL_ORIGIN, protocol=protocol)
    env = _isolated_quick_env(root)
    suspended_configs = suspend_default_cloudflared_configs_for_quick_tunnel()
    cmd = [cloudflared, "tunnel", "--protocol", protocol, "--url", LOCAL_ORIGIN, "--ha-connections", "1"]
    proc: Optional[subprocess.Popen[str]] = None
    try:
        proc = start_process("cloudflared", cmd, root, env, q)
        deadline = time.time() + 90
        while time.time() < deadline:
            if proc.poll() is not None:
                raise SupervisorError(f"cloudflared exited before URL allocation, exit_code={proc.returncode}")
            try:
                name, line = q.get(timeout=0.25)
            except queue.Empty:
                continue
            emit_stream(name, line)
            match = URL_RE.search(line)
            if match:
                url = match.group(0).rstrip("/")
                endpoint = url + "/mcp"
                # Keep the operator's default cloudflared config hidden while
                # the quick tunnel process is alive. Restoring it immediately
                # after URL allocation lets cloudflared finish startup with the
                # named tunnel credentials, which causes Cloudflare 1033.
                emit("OK", "Cloudflare quick route allocated", endpoint=endpoint)
                return proc, url, suspended_configs
        raise SupervisorError("cloudflared did not print a trycloudflare.com URL")
    except Exception:
        if proc is not None:
            stop_processes([proc])
        restore_default_cloudflared_configs(suspended_configs)
        raise
def _line_has_quick_route_terminal_error(line: str) -> bool:
    clean = line.lower()
    return any(pattern in clean for pattern in QUICK_ROUTE_TERMINAL_PATTERNS)


def _verify_public_route(root: Path, public_url: str, protocol: str, q: "queue.Queue[tuple[str, str]]", timeout_sec: float = 120.0) -> bool:
    health = public_url.rstrip("/") + "/health"
    endpoint = public_url.rstrip("/") + "/mcp"
    deadline = time.time() + timeout_sec
    announced_wait = False
    terminal_error_count = 0
    while time.time() < deadline:
        for _name, line in drain_logs_collect(q, nonblocking=True):
            if _line_has_quick_route_terminal_error(line):
                terminal_error_count += 1
        if terminal_error_count >= QUICK_ROUTE_TERMINAL_ERROR_THRESHOLD:
            emit(
                "WARN",
                "quick route connector was rejected by Cloudflare; abandoning allocated route early",
                endpoint=endpoint,
                protocol=protocol,
                occurrences=terminal_error_count,
            )
            return False
        if probe(health, timeout=3.0):
            write_endpoint_state(root, endpoint, "http", True, "quick", "", protocol=protocol)
            emit("OK", "public MCP endpoint verified and written", endpoint=endpoint, protocol=protocol)
            return True
        if not announced_wait:
            announced_wait = True
            emit("STATE", "waiting for Cloudflare quick route to become publicly reachable", endpoint=endpoint, protocol=protocol)
        time.sleep(1.0)
    # Final late check closes the race where Cloudflare reaches origin exactly
    # as the timeout expires. Do not do it when Cloudflare has already rejected
    # the quick connector, because that hostname is not usable.
    if terminal_error_count < QUICK_ROUTE_TERMINAL_ERROR_THRESHOLD and probe(health, timeout=5.0):
        write_endpoint_state(root, endpoint, "http", True, "quick", "", protocol=protocol)
        emit("OK", "public MCP endpoint verified and written", endpoint=endpoint, protocol=protocol)
        return True
    emit("WARN", "quick route was allocated but public health did not verify", endpoint=endpoint, protocol=protocol)
    return False


def start_quick_tunnel(root: Path, cloudflared: str, q: "queue.Queue[tuple[str, str]]", primary: str = "quic", fallbacks: Iterable[str] = ("auto", "http2")) -> tuple[subprocess.Popen[str], str, str, list[SuspendedCloudflaredConfig]]:
    protocols = _protocol_sequence(primary, fallbacks)
    last_error = ""
    verify_timeout = quick_verify_timeout(120.0)
    for index, protocol in enumerate(protocols):
        proc: Optional[subprocess.Popen[str]] = None
        suspended_configs: list[SuspendedCloudflaredConfig] = []
        try:
            proc, public_url, suspended_configs = start_quick_tunnel_once(root, cloudflared, q, protocol=protocol)
            endpoint = public_url.rstrip("/") + "/mcp"
            if _verify_public_route(root, public_url, protocol, q, timeout_sec=verify_timeout):
                emit("STATE", "Cloudflare quick route selected", endpoint=endpoint, protocol=protocol)
                emit("INFO", "Temporary public origin:", endpoint=public_url.rstrip("/"))
                return proc, public_url, protocol, suspended_configs
            last_error = f"quick route public health did not verify for {endpoint}"
        except SupervisorError as exc:
            last_error = str(exc)
            emit("WARN", "quick route startup failed", protocol=protocol, error=last_error)
        except KeyboardInterrupt:
            if proc is not None:
                stop_processes([proc])
            if suspended_configs:
                restore_default_cloudflared_configs(suspended_configs)
            raise
        if proc is not None:
            stop_processes([proc])
            proc = None
        if suspended_configs:
            restore_default_cloudflared_configs(suspended_configs)
        if index + 1 < len(protocols):
            emit("WARN", "retrying quick route with fallback transport", next_protocol=protocols[index + 1])
    raise SupervisorError(last_error or "could not start Cloudflare quick route")

def _compact_cloudflared_line(line: str) -> str | None:
    clean = _strip_ansi(line).strip()
    if not clean:
        return None
    if "CONNECTIVITY PRE-CHECKS" in clean or clean.startswith("+") or clean.startswith("|"):
        return None
    if " precheck component=" in clean:
        return None
    if " precheck complete " in clean:
        hard_fail = re.search(r"hard_fail=([^\s]+)", clean)
        protocol = re.search(r"suggested_protocol=([^\s]+)", clean)
        status = "failed" if hard_fail and hard_fail.group(1).lower() == "true" else "ok"
        proto = protocol.group(1) if protocol else "auto"
        return f"precheck {status} protocol={proto}"
    return line


def emit_stream(name: str, line: str) -> None:
    if not line:
        return
    if name == "cloudflared":
        compact = _compact_cloudflared_line(line)
        if compact is None:
            _footer_observe_stream(name, line)
            return
        line = compact
    _footer_observe_stream(name, line)
    stream_color = "cyan" if name == "origin" else "magenta" if name == "cloudflared" else "gray"
    _footer_print(_bracket(name, stream_color, strong=True) + " " + _colorize_stream_line(name, line))


def drain_logs_collect(q: "queue.Queue[tuple[str, str]]", nonblocking: bool = False) -> list[tuple[str, str]]:
    drained: list[tuple[str, str]] = []
    while True:
        try:
            name, line = q.get_nowait() if nonblocking else q.get(timeout=0.25)
        except queue.Empty:
            return drained
        emit_stream(name, line)
        drained.append((name, line))


def drain_logs(q: "queue.Queue[tuple[str, str]]", nonblocking: bool = False) -> None:
    drain_logs_collect(q, nonblocking=nonblocking)


def monitor(root: Path, origin: Optional[subprocess.Popen[str]], tunnel: subprocess.Popen[str], public_url: str, quick: bool, q: "queue.Queue[tuple[str, str]]", write: bool, suspended_configs: Optional[list[SuspendedCloudflaredConfig]] = None, *, assume_yes: bool = False) -> int:
    endpoint = public_url.rstrip("/") + "/mcp" if public_url else ""
    _footer_bind(root, endpoint=endpoint, write=write)
    health = public_url.rstrip("/") + "/health" if public_url else ""
    if public_url:
        if wait_probe(health, 45, "public health"):
            _footer_mark("CONNECTED", "public health verified", endpoint=endpoint, tunnel="ready", origin="ready", write=write)
            emit("OK", "serverBridge is live", endpoint=endpoint)
        else:
            emit("WARN", "domain was allocated, but public health did not verify yet", endpoint=endpoint)
            if quick:
                emit("WARN", "quick tunnel URL may require reconnect or fallback to named tunnel", endpoint=endpoint)
    emit("STATE", "supervisor is running; close this window to stop origin+tunnel")
    next_origin_check = 0.0
    restart_times: list[float] = []
    try:
        while True:
            drain_logs(q, nonblocking=True)
            _footer_tick()
            now = time.time()
            if now >= next_origin_check:
                next_origin_check = now + 2.0
                try:
                    before = origin
                    origin = ensure_origin_alive(root, write, origin, q, assume_yes=assume_yes)
                    if origin is not before:
                        restart_times = [t for t in restart_times if now - t < 120]
                        restart_times.append(now)
                        if len(restart_times) > 5:
                            emit("ERROR", "local origin restart loop detected", restarts=len(restart_times), window_seconds=120)
                            return 1
                except SupervisorError as exc:
                    emit("ERROR", str(exc))
                    return 1
            if tunnel.poll() is not None:
                emit("ERROR", "cloudflared tunnel exited", exit_code=tunnel.returncode)
                return int(tunnel.returncode or 1)
            time.sleep(0.25)
    except KeyboardInterrupt:
        emit("INFO", "stopping serverBridge")
        return 130
    finally:
        with _FOOTER_LOCK:
            _footer_clear_locked()
            _footer_restore_layout_locked()
        stop_processes([tunnel, origin])
        if suspended_configs:
            restore_default_cloudflared_configs(suspended_configs)


def stop_processes(processes: Iterable[Optional[subprocess.Popen[str]]]) -> None:
    for proc in processes:
        if proc is None or proc.poll() is not None:
            continue
        try:
            proc.terminate()
        except Exception:
            pass
    deadline = time.time() + 5
    for proc in processes:
        if proc is None:
            continue
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="One-window North Star MCP origin + tunnel supervisor")
    parser.add_argument("--root", default=".")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--prefer-named", action="store_true")
    parser.add_argument("--setup-named", action="store_true", help="Interactively create a Cloudflare named tunnel when stable config is missing.")
    parser.add_argument("--quick-protocol", default="auto", choices=["http2", "quic", "auto"])
    parser.add_argument("-y", "--yes", "--assume-yes", action="store_true", help="Run unattended: assume yes for Suite-owned confirmations and skip interactive tunnel setup prompts.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if args.yes:
        os.environ["NORTHSTAR_SUITE_YES"] = "1"
        os.environ["NORTHSTAR_SUITE_YES_REASON"] = "serverBridge"
        os.environ.setdefault("NORTHSTAR_BRIDGE_SUDO", "1")
        os.environ["NORTHSTAR_BRIDGE_DENSE_LOGS"] = "1"
    bridge_write = bool(args.write or args.yes)
    q: "queue.Queue[tuple[str, str]]" = queue.Queue()
    _footer_bind(root, write=bridge_write)
    origin: Optional[subprocess.Popen[str]] = None
    tunnel: Optional[subprocess.Popen[str]] = None
    suspended_configs: list[SuspendedCloudflaredConfig] = []
    try:
        origin = start_origin(root, bridge_write, q, assume_yes=args.yes)
        cloudflared = find_cloudflared()
        cfg = load_stable_tunnel(root)
        if args.prefer_named and cfg.route_mode == "named" and not (cfg.tunnel_name and cfg.public_endpoint) and args.setup_named and not args.yes:
            created = setup_named_tunnel_interactive(root, cloudflared)
            if created is not None:
                cfg = created
        if args.prefer_named and cfg.route_mode == "named" and (cfg.tunnel_name or cfg.tunnel_id) and cfg.public_endpoint:
            try:
                tunnel, active_protocol = start_named_tunnel(root, cloudflared, cfg, q)
                public_url = cfg.public_url
                emit("STATE", "named tunnel selected", endpoint=cfg.public_endpoint, protocol=active_protocol)
                return monitor(root, origin, tunnel, public_url, quick=False, q=q, write=bridge_write, assume_yes=args.yes)
            except SupervisorError as exc:
                emit("WARN", "Named Cloudflare Tunnel failed.", error=str(exc))
                if not cfg.quick_tunnel_fallback:
                    raise
                emit("WARN", "quick_tunnel_fallback=true, starting emergency quick tunnel.")
                emit("WARN", "Quick Tunnel is not canonical Suite URL.")
                stop_processes([tunnel])
                tunnel = None
        if args.prefer_named and cfg.route_mode == "quick":
            emit("STATE", "Cloudflare route mode is enabled; requesting a fresh trycloudflare.com route", config=cfg.source, protocol=cfg.quick_protocol)
        elif args.prefer_named:
            emit("WARN", "stable named tunnel is not configured; falling back to quick Cloudflare route", config=".takesome/ai-bridge/state/stable-tunnel.json")
        protocol = args.quick_protocol if args.quick_protocol != "auto" else cfg.quick_protocol
        tunnel, public_url, active_protocol, suspended_configs = start_quick_tunnel(root, cloudflared, q, primary=protocol, fallbacks=cfg.quick_fallback_protocols)
        return monitor(root, origin, tunnel, public_url, quick=True, q=q, write=bridge_write, suspended_configs=suspended_configs, assume_yes=args.yes)
    except KeyboardInterrupt:
        emit("INFO", "stopping serverBridge")
        stop_processes([tunnel, origin])
        if suspended_configs:
            restore_default_cloudflared_configs(suspended_configs)
        return 130
    except SupervisorError as exc:
        emit("ERROR", str(exc))
        stop_processes([tunnel, origin])
        if suspended_configs:
            restore_default_cloudflared_configs(suspended_configs)
        return 1
    except Exception as exc:
        emit("ERROR", f"unexpected supervisor error: {type(exc).__name__}: {exc}")
        stop_processes([tunnel, origin])
        if suspended_configs:
            restore_default_cloudflared_configs(suspended_configs)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
