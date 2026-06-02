from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .contracts import BRIDGE_VERSION, PROTOCOL_VERSION, BridgeContext, BridgeError, ToolSpec, MAX_PUBLIC_RESPONSE_BYTES, MAX_PUBLIC_STRING_BYTES
from .rpc_surface import (
    PUBLIC_APP_DESCRIPTION,
    PUBLIC_APP_TAGS,
    PUBLIC_APP_TITLE,
    PUBLIC_TOOL_MAP,
    public_tool_descriptors,
    tool_descriptor,
)


def rpc_result(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def rpc_error(request_id: Any, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def discovery_payload(tools: Dict[str, ToolSpec]) -> Dict[str, Any]:
    return {
        "ok": True,
        "name": "northstar-ai-bridge",
        "version": BRIDGE_VERSION,
        "title": PUBLIC_APP_TITLE,
        "description": PUBLIC_APP_DESCRIPTION,
        "tags": PUBLIC_APP_TAGS,
        "transport": "mcp-streamable-http",
        "endpoint": "/mcp",
        "http": {
            "POST /mcp": "JSON-RPC MCP messages",
            "OPTIONS /mcp": "transport preflight / allowed methods",
            "HEAD /mcp": "reachability probe / zero-byte metadata headers",
            "GET /mcp": "operator discovery; use POST for MCP clients",
        },
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "methods": ["initialize", "notifications/initialized", "ping", "tools/list", "tools/call"],
        "toolCount": len(public_tool_descriptors(tools)),
    }


def _map_tool_name(name: Any) -> str:
    text = str(name or "")
    return PUBLIC_TOOL_MAP.get(text, text)


def _bounded_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "…"
    if isinstance(value, str):
        raw = value.encode("utf-8", errors="replace")
        if len(raw) <= MAX_PUBLIC_STRING_BYTES:
            return value
        marker = "...[northstar-public-string-truncated-tail]\n"
        keep = max(1, MAX_PUBLIC_STRING_BYTES - len(marker.encode("utf-8")))
        return marker + raw[-keep:].decode("utf-8", errors="replace")
    if isinstance(value, list):
        limit = 80 if depth == 0 else 40
        out = [_bounded_value(item, depth=depth + 1) for item in value[:limit]]
        if len(value) > limit:
            out.append({"truncated_items": len(value) - limit})
        return out
    if isinstance(value, dict):
        return {str(k): _bounded_value(v, depth=depth + 1) for k, v in value.items()}
    return value


def _bounded_payload(payload: Any) -> Any:
    bounded = _bounded_value(payload)
    # Second-pass hard cap: if nested JSON is still too large, keep a safe
    # summary. This protects the MCP message stream itself, not just stdout.
    try:
        raw = json.dumps(bounded, ensure_ascii=False).encode("utf-8", errors="replace")
    except Exception:
        raw = str(bounded).encode("utf-8", errors="replace")
    if len(raw) <= MAX_PUBLIC_RESPONSE_BYTES:
        return bounded
    if isinstance(bounded, dict):
        summary = {k: bounded.get(k) for k in ("schema", "ok", "error", "message", "command_id", "allowed_surface", "exit_code", "elapsed_ms", "truncated", "output_policy") if k in bounded}
        summary["truncated"] = True
        summary["response_truncated_bytes"] = len(raw)
        summary["available_keys"] = sorted(str(k) for k in bounded.keys())[:80]
        return summary
    return {"ok": True, "truncated": True, "response_truncated_bytes": len(raw), "summary": str(type(bounded).__name__)}


def _content_summary(payload: Any) -> Any:
    if isinstance(payload, dict):
        keys = (
            "schema", "ok", "error", "message", "command_id", "allowed_surface",
            "exit_code", "elapsed_ms", "truncated", "path", "kind", "deleted",
            "bytes_written", "archive_count", "extracted_count", "warnings",
        )
        summary = {k: payload.get(k) for k in keys if k in payload}
        if "stdout" in payload:
            summary["stdout_tail_preview"] = str(payload.get("stdout", ""))[-2000:]
        if "stderr" in payload and payload.get("stderr"):
            summary["stderr_tail_preview"] = str(payload.get("stderr", ""))[-2000:]
        if not summary:
            summary = {"keys": sorted(str(k) for k in payload.keys())[:40]}
        return summary
    if isinstance(payload, list):
        return {"list_count": len(payload), "first": payload[:3]}
    return payload


def _tool_result_payload(payload: Any) -> Dict[str, Any]:
    payload = _bounded_payload(payload)
    result: Dict[str, Any] = {
        "content": [{"type": "text", "text": json.dumps(_content_summary(payload), ensure_ascii=False, indent=2)}],
        "isError": False,
    }
    if isinstance(payload, dict):
        result["structuredContent"] = payload
    return result


def _tool_error_payload(error: Any) -> Dict[str, Any]:
    error = _bounded_payload(error)
    result: Dict[str, Any] = {
        "content": [{"type": "text", "text": json.dumps(_content_summary(error), ensure_ascii=False, indent=2)}],
        "isError": True,
    }
    if isinstance(error, dict):
        result["structuredContent"] = error
    return result


def _sanitize_public_arguments(public_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if public_name == "execute_suite_command":
        # Public execution is deliberately narrower than the internal
        # northstar.suite_command tool: no allow_unlisted, no arbitrary shell,
        # bounded timeout, and only the declared allow-list inside suite.py may run.
        command_id = str(arguments.get("command_id", "")).strip()
        sanitized: Dict[str, Any] = {"command_id": command_id, "allow_unlisted": False}
        if "timeout_sec" in arguments:
            try:
                sanitized["timeout_sec"] = max(0, int(arguments.get("timeout_sec", 0)))
            except Exception:
                sanitized["timeout_sec"] = 0
        if "requires_openai_key" in arguments:
            sanitized["requires_openai_key"] = bool(arguments.get("requires_openai_key"))
        if "allow_unlisted" in arguments:
            sanitized["allow_unlisted"] = bool(arguments.get("allow_unlisted"))
        return sanitized
    if public_name == "list_suite_actions":
        sanitized = {}
        if "timeout_sec" in arguments:
            try:
                sanitized["timeout_sec"] = max(5, min(int(arguments.get("timeout_sec", 60)), 300))
            except Exception:
                sanitized["timeout_sec"] = 60
        return sanitized
    return arguments


def _decorate_public_result(public_name: str, arguments: Dict[str, Any], payload: Any) -> Any:
    if public_name != "execute_suite_command" or not isinstance(payload, dict):
        return payload
    command_id = str(arguments.get("command_id", "")).strip()
    allowed_surface = "unknown"
    try:
        from .suite import READ_ONLY_COMMANDS, WRITE_COMMANDS
        if command_id in READ_ONLY_COMMANDS:
            allowed_surface = "read_only"
        elif command_id in WRITE_COMMANDS:
            allowed_surface = "write_allowlist"
    except Exception:
        pass
    return {
        "schema": "northstar.suite.execute_command.v1",
        "command_id": command_id,
        "allowed_surface": allowed_surface,
        **payload,
    }


def handle_rpc(ctx: BridgeContext, tools: Dict[str, ToolSpec], request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    try:
        if method == "initialize":
            return rpc_result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": "northstar-ai-bridge", "title": PUBLIC_APP_TITLE, "version": BRIDGE_VERSION},
                "capabilities": {"tools": {"listChanged": False}},
                "instructions": "North Star Engine operator MCP bridge. execute_suite_command, write_text_file and delete_path are always visible; write/delete execution requires bridge write mode and remains bounded to the repository root. Project tool registry exposes discovered tools such as grep, sed, git, cargo and descriptor tools as first-class MCP tools with bounded stdout/stderr.",
            })
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return rpc_result(request_id, {})
        if method == "tools/list":
            return rpc_result(request_id, {"tools": public_tool_descriptors(tools)})
        if method == "tools/call":
            requested_name = str(params.get("name") or "")
            name = _map_tool_name(requested_name)
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            if requested_name in PUBLIC_TOOL_MAP:
                arguments = _sanitize_public_arguments(requested_name, arguments)
            if name not in tools:
                raise BridgeError("unknown tool", "unknown_tool", {"name": name})
            payload = tools[name].handler(arguments)
            payload = _decorate_public_result(requested_name, arguments, payload)
            return rpc_result(request_id, _tool_result_payload(payload))
        return rpc_error(request_id, -32601, "method not found", {"method": method})
    except BridgeError as exc:
        return rpc_result(request_id, _tool_error_payload({"ok": False, "error": exc.code, "message": str(exc), **exc.data}))
    except Exception as exc:
        return rpc_result(request_id, _tool_error_payload({"ok": False, "error": "internal_error", "message": str(exc)}))


def handle_rpc_batch(ctx: BridgeContext, tools: Dict[str, ToolSpec], request: Any) -> tuple[Any, int]:
    """Handle a single JSON-RPC message or a JSON-RPC batch.

    Returns (payload, status_code).  Pure notifications return HTTP 202.
    """
    if isinstance(request, list):
        if not request:
            return rpc_error(None, -32600, "invalid request", {"reason": "empty batch"}), 400
        responses: list[Dict[str, Any]] = []
        for item in request:
            if not isinstance(item, dict):
                responses.append(rpc_error(None, -32600, "invalid request", {"reason": "batch item is not object"}))
                continue
            response = handle_rpc(ctx, tools, item)
            if response is not None:
                responses.append(response)
        if not responses:
            return {"ok": True, "notification": True}, 202
        return responses, 200

    if not isinstance(request, dict):
        return rpc_error(None, -32600, "invalid request", {"reason": "request is not object"}), 400

    response = handle_rpc(ctx, tools, request)
    if response is None:
        return {"ok": True, "notification": True}, 202
    return response, 200
