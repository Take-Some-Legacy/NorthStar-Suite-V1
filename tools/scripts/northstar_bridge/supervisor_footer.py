from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .terminal_style import color, fit_ansi, strip_ansi, style

FOOTER_STATE_REL = Path(".takesome") / "ai-bridge" / "state" / "agent-status.json"
FOOTER_ENABLED_ENV = "NORTHSTAR_SUPERVISOR_FOOTER"
FOOTER_MODE_ENV = "NORTHSTAR_SUPERVISOR_FOOTER_MODE"



@dataclass
class AgentFooterStatus:
    """Best-effort live state for the fixed serverBridge console footer."""

    status: str = "STARTING"
    endpoint: str = ""
    origin: str = "starting"
    tunnel: str = "starting"
    write: bool = False
    tools: int = 0
    last_event: str = "boot"
    request_id: int = 0
    request_count: int = 0
    health_count: int = 0
    error_count: int = 0
    started_at: float = 0.0
    updated_at: float = 0.0
    working_until: float = 0.0
    state_path: str = ""

    def effective_status(self) -> str:
        now = time.time()
        if self.status in {"ERROR", "WARN", "STARTING"}:
            return self.status
        if now < self.working_until:
            return "WORKING"
        if self.status == "CONNECTED" and now - (self.updated_at or now) < 6.0:
            return "CONNECTED"
        if self.endpoint:
            return "IDLE"
        return self.status or "STARTING"


_FOOTER = AgentFooterStatus(started_at=time.time(), updated_at=time.time())
_FOOTER_LOCK = threading.RLock()
_FOOTER_LAST_WRITE = 0.0
_FOOTER_LAST_TEXT = ""
_FOOTER_LAST_SIZE: tuple[int, int] = (0, 0)
_FOOTER_ROOT: Path | None = None
_FOOTER_SUPPORTED = True
_FOOTER_SCROLL_ACTIVE = False
_FOOTER_ALT_SCREEN_ACTIVE = False
_FOOTER_DRAWN_ROWS: set[int] = set()


def _footer_enabled() -> bool:
    # Default to stream-safe mode. The old fixed footer used alternate screen,
    # scroll-region control and cursor repositioning; that keeps the footer
    # visually pinned, but it also breaks terminal scrollback and can pull the
    # operator back to the bottom while new log lines arrive.
    #
    # The footer can still be re-enabled explicitly for demos with:
    #   NORTHSTAR_SUPERVISOR_FOOTER=1
    raw = os.environ.get(FOOTER_ENABLED_ENV, "0").strip().lower()
    if raw not in {"1", "true", "on", "yes", "y", "force"}:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return bool(sys.stdout.isatty())


def _footer_size() -> tuple[int, int]:
    size = shutil.get_terminal_size((120, 30))
    return max(40, size.columns), max(4, size.lines)


def _footer_width() -> int:
    return _footer_size()[0]


def _footer_height() -> int:
    # One explicit separator + one status line. The scroll region keeps logs
    # above this reserved area, so the footer remains visually attached to the
    # bottom even when subprocesses are noisy.
    return 2


def _footer_row() -> int:
    return _footer_size()[1]


def _footer_separator_row() -> int:
    return max(1, _footer_row() - 1)


def _footer_log_bottom() -> int:
    return max(1, _footer_row() - _footer_height())


def _footer_clear_rows_sequence_locked(rows: set[int], *, reset_scroll: bool = False) -> str:
    _, height = _footer_size()
    visible_rows = sorted({row for row in rows if 1 <= row <= height})
    if not visible_rows and not reset_scroll:
        return ""
    parts = ["\033[s"]
    if reset_scroll:
        parts.append("\033[r")
    for row in visible_rows:
        parts.append(f"\033[{row};1H\033[2K")
    parts.append("\033[u")
    return "".join(parts)


def _footer_alt_screen_enabled() -> bool:
    # Alternate screen is never enabled by default: it hides normal scrollback.
    raw = os.environ.get("NORTHSTAR_SUPERVISOR_ALT_SCREEN", "0").strip().lower()
    return raw in {"1", "true", "on", "yes", "y", "force"}


def _footer_enter_alt_screen_locked() -> None:
    global _FOOTER_ALT_SCREEN_ACTIVE, _FOOTER_LAST_TEXT
    if _FOOTER_ALT_SCREEN_ACTIVE or not _footer_enabled() or not _footer_alt_screen_enabled():
        return
    try:
        sys.stdout.write("\033[?1049h\033[2J\033[H")
        sys.stdout.flush()
        _FOOTER_ALT_SCREEN_ACTIVE = True
        _FOOTER_LAST_TEXT = ""
    except Exception:
        pass


