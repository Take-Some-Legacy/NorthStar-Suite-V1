from __future__ import annotations

import http.server
import json
import mimetypes
import os
import socketserver
import threading
import time
import urllib.parse
from itertools import count
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import access, dataset, oauth, release_info, repo, status as bridge_status
from .cluster_doctor import run_cluster_doctor
from .cluster_topology import cluster_summary
from .console import emit
from .contracts import BRIDGE_VERSION, BridgeContext
from .registry import build_tools
from .rpc import discovery_payload, handle_rpc_batch, tool_descriptor, server_info
from .paths import rel
from .mcp_routes import all_head_paths, is_direct_tool_call_path, is_discovery_path, is_mcp_path, is_operator_get_path, route_label

_REQUEST_IDS = count(1)
_SECRET_KEY_PARTS = ("key", "token", "secret", "password", "authorization", "credential")
_PREVIEW_LIMIT = 700
_SLOW_MS = 1000
_RESERVED_LOG_FIELDS = {"method", "path", "route", "status", "elapsed_ms", "bytes", "id", "request_id"}
_MAX_FAVICON_BYTES = 256 * 1024
_FAVICON_CANDIDATES = (
    "favicon.ico",
    "docs/favicon.ico",
    ".takesome/config/favicon.ico",
    "noesis/bridge/favicon.ico",
    "NewEngine/neocore2/assets/favicon.ico",
    "NewEngine/neocore2/assets/ui/favicon.ico",
)


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    ctx: BridgeContext
    tools: Dict[str, Any]
    status_interval: int


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = f"NorthStarAIBridge/{BRIDGE_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _auth_required(self, path: str) -> bool:
        ctx = self.server.ctx  # type: ignore[attr-defined]
        return is_direct_tool_call_path(path, ctx.mcp_routes) or is_operator_get_path(path, ctx.mcp_routes)

    def _rpc_body_requires_auth(self, body: Any) -> bool:
        def one(item: Any) -> bool:
            return isinstance(item, dict) and item.get("method") == "tools/call"
        if isinstance(body, list):
            return any(one(item) for item in body)
        return one(body)

    def _authorized(self, path: str) -> bool:
        if not self._auth_required(path):
            return True
        ctx = self.server.ctx  # type: ignore[attr-defined]
        return access.authorized(ctx.root, self.headers)

    def _send_forbidden_local(self, request_id: int, started: float) -> None:
        ctx = self.server.ctx  # type: ignore[attr-defined]
        self._send({"ok": False, "error": "forbidden_local_token_required", "auth": access.status(ctx.root)}, 403, request_id=request_id, started=started)

    def _send_oauth_required(self, request_id: int, started: float) -> None:
        ctx = self.server.ctx  # type: ignore[attr-defined]
        routes = ctx.mcp_routes
        current_path = _request_path(self.path)
        payload = {"ok": False, "error": "oauth_required", "auth": oauth.protected_resource_metadata(oauth.base_url_from_headers(self.headers), current_path if is_mcp_path(current_path, routes) else routes.endpoint)}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("WWW-Authenticate", f'Bearer resource_metadata="{oauth.base_url_from_headers(self.headers)}/.well-known/oauth-protected-resource"')
        self._send_common_headers()
        self.end_headers()
        self.wfile.write(data)
        _emit_response("POST", _request_path(self.path), request_id, 401, int((time.time() - started) * 1000), len(data), response_status="oauth_required")

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization, MCP-Protocol-Version, Mcp-Session-Id")
        self.send_header("Access-Control-Expose-Headers", "MCP-Protocol-Version, Mcp-Session-Id")
        self.send_header("MCP-Protocol-Version", "2025-03-26")
        self.send_header("X-Noesis-Title", release_info.BRIDGE_PUBLIC_TITLE)
        self.send_header("X-MCP-Server-Title", release_info.BRIDGE_PUBLIC_TITLE)
        self.send_header("X-Noesis-Short-Title", release_info.BRIDGE_SHORT_TITLE)
        self.send_header("X-Noesis-Server", release_info.BRIDGE_SERVICE_NAME)
        self.send_header("X-Noesis-Product", release_info.BRIDGE_PRODUCT_NAME)
        self.send_header("X-Noesis-Runtime-Layout", release_info.BRIDGE_RUNTIME_LAYOUT)
        self.send_header("X-Noesis-Web-Contract", "noesis.web.v1")
        self.send_header("X-Noesis-Web-Surface", "bridge.mcp")
        self.send_header("Cache-Control", "no-store")

    def do_OPTIONS(self) -> None:
        started = time.time()
        request_id = next(_REQUEST_IDS)
        path = _request_path(self.path)
        _emit_request("OPTIONS", path, request_id)
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self._send_common_headers()
        self.end_headers()
        _emit_response("OPTIONS", path, request_id, 204, int((time.time() - started) * 1000), 0, response_status="ok")

    def _send(
        self,
        payload: Any,
        status_code: int = 200,
        *,
        request_id: Optional[int] = None,
        started: Optional[float] = None,
        trace: Optional[Dict[str, Any]] = None,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        if isinstance(payload, (bytes, bytearray)):
            data = bytes(payload)
        elif content_type.startswith("text/event-stream"):
            data = str(payload).encode("utf-8")
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        path = _request_path(self.path)
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self._send_common_headers()
            self.end_headers()
            if data:
                self.wfile.write(data)
        except OSError as exc:
            if _is_client_disconnect(exc):
                _emit_client_disconnect("POST", path, request_id, started, exc, trace=trace)
                return
            raise

        if started is not None:
            elapsed_ms = int((time.time() - started) * 1000)
            extra: Dict[str, Any] = {}
            if trace:
                extra.update(trace)
            summary = _response_summary(payload)
            if summary:
                extra.update(summary)
            _emit_response(self.command, _request_path(self.path), request_id, status_code, elapsed_ms, len(data), **extra)

    def _send_binary(
        self,
        data: bytes,
        *,
        content_type: str,
        status_code: int = 200,
        request_id: Optional[int] = None,
        started: Optional[float] = None,
        trace: Optional[Dict[str, Any]] = None,
        cache_control: str = "public, max-age=3600",
    ) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization, MCP-Protocol-Version, Mcp-Session-Id")
        self.send_header("Access-Control-Expose-Headers", "MCP-Protocol-Version, Mcp-Session-Id")
        self.send_header("MCP-Protocol-Version", "2025-03-26")
        self.send_header("X-Noesis-Title", release_info.BRIDGE_PUBLIC_TITLE)
        self.send_header("X-MCP-Server-Title", release_info.BRIDGE_PUBLIC_TITLE)
        self.send_header("X-Noesis-Short-Title", release_info.BRIDGE_SHORT_TITLE)
        self.send_header("X-Noesis-Server", release_info.BRIDGE_SERVICE_NAME)
        self.send_header("X-Noesis-Product", release_info.BRIDGE_PRODUCT_NAME)
        self.send_header("X-Noesis-Runtime-Layout", release_info.BRIDGE_RUNTIME_LAYOUT)
        self.send_header("X-Noesis-Web-Contract", "noesis.web.v1")
        self.send_header("X-Noesis-Web-Surface", "bridge.mcp")
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        if data:
            self.wfile.write(data)

        if started is not None:
            elapsed_ms = int((time.time() - started) * 1000)
            extra: Dict[str, Any] = {"binary": True}
            if trace:
                extra.update(trace)
            _emit_response(self.command, _request_path(self.path), request_id, status_code, elapsed_ms, len(data), **extra)

    def _send_favicon(self, ctx: BridgeContext, *, request_id: Optional[int], started: float) -> None:
        favicon = _find_favicon(ctx)
        if favicon is None:
            self._send(
                {"ok": False, "error": "not_found", "path": "/favicon.ico", "optional": True},
                404,
                request_id=request_id,
                started=started,
                trace={"optional_asset": "favicon.ico"},
            )
            return

        size = favicon.stat().st_size
        if size > _MAX_FAVICON_BYTES:
            self._send(
                {
                    "ok": False,
                    "error": "asset_too_large",
                    "path": rel(ctx.root, favicon),
                    "size_bytes": size,
                    "max_bytes": _MAX_FAVICON_BYTES,
                },
                413,
                request_id=request_id,
                started=started,
                trace={"optional_asset": "favicon.ico", "asset_path": rel(ctx.root, favicon)},
            )
            return

        content_type = mimetypes.guess_type(favicon.name)[0] or "image/x-icon"
        self._send_binary(
            favicon.read_bytes(),
            content_type=content_type,
            request_id=request_id,
            started=started,
            trace={"optional_asset": "favicon.ico", "asset_path": rel(ctx.root, favicon)},
        )

    def _read_body_bytes(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def _read_json(self) -> Tuple[Any, bytes]:
        raw = self._read_body_bytes() or b"{}"
        if not raw:
            return {}, raw
        return json.loads(raw.decode("utf-8", errors="replace")), raw

    def do_HEAD(self) -> None:
        started = time.time()
        request_id = next(_REQUEST_IDS)
        path = _request_path(self.path)
        _emit_request("HEAD", path, request_id)
        ctx = self.server.ctx  # type: ignore[attr-defined]
        status_code = 200 if path in all_head_paths(ctx.mcp_routes) else 404
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", "0")
        self._send_common_headers()
        self.end_headers()
        _emit_response("HEAD", path, request_id, status_code, int((time.time() - started) * 1000), 0, response_status="ok" if status_code < 400 else "not_found")

    def do_GET(self) -> None:
        started = time.time()
        request_id = next(_REQUEST_IDS)
        path = _request_path(self.path)
        _emit_request("GET", path, request_id)
        try:
            if not self._authorized(path):
                self._send_forbidden_local(request_id, started)
                return
            ctx = self.server.ctx  # type: ignore[attr-defined]
            tools = self.server.tools  # type: ignore[attr-defined]
            routes = ctx.mcp_routes
            if oauth.is_well_known_path(path):
                status_code, payload = oauth.well_known_response(oauth.base_url_from_headers(self.headers), path, routes.endpoint)
                self._send(payload, status_code=status_code, request_id=request_id, started=started)
            elif path == "/oauth/authorize":
                status_code, headers, data = oauth.authorize(ctx.root, self.headers, urllib.parse.urlparse(self.path).query)
                self.send_response(status_code)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self._send_common_headers()
                self.end_headers()
                if data:
                    self.wfile.write(data)
                _emit_response("GET", path, request_id, status_code, int((time.time() - started) * 1000), len(data), response_status="ok" if status_code < 400 else "error")
            elif path == "/favicon.ico":
                self._send_favicon(ctx, request_id=request_id, started=started)
            elif path == "/health":
                binding = ctx.host_binding
                self._send(
                    {
                        "schema": "noesis.suite.health.v1",
                        "ok": True,
                        "name": release_info.BRIDGE_SERVICE_NAME,
                        "title": release_info.BRIDGE_PUBLIC_TITLE,
                        "description": release_info.BRIDGE_PUBLIC_DESCRIPTION,
                        "version": BRIDGE_VERSION,
                        "releaseName": release_info.BRIDGE_RELEASE_NAME,
                        "releaseNotes": release_info.BRIDGE_RELEASE_NOTES,
                        "serverInfo": server_info(ctx),
                        "_meta": {
                            "title": release_info.BRIDGE_PUBLIC_TITLE,
                            "server/title": release_info.BRIDGE_PUBLIC_TITLE,
                            "description": release_info.BRIDGE_PUBLIC_DESCRIPTION,
                            "product": release_info.BRIDGE_PRODUCT_NAME,
                            "vendor": release_info.BRIDGE_VENDOR,
                        },
                        "mode": "http",
                        "machine_id": binding.machine_id if binding else "",
                        "cluster_id": binding.cluster_id if binding else "",
                        "machine_role": binding.role if binding else "",
                        "endpoint_url": binding.endpoint_url if binding else "",
                        "health_url": binding.health_url if binding else "",
                        "is_clustered": binding.is_clustered if binding else False,
                        "endpoints": [*ctx.mcp_routes.mcp_paths, "/status", "/cluster", "/cluster/doctor", "/tools", "/dataset", "/logs", "/favicon.ico"],
                    },
                    request_id=request_id,
                    started=started,
                    trace={"machine": binding.machine_id if binding else "", "cluster": binding.cluster_id if binding else ""},
                )
            elif path == "/cluster":
                self._send(cluster_summary(ctx.host_binding), request_id=request_id, started=started)
            elif path == "/cluster/doctor":
                params = _query_params(self.path)
                doctor = run_cluster_doctor(
                    ctx.host_binding,
                    timeout_sec=params.get("timeout", "1.5"),
                    include_status=_query_truthy(params, "status", True),
                    include_disabled=_query_truthy(params, "include_disabled", False),
                )
                self._send(doctor, request_id=request_id, started=started, trace={"cluster_result": doctor.get("result"), "request_count": (doctor.get("summary") or {}).get("request_count")})
            elif is_discovery_path(path, ctx.mcp_routes):
                payload = discovery_payload(tools, ctx.mcp_routes)
                payload["serverInfo"] = server_info(ctx)
                payload["_meta"] = {
                    "title": payload["serverInfo"].get("title"),
                    "server/title": payload["serverInfo"].get("title"),
                    "description": payload["serverInfo"].get("description"),
                    "product": payload["serverInfo"].get("product"),
                    "vendor": payload["serverInfo"].get("vendor"),
                }
                accept = self.headers.get("Accept", "")
                if "text/event-stream" in accept:
                    event = "event: endpoint\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                    self._send(event, request_id=request_id, started=started, content_type="text/event-stream; charset=utf-8")
                else:
                    self._send(payload, request_id=request_id, started=started)
            elif path == "/status":
                self._send(bridge_status.status(ctx, {}), request_id=request_id, started=started)
            elif path == "/tools":
                self._send({"ok": True, "tools": [tool_descriptor(tool) for tool in tools.values()]}, request_id=request_id, started=started, trace={"tool_count": len(tools)})
            elif path == "/dataset":
                self._send(dataset.status(ctx, {}), request_id=request_id, started=started)
            elif path == "/logs":
                self._send(repo.list_logs(ctx, {"limit": 30}), request_id=request_id, started=started)
            else:
                self._send({"ok": False, "error": "not_found", "path": path}, 404, request_id=request_id, started=started)
        except Exception as exc:
            self._send({"ok": False, "error": "http_exception", "message": str(exc)}, 500, request_id=request_id, started=started, trace={"error_details": str(exc)})

    def do_POST(self) -> None:
        started = time.time()
        request_id = next(_REQUEST_IDS)
        path = _request_path(self.path)
        ctx = self.server.ctx  # type: ignore[attr-defined]
        tools = self.server.tools  # type: ignore[attr-defined]

        if path == "/oauth/token":
            raw = self._read_body_bytes()
            trace = {"raw_bytes": len(raw), "oauth_endpoint": "token"}
            _emit_request("POST", path, request_id, **trace)
            try:
                status_code, headers, payload = oauth.token(ctx.root, raw, self.headers.get("Content-Type", ""))
                self._send(payload, status_code=status_code, request_id=request_id, started=started, trace=trace)
            except Exception as exc:
                self._send({"ok": False, "error": "oauth_token_exception", "message": str(exc)}, 500, request_id=request_id, started=started, trace={**trace, "error_details": str(exc)})
            return

        try:
            body, raw = self._read_json()
        except Exception as exc:
            _emit_request("POST", path, request_id, error="invalid_json", error_details=str(exc))
            self._send({"ok": False, "error": "invalid_json", "message": str(exc)}, 400, request_id=request_id, started=started, trace={"error_details": str(exc)})
            return

        trace = _request_trace(path, body, len(raw))
        _emit_request("POST", path, request_id, **trace)
        try:
            if path == "/oauth/register":
                payload = oauth.register_client(ctx.root, body if isinstance(body, dict) else {})
                self._send(payload, status_code=201, request_id=request_id, started=started, trace=trace)
                return
            if is_mcp_path(path, ctx.mcp_routes) and self._rpc_body_requires_auth(body) and not access.authorized(ctx.root, self.headers):
                self._send_oauth_required(request_id, started)
                return
            if not is_mcp_path(path, ctx.mcp_routes) and not self._authorized(path):
                self._send_forbidden_local(request_id, started)
                return
            if is_mcp_path(path, ctx.mcp_routes):
                response, status_code = handle_rpc_batch(ctx, tools, body)
                self._send(response, status_code=status_code, request_id=request_id, started=started, trace=trace)
            elif is_direct_tool_call_path(path, ctx.mcp_routes):
                response = _handle_direct_tool_call(ctx, tools, body)
                self._send(response, request_id=request_id, started=started, trace=trace)
            else:
                self._send({"ok": False, "error": "not_found", "path": path}, 404, request_id=request_id, started=started, trace=trace)
        except Exception as exc:
            if _is_client_disconnect(exc):
                _emit_client_disconnect("POST", path, request_id, started, exc, trace=trace)
                return
            self._send({"ok": False, "error": "http_exception", "message": str(exc)}, 500, request_id=request_id, started=started, trace={**trace, "error_details": str(exc)})


def _find_favicon(ctx: BridgeContext) -> Optional[Path]:
    root = ctx.root.resolve()
    for rel_path in _FAVICON_CANDIDATES:
        candidate = (root / rel_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file() and candidate.name.lower() == "favicon.ico":
            return candidate
    return None


def _request_path(raw: str) -> str:
    return urllib.parse.urlparse(raw).path or "/"




def _query_params(raw: str) -> Dict[str, str]:
    parsed = urllib.parse.urlparse(raw)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    return {str(key): str(values[-1]) if values else "" for key, values in query.items()}


def _query_truthy(params: Dict[str, str], name: str, default: bool = False) -> bool:
    if name not in params:
        return default
    return str(params.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _route(path: str) -> str:
    return route_label(path)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _suppress_health_log(path: str, *, status_code: int | None = None, elapsed_ms: int = 0, error: str = "") -> bool:
    if _truthy_env("NORTHSTAR_BRIDGE_LOG_HEALTH"):
        return False
    if _route(path) != "health" or error:
        return False
    if status_code is not None and status_code >= 400:
        return False
    if elapsed_ms >= _SLOW_MS:
        return False
    return True


def _log_level_for_request(path: str, error: str = "") -> str:
    if error:
        return "ERROR"
    return "HEALTH" if _route(path) == "health" else "HTTP"


def _log_level_for_response(path: str, status_code: int, elapsed_ms: int) -> str:
    if elapsed_ms >= _SLOW_MS:
        return "SLOW"
    if status_code >= 500:
        return "ERROR"
    if status_code >= 400:
        return "WARN"
    return "HEALTH" if _route(path) == "health" else "OK"


def _safe_extra(extra: Dict[str, Any]) -> Dict[str, Any]:
    # Protect structured emitters from bugs where a field is passed both as a
    # positional argument and inside **extra. This directly fixes the previous
    # `_emit_response() got multiple values for argument 'path'` crash.
    return {str(k): v for k, v in extra.items() if str(k) not in _RESERVED_LOG_FIELDS}


def _is_client_disconnect(exc: BaseException) -> bool:
    if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        return True
    if not isinstance(exc, OSError):
        return False
    # Windows: WSAECONNABORTED/WSAECONNRESET. POSIX: EPIPE/ECONNRESET.
    return getattr(exc, "winerror", None) in {10053, 10054} or getattr(exc, "errno", None) in {32, 104, 10053, 10054}


def _emit_client_disconnect(method: str, path: str, request_id: Optional[int], started: Optional[float], exc: BaseException, *, trace: Optional[Dict[str, Any]] = None) -> None:
    elapsed_ms = int((time.time() - started) * 1000) if started is not None else 0
    extra = dict(trace or {})
    extra.update({"response_status": "client_disconnected", "error_details": str(exc)})
    # 499 is not sent to the client here; it is an operator-log status meaning
    # the client/tunnel closed the request before the bridge could deliver the
    # response. This must not be reported as a bridge crash.
    _emit_response(method, path, request_id, 499, elapsed_ms, 0, **extra)


def _emit_request(method: str, path: str, request_id: Optional[int], **extra: Any) -> None:
    if _suppress_health_log(path, error=str(extra.get("error", ""))):
        return
    level = _log_level_for_request(path, str(extra.get("error", "")))
    label = f"#{request_id} {method} {path}" if request_id is not None else f"{method} {path}"
    fields: Dict[str, Any] = {"id": request_id, "method": method, "path": path, "route": _route(path)}
    fields.update(_safe_extra(extra))
    emit(level, label, **fields)


def _emit_response(method: str, path: str, request_id: Optional[int], status_code: int, elapsed_ms: int, bytes_count: int, **extra: Any) -> None:
    if _suppress_health_log(path, status_code=status_code, elapsed_ms=elapsed_ms):
        return
    level = _log_level_for_response(path, status_code, elapsed_ms)
    label = f"#{request_id} {method} {path} -> {status_code}" if request_id is not None else f"{method} {path} -> {status_code}"
    fields: Dict[str, Any] = {
        "id": request_id,
        "method": method,
        "path": path,
        "route": _route(path),
        "status": status_code,
        "elapsed_ms": elapsed_ms,
        "bytes": bytes_count,
    }
    fields.update(_safe_extra(extra))
    emit(level, label, **fields)


def _handle_direct_tool_call(ctx: BridgeContext, tools: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    name = str(body.get("name") or body.get("tool") or "")
    args = body.get("arguments") or body.get("args") or {}
    if name not in tools:
        return {"ok": False, "error": "unknown_tool", "tool": name, "available": sorted(tools)}
    try:
        result = tools[name].handler(args if isinstance(args, dict) else {})
        return {"ok": True, "tool": name, "result": result}
    except Exception as exc:
        return {"ok": False, "error": "tool_exception", "tool": name, "message": str(exc)}


def _request_trace(path: str, body: Any, raw_bytes: int) -> Dict[str, Any]:
    if isinstance(body, list):
        return {"raw_bytes": raw_bytes, "rpc_batch": len(body)}
    if not isinstance(body, dict):
        return {"raw_bytes": raw_bytes, "rpc_invalid": type(body).__name__}
    method = str(body.get("method", ""))
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    tool = ""
    args: Any = {}
    if method == "tools/call":
        tool = str(params.get("name", ""))
        args = params.get("arguments") or {}
    elif is_direct_tool_call_path(path):
        tool = str(body.get("name") or body.get("tool") or "")
        args = body.get("arguments") or body.get("args") or {}
    fields: Dict[str, Any] = {"raw_bytes": raw_bytes}
    if method:
        fields["rpc_method"] = method
    if tool:
        fields["tool"] = tool
    if args:
        fields["args"] = _preview(args)
    if "id" in body:
        fields["rpc_id"] = body.get("id")
    return fields


def _response_summary(payload: Any) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    if not isinstance(payload, dict):
        return {"result": _preview(payload)}
    if "error" in payload and payload.get("error"):
        err = payload.get("error")
        fields["response_status"] = "error"
        fields["error_details"] = _preview(err)
        return fields
    result = payload.get("result", payload)
    fields["response_status"] = "ok" if payload.get("ok", True) is not False else "failed"
    summary = _result_preview(result)
    if summary:
        fields["result"] = summary
    return fields


def _result_preview(result: Any) -> str:
    if isinstance(result, dict):
        compact: Dict[str, Any] = {}
        for key in ("ok", "tool", "path", "browser_path", "knowledge_path", "file_count", "directory_count", "topic_count", "completed_steps", "exit_code", "error", "message", "schema", "status", "run_id"):
            if key in result:
                compact[key] = result[key]
        if not compact:
            compact = {"keys": sorted(str(k) for k in result.keys())[:12]}
        return _preview(compact)
    if isinstance(result, list):
        return _preview({"list_count": len(result), "first": result[:2]})
    return _preview(result)


def _preview(value: Any, limit: int = _PREVIEW_LIMIT) -> str:
    safe = _sanitize(value)
    try:
        text = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        text = str(safe)
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(part in key_text.lower() for part in _SECRET_KEY_PARTS):
                out[key_text] = "***"
            else:
                out[key_text] = _sanitize(item)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:20]] + (["…"] if len(value) > 20 else [])
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "…"
    return value


def _heartbeat(server: ThreadingHTTPServer, interval: int) -> None:
    while True:
        time.sleep(max(5, interval))
        binding = server.ctx.host_binding
        emit("STATE", "heartbeat", tools=len(server.tools), write=server.ctx.write_enabled, machine=(binding.machine_id if binding else ""), cluster=(binding.cluster_id if binding else ""))


def run_http(ctx: BridgeContext, host: str, port: int, status_interval: int = 30) -> int:
    tools = build_tools(ctx)
    server = ThreadingHTTPServer((host, port), Handler)
    server.ctx = ctx
    server.tools = tools
    server.status_interval = status_interval
    binding = ctx.host_binding
    emit("STATE", "http bridge up", host=host, port=port, tools=len(tools), write=ctx.write_enabled, machine=(binding.machine_id if binding else ""), cluster=(binding.cluster_id if binding else ""), endpoint=(binding.endpoint_url if binding else ""))
    threading.Thread(target=_heartbeat, args=(server, status_interval), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        emit("STATE", "http bridge stopping", host=host, port=port)
    finally:
        server.server_close()
    return 0
