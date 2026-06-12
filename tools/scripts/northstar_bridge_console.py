#!/usr/bin/env python3
"""Pretty console instrumentation for North Star AI Bridge.

This module is intentionally a small runtime patch layer: the stable public
entrypoint imports the bridge implementation, then installs richer console
logging without forcing the bridge core to know about terminal presentation.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from dataclasses import replace
from typing import Any, Callable, Dict

_INSTALLED = False

ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "gray": "\033[90m",
}


def _enable_windows_ansi() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        flag = 0x0004
        ok = False
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | flag)
                ok = True
        return ok
    except Exception:
        return False


_ANSI_READY = _enable_windows_ansi()


def color(text: Any, name: str) -> str:
    value = str(text)
    if os.environ.get("NO_COLOR") or not _ANSI_READY:
        return value
    return f"{ANSI.get(name, '')}{value}{ANSI['reset']}"


def emit(level: str, message: str, **fields: Any) -> None:
    now = dt.datetime.now().strftime("%H:%M:%S")
    level_u = level.upper()
    level_color = {
        "OK": "green",
        "INFO": "cyan",
        "STATE": "blue",
        "HTTP": "blue",
        "TOOL": "magenta",
        "WARN": "yellow",
        "ERROR": "red",
    }.get(level_u, "white")
    pieces = [
        color("[", "gray") + color(now, "dim") + color("]", "gray"),
        color("[", "gray") + color(level_u, level_color) + color("]", "gray"),
        color(message, "white" if level_u not in {"ERROR", "WARN"} else level_color),
    ]
    for key, value in fields.items():
        if value is None:
            continue
        pieces.append(color(str(key), "gray") + color("=", "dim") + color(value, "cyan" if key in {"tool", "method", "path", "url", "endpoint"} else "white"))
    print(" ".join(pieces), file=sys.stderr, flush=True)


def _tool_ok(payload: Any) -> bool:
    if isinstance(payload, dict):
        return bool(payload.get("ok", True)) and not payload.get("error")
    return True


def install(bridge_module: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_tools = bridge_module._tools
    original_run_http = bridge_module.run_http
    original_do_get = bridge_module.Handler.do_GET
    original_do_post = bridge_module.Handler.do_POST

    def patched_tools(ctx: Any) -> Dict[str, Any]:
        tools = original_tools(ctx)
        patched: Dict[str, Any] = {}
        for name, spec in tools.items():
            handler = spec.handler

            def make_handler(tool_name: str, wrapped: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
                def call(args: Dict[str, Any]) -> Dict[str, Any]:
                    started = time.perf_counter()
                    emit("TOOL", "call", tool=tool_name, write=getattr(ctx, "write_enabled", False))
                    try:
                        result = wrapped(args)
                    except Exception as exc:
                        emit("ERROR", "tool crashed", tool=tool_name, error=f"{type(exc).__name__}: {exc}", elapsed_ms=int((time.perf_counter() - started) * 1000))
                        raise
                    emit("OK" if _tool_ok(result) else "WARN", "tool completed", tool=tool_name, elapsed_ms=int((time.perf_counter() - started) * 1000))
                    return result
                return call

            try:
                patched[name] = replace(spec, handler=make_handler(name, handler))
            except Exception:
                # Fallback for non-dataclass ToolSpec-compatible objects.
                spec.handler = make_handler(name, handler)
                patched[name] = spec
        return patched

    def patched_run_http(ctx: Any, host: str, port: int, status_interval: int = 30) -> int:
        emit("STATE", "HTTP bridge starting", endpoint=f"http://{host}:{port}{getattr(getattr(ctx, 'mcp_routes', None), 'endpoint', '/mcp')}", write=getattr(ctx, "write_enabled", False), root=getattr(ctx, "root", ""))
        rc = original_run_http(ctx, host, port, status_interval)
        emit("STATE", "HTTP bridge stopped", rc=rc)
        return rc

    def patched_do_get(self: Any) -> None:
        path = getattr(self, "path", "")
        started = time.perf_counter()
        emit("HTTP", "request", method="GET", path=path)
        try:
            return original_do_get(self)
        finally:
            emit("OK", "response", method="GET", path=path, elapsed_ms=int((time.perf_counter() - started) * 1000))

    def patched_do_post(self: Any) -> None:
        path = getattr(self, "path", "")
        started = time.perf_counter()
        emit("HTTP", "request", method="POST", path=path)
        try:
            return original_do_post(self)
        finally:
            emit("OK", "response", method="POST", path=path, elapsed_ms=int((time.perf_counter() - started) * 1000))

    bridge_module._tools = patched_tools
    bridge_module.run_http = patched_run_http
    bridge_module.Handler.do_GET = patched_do_get
    bridge_module.Handler.do_POST = patched_do_post
    emit("OK", "console instrumentation installed", style="split-color", tool_logging=True)