def _footer_leave_alt_screen_locked() -> None:
    global _FOOTER_ALT_SCREEN_ACTIVE
    if not _FOOTER_ALT_SCREEN_ACTIVE:
        return
    try:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
    except Exception:
        pass
    _FOOTER_ALT_SCREEN_ACTIVE = False


def _footer_apply_layout_locked(force: bool = False) -> None:
    global _FOOTER_LAST_SIZE, _FOOTER_LAST_TEXT, _FOOTER_SCROLL_ACTIVE
    if not _footer_enabled() or not _FOOTER_SUPPORTED:
        return
    _footer_enter_alt_screen_locked()
    width, height = _footer_size()
    size = (width, height)
    size_changed = size != _FOOTER_LAST_SIZE or not _FOOTER_SCROLL_ACTIVE
    if not force and not size_changed and _FOOTER_SCROLL_ACTIVE:
        return
    if force and not size_changed and _FOOTER_SCROLL_ACTIVE:
        return
    try:
        log_bottom = _footer_log_bottom()
        cleanup_rows = set(_FOOTER_DRAWN_ROWS)
        cleanup_rows.update({_footer_separator_row(), _footer_row()})
        cleanup = _footer_clear_rows_sequence_locked(cleanup_rows, reset_scroll=size_changed)
        sys.stdout.write(f"{cleanup}\033[s\033[1;{log_bottom}r\033[u")
        sys.stdout.flush()
        _FOOTER_LAST_SIZE = size
        _FOOTER_LAST_TEXT = ""
        _FOOTER_SCROLL_ACTIVE = True
    except Exception:
        pass


def restore_layout() -> None:
    global _FOOTER_SCROLL_ACTIVE
    if _FOOTER_SCROLL_ACTIVE:
        try:
            sys.stdout.write("\033[r")
            sys.stdout.flush()
        except Exception:
            pass
        _FOOTER_SCROLL_ACTIVE = False
    _footer_leave_alt_screen_locked()


def _footer_status_color(status: str) -> str:
    return {
        "STARTING": "yellow",
        "CONNECTED": "green",
        "WORKING": "magenta",
        "IDLE": "cyan",
        "WARN": "yellow",
        "ERROR": "red",
    }.get(status, "white")


def _footer_mode(width: int) -> str:
    raw = os.environ.get("NORTHSTAR_SUPERVISOR_FOOTER_SIZE", "auto").strip().lower()
    if raw in {"minimal", "compact", "full"}:
        return raw
    if width < 72:
        return "minimal"
    if width < 108:
        return "compact"
    return "full"


def _footer_field(key: str, value: object, value_color: str = "white") -> str:
    return color(key, "gray") + color("=", "dim") + color(value, value_color)


def _footer_endpoint(width: int, mode: str) -> str:
    endpoint = (_FOOTER.endpoint or "local-only").replace("https://", "").replace("http://", "")
    cap = 28 if mode == "minimal" else 42 if mode == "compact" else max(34, min(64, width // 3))
    if len(endpoint) > cap:
        endpoint = "…" + endpoint[-(cap - 1):]
    return endpoint


def _footer_line(width: int | None = None) -> str:
    width = width or _footer_width()
    mode = _footer_mode(width)
    status = _FOOTER.effective_status()
    status_color = _footer_status_color(status)
    age = max(0, int(time.time() - (_FOOTER.updated_at or _FOOTER.started_at or time.time())))
    endpoint = _footer_endpoint(width, mode)
    head = style(" AI ", status_color, "bold") + " " + style(status.ljust(9), status_color, "bold")
    sep = color("│", "gray")
    if mode == "minimal":
        parts = [
            head,
            sep,
            _footer_field("req", _FOOTER.request_count, "cyan"),
            _footer_field("health", _FOOTER.health_count, "green"),
            sep,
            color(endpoint, "cyan"),
        ]
    elif mode == "compact":
        parts = [
            head,
            sep,
            _footer_field("origin", _FOOTER.origin, "green" if _FOOTER.origin == "ready" else "yellow"),
            _footer_field("tunnel", _FOOTER.tunnel, "green" if _FOOTER.tunnel == "ready" else "yellow"),
            _footer_field("tools", _FOOTER.tools or "-", "cyan"),
            sep,
            _footer_field("endpoint", endpoint, "cyan"),
        ]
    else:
        parts = [
            head,
            sep,
            _footer_field("origin", _FOOTER.origin, "green" if _FOOTER.origin == "ready" else "yellow"),
            _footer_field("tunnel", _FOOTER.tunnel, "green" if _FOOTER.tunnel == "ready" else "yellow"),
            _footer_field("write", "on" if _FOOTER.write else "off", "green" if _FOOTER.write else "yellow"),
            _footer_field("tools", _FOOTER.tools or "-", "cyan"),
            _footer_field("req", _FOOTER.request_count, "cyan"),
            _footer_field("health", _FOOTER.health_count, "green"),
            sep,
            _footer_field("endpoint", endpoint, "cyan"),
            sep,
            _footer_field("last", f"{_FOOTER.last_event or 'boot'} {age}s", "white"),
        ]
    return " ".join(str(part) for part in parts)


def _footer_separator(width: int) -> str:
    title = " North Star Bridge — footer "
    if width <= len(title) + 4:
        return color("─" * width, "gray")
    left = max(1, (width - len(title)) // 2)
    right = max(1, width - len(title) - left)
    return color("─" * left, "gray") + style(title, "gray", "bold") + color("─" * right, "gray")


def write_state_locked(force: bool = False) -> None:
    """Persist the live footer state for diagnostics without risking supervisor startup."""

    global _FOOTER_LAST_WRITE
    root = _FOOTER_ROOT
    if root is None:
        return
    now = time.time()
    if not force and now - _FOOTER_LAST_WRITE < 0.25:
        return
    try:
        state_path = root / FOOTER_STATE_REL
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(_FOOTER)
        payload["effective_status"] = _FOOTER.effective_status()
        payload["updated_at_unix"] = int(now)
        payload["schema"] = "northstar.bridge.footer_state.v1"
        payload["state_path"] = str(state_path)
        _FOOTER.state_path = str(state_path)
        tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(state_path)
        _FOOTER_LAST_WRITE = now
    except Exception:
        # Footer diagnostics are never allowed to kill serverBridge.
        return


def draw(force: bool = False) -> None:
    global _FOOTER_LAST_TEXT, _FOOTER_SUPPORTED
    if not _footer_enabled() or not _FOOTER_SUPPORTED:
        return
    try:
        _footer_apply_layout_locked(force=force)
        # Never paint into the final terminal column. Some terminals keep an
        # autowrap-pending state there; on resize that pending wrap can push the
        # footer into the log region and leave duplicated footer rows behind.
        width = max(1, _footer_width() - 1)
        body = fit_ansi(_footer_line(width), width)
        separator = fit_ansi(_footer_separator(width), width)
        text = separator + "\n" + body
        if not force and text == _FOOTER_LAST_TEXT:
            return
        sep_row = _footer_separator_row()
        row = _footer_row()
        sys.stdout.write(
            f"\033[s"
            f"\033[?7l"
            f"\033[{sep_row};1H\033[2K{separator}"
            f"\033[{row};1H\033[2K{body}"
            f"\033[?7h"
            f"\033[u"
        )
        sys.stdout.flush()
        _FOOTER_DRAWN_ROWS.update({sep_row, row})
        _FOOTER_LAST_TEXT = text
    except Exception:
        _FOOTER_SUPPORTED = False


def clear() -> None:
    global _FOOTER_LAST_TEXT
    if not _footer_enabled() or not _FOOTER_SUPPORTED:
        return
    try:
        rows = set(_FOOTER_DRAWN_ROWS)
        rows.update({_footer_separator_row(), _footer_row()})
        sys.stdout.write(_footer_clear_rows_sequence_locked(rows))
        sys.stdout.flush()
        _FOOTER_DRAWN_ROWS.clear()
        _FOOTER_LAST_TEXT = ""
    except Exception:
        pass


def mark(status: str | None = None, event: str | None = None, **fields: Any) -> None:
    with _FOOTER_LOCK:
        now = time.time()
        if status:
            _FOOTER.status = status
        if event:
            _FOOTER.last_event = event[:120]
        _FOOTER.updated_at = now
        if "endpoint" in fields and fields["endpoint"]:
            _FOOTER.endpoint = str(fields["endpoint"])
        if "write" in fields:
            _FOOTER.write = bool(fields["write"])
        if "tools" in fields:
            try:
                _FOOTER.tools = int(fields["tools"])
            except Exception:
                pass
        if "origin" in fields and fields["origin"]:
            _FOOTER.origin = str(fields["origin"])
        if "tunnel" in fields and fields["tunnel"]:
            _FOOTER.tunnel = str(fields["tunnel"])
        if "request_id" in fields and fields["request_id"]:
            try:
                _FOOTER.request_id = int(fields["request_id"])
            except Exception:
                pass
        if fields.get("working"):
            _FOOTER.working_until = max(_FOOTER.working_until, now + 8.0)
            if _FOOTER.status not in {"ERROR", "WARN", "STARTING"}:
                _FOOTER.status = "CONNECTED"
        write_state_locked(force=status is not None or bool(fields))
        draw(force=True)


def bind(root: Path, *, endpoint: str = "", write: bool = False) -> None:
    global _FOOTER_ROOT
    with _FOOTER_LOCK:
        _FOOTER_ROOT = root
        _FOOTER.endpoint = endpoint or _FOOTER.endpoint
        _FOOTER.write = bool(write)
        _FOOTER.origin = "starting"
        _FOOTER.tunnel = "starting"
        _FOOTER.status = "STARTING"
        _FOOTER.last_event = "supervisor start"
        _FOOTER.updated_at = time.time()
        write_state_locked(force=True)
        draw(force=True)


def tick() -> None:
    with _FOOTER_LOCK:
        if _FOOTER.status == "CONNECTED" and time.time() >= _FOOTER.working_until:
            # CONNECTED is a transitional state; once the route is verified and no
            # request is active, the agent is explicitly idle, not ambiguous.
            _FOOTER.status = "CONNECTED"
        write_state_locked()
        draw()


def observe_supervisor_event(level: str, message: str, fields: dict[str, object]) -> None:
    with _FOOTER_LOCK:
        level_u = level.upper().strip()
        event = str(message)
        status: str | None = None
        if level_u == "ERROR":
            status = "ERROR"
            _FOOTER.error_count += 1
        elif level_u == "WARN" and _FOOTER.status != "ERROR":
            status = "WARN"
        elif "serverBridge is live" in event or "endpoint verified" in event or "route selected" in event:
            status = "CONNECTED"
        elif "local origin is ready" in event or "http bridge up" in event:
            _FOOTER.origin = "ready"
        if "Cloudflare" in event or "tunnel" in event or "route" in event:
            if level_u in {"OK", "STATE", "INFO"}:
                _FOOTER.tunnel = "ready" if "verified" in event or "selected" in event or "allocated" in event else _FOOTER.tunnel
        mark(status, event, **fields)


def observe_stream(name: str, line: str) -> None:
    with _FOOTER_LOCK:
        clean = strip_ansi(line).strip()
        fields: dict[str, object] = {}
        request_match = re.search(r"#(\d+)\s+(GET|POST|OPTIONS)\s+(\S+)", clean)
        working = False
        status: str | None = None
        event = clean[:120] or name
        if name == "origin":
            _FOOTER.origin = "ready"
            tools_match = re.search(r"tools=(\d+)", clean)
            if tools_match:
                fields["tools"] = int(tools_match.group(1))
            if "write=true" in clean:
                fields["write"] = True
            elif "write=false" in clean:
                fields["write"] = False
            if request_match:
                _FOOTER.request_count += 1
                fields["request_id"] = int(request_match.group(1))
                method = request_match.group(2)
                path = request_match.group(3)
                if path == "/health":
                    _FOOTER.health_count += 1
                    event = f"health #{request_match.group(1)}"
                else:
                    mcp_endpoint = os.environ.get("NORTHSTAR_MCP_ENDPOINT_PATH", "/mcp")
                    working = method == "POST" or path in {mcp_endpoint, "/tools/call"}
                    event = f"{method} {path} #{request_match.group(1)}"
            if "[ERROR" in clean or "Traceback" in clean or "Exception occurred" in clean:
                status = "ERROR"
                _FOOTER.error_count += 1
            elif working:
                status = "CONNECTED"
        elif name == "cloudflared":
            _FOOTER.tunnel = "ready" if "Tunnel has been created" in clean or "Registered tunnel connection" in clean else _FOOTER.tunnel
            if "ERR" in clean or "error" in clean.lower():
                status = "WARN" if _FOOTER.status != "ERROR" else None
            event = clean[:120] or "cloudflared"
        fields["working"] = working
        mark(status, event, **fields)


def print_line(line: str) -> None:
    with _FOOTER_LOCK:
        if _footer_enabled() and _FOOTER_SUPPORTED:
            _footer_apply_layout_locked()
            clear()
            log_row = _footer_log_bottom()
            display_line = fit_ansi(line, max(1, _footer_width() - 1))
            sys.stdout.write(f"\033[{log_row};1H\033[2K{display_line}\n")
            sys.stdout.flush()
            draw(force=True)
        else:
            print(line, flush=True)
