from __future__ import annotations
import json
from typing import Any, Dict, Optional
from . import release_info
from .contracts import BRIDGE_VERSION, PROTOCOL_VERSION, BridgeContext, BridgeError, ToolSpec, MAX_PUBLIC_RESPONSE_BYTES, MAX_PUBLIC_STRING_BYTES
from .mcp_routes import DEFAULT_MCP_ROUTES, McpRouteProfile
from .rpc_surface import (
    PUBLIC_APP_DESCRIPTION,
    PUBLIC_APP_TAGS,
    PUBLIC_APP_TITLE,
    PUBLIC_TOOL_MAP,
    public_tool_descriptors,
    tool_descriptor,
)

DEFAULT_PUBLIC_SUITE_TIMEOUT_SEC = 120
MAX_PUBLIC_SUITE_TIMEOUT_SEC = 600
PUBLIC_CONTENT_STREAM_PREVIEW_BYTES = 4 * 1024


def _path_text(value: Any) -> str:
    try:
        return str(value.resolve())
    except Exception:
        return str(value)


def _dataset_root_for_agent(ctx: BridgeContext) -> str:
    try:
        from . import dataset as dataset_module
        summary = dataset_module.status(ctx, {})
        if isinstance(summary, dict):
            directories = summary.get("directories") if isinstance(summary.get("directories"), dict) else {}
            value = summary.get("dataSetDirectory") or directories.get("root")
            if value:
                return str(value)
    except Exception:
        pass
    try:
        return _path_text(ctx.suite_root / "dataSet")
    except Exception:
        return ""


def _agent_workspace(ctx: BridgeContext) -> Dict[str, Any]:
    return {
        "schema": "northstar.bridge.workspace.v1",
        "workspaceRoot": _path_text(ctx.root.resolve()),
        "kind": "projects_repository",
        "containsMultipleProjects": True,
        "projectSelectionRequired": True,
        "activeProjectRoot": None,
        "selectionPolicy": {
            "beforeProjectScopedWork": "Resolve activeProjectRoot from the user request, a trusted prior active project context, or ask which project to use.",
            "doNotAssumeWorkspaceRootIsProjectRoot": True,
            "safeDiscovery": "List top-level directories under workspaceRoot to propose project candidates when the user did not specify a project.",
        },
    }


def _agent_paths(ctx: BridgeContext) -> Dict[str, Any]:
    suite_root = ctx.operator_root.resolve()
    workspace_root = ctx.root.resolve()
    tools_root = suite_root / "tools"
    runtime_root = ctx.suite_root.resolve()
    dataset_root = _dataset_root_for_agent(ctx)
    return {
        "schema": "northstar.bridge.agent_paths.v1",
        "suiteRoot": _path_text(suite_root),
        "workspaceRoot": _path_text(workspace_root),
        "activeProjectRoot": None,
        "toolsRoot": _path_text(tools_root),
        "datasetRoot": dataset_root,
        "runtimeRoot": _path_text(runtime_root),
        "semantics": {
            "suiteRoot": "Installed NOESIS/NorthStar Suite source and control plane root.",
            "workspaceRoot": "Projects repository/container. It contains multiple projects and is not itself the active project.",
            "activeProjectRoot": "Concrete selected project root for the current task. Resolve it before project-scoped edits, builds, tests or runs.",
            "toolsRoot": "Suite toolbelt root. Read/execute by default; change only for explicit toolchain maintenance.",
            "datasetRoot": "Reference/orientation data for agent work. Use for context; do not treat as project workspace.",
            "runtimeRoot": "Machine-local Suite state, logs and endpoint reports.",
        },
    }


def _agent_access(ctx: BridgeContext) -> Dict[str, Any]:
    write_enabled = bool(getattr(ctx, "write_enabled", False))
    sudo = bool(getattr(ctx, "sudo", False))
    level = "sudo_write" if sudo else ("read_write" if write_enabled else "read_only")
    return {
        "schema": "northstar.bridge.agent_access.v1",
        "level": level,
        "writeEnabled": write_enabled,
        "sudo": sudo,
        "writeBoundary": "selectedProjectRootWithinWorkspaceRoot",
        "policies": {
            "workspaceRoot": "Container of projects. Do not perform broad edits, builds or tests at workspaceRoot unless the task explicitly targets workspace-level infrastructure.",
            "activeProjectRoot": "Primary writable project area after project selection. Required for normal code edits, builds, tests and runs.",
            "projectSelection": "If the user request does not name a project and no trusted activeProjectRoot exists, ask which project to use.",
            "suiteRoot": "Suite source/control-plane area; change only with explicit operator intent.",
            "toolsRoot": "Read/execute by default; change only when the task is toolchain maintenance.",
            "datasetRoot": "Reference/orientation data; avoid changes unless the task updates the dataset or index.",
            "pathPolicy": "File mutations remain bounded by the bridge path policy.",
        },
    }


def _available_tool_context(tools: Dict[str, ToolSpec]) -> Dict[str, Any]:
    descriptors = public_tool_descriptors(tools)
    rows: list[Dict[str, Any]] = []
    for desc in descriptors:
        annotations = desc.get("annotations") if isinstance(desc.get("annotations"), dict) else {}
        meta = desc.get("_meta") if isinstance(desc.get("_meta"), dict) else {}
        rows.append({
            "name": desc.get("name"),
            "title": desc.get("title"),
            "riskTier": meta.get("northstar/riskTier"),
            "readOnly": annotations.get("readOnlyHint"),
            "destructive": annotations.get("destructiveHint"),
        })
    return {
        "schema": "northstar.bridge.available_tools.v1",
        "count": len(rows),
        "listMethod": "tools/list",
        "callMethod": "tools/call",
        "tools": rows,
    }


def _agent_context(ctx: BridgeContext, tools: Dict[str, ToolSpec] | None = None) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "schema": "northstar.bridge.agent_context.v1",
        "kind": "software_authoring_bridge",
        "purpose": "Bridge for inspecting, writing, validating and maintaining software projects through bounded Suite tools.",
        "workspace": _agent_workspace(ctx),
        "paths": _agent_paths(ctx),
        "access": _agent_access(ctx),
    }
    if tools is not None:
        context["availableTools"] = _available_tool_context(tools)
    return context


def _agent_instructions(ctx: BridgeContext, tools: Dict[str, ToolSpec]) -> str:
    paths = _agent_paths(ctx)
    access = _agent_access(ctx)
    available = _available_tool_context(tools)
    return (
        "NOESIS Suite Operator Bridge. This is a bounded bridge for writing and maintaining software. "
        f"suiteRoot={paths['suiteRoot']} is the installed Suite/control-plane root. "
        f"workspaceRoot={paths['workspaceRoot']} is a projects repository containing multiple projects, not a single project root. "
        "Before project-scoped work, resolve activeProjectRoot from the user's request, a trusted prior active project context, or ask which project to use. "
        f"toolsRoot={paths['toolsRoot']} contains Suite tools; prefer read/execute and change only when explicitly required. "
        f"datasetRoot={paths['datasetRoot']} contains reference/orientation data for agent work. "
        f"runtimeRoot={paths['runtimeRoot']} contains machine-local Suite state and logs. "
        f"Access level is {access['level']} (writeEnabled={access['writeEnabled']}, sudo={access['sudo']}). "
        "File mutations remain bounded by bridge path policy. "
        f"{available['count']} public MCP tools are available; use tools/list for descriptors and tools/call for execution."
    )

def rpc_result(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
def rpc_error(request_id: Any, code: int, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def server_info(ctx: BridgeContext | None = None) -> Dict[str, Any]:
    binding = getattr(ctx, "host_binding", None) if ctx is not None else None
    info: Dict[str, Any] = {
        "name": release_info.BRIDGE_SERVICE_NAME,
        "title": release_info.BRIDGE_PUBLIC_TITLE,
        "version": BRIDGE_VERSION,
        "description": release_info.BRIDGE_PUBLIC_DESCRIPTION,
        **release_info.public_meta(binding),
    }
    info["serverTitle"] = info["title"]
    info["displayTitle"] = info["title"]
    info["canonicalTitle"] = info["title"]
    if ctx is not None:
        agent_context = _agent_context(ctx)
        info["agentContext"] = agent_context
        info["workspace"] = agent_context["workspace"]
        info["paths"] = agent_context["paths"]
        info["access"] = agent_context["access"]
    return info

def discovery_payload(tools: Dict[str, ToolSpec], routes: McpRouteProfile = DEFAULT_MCP_ROUTES, ctx: BridgeContext | None = None) -> Dict[str, Any]:
    info = server_info(ctx)
    agent_context = _agent_context(ctx, tools) if ctx is not None else {"availableTools": _available_tool_context(tools)}
    return {
        "ok": True,
        "name": info["name"],
        "version": info["version"],
        "title": info["title"],
        "description": info["description"],
        "releaseName": info["releaseName"],
        "releaseNotes": info["releaseNotes"],
        "serverInfo": info,
        "agentContext": agent_context,
        "workspace": agent_context.get("workspace", {}),
        "paths": agent_context.get("paths", {}),
        "access": agent_context.get("access", {}),
        "availableTools": agent_context.get("availableTools", {}),
        "_meta": {
            "title": info["title"],
            "server/title": info["title"],
            "description": info["description"],
            "product": info["product"],
            "vendor": info["vendor"],
            "transport": info.get("transport"),
            "protocolFamily": info.get("protocolFamily"),
            "capabilitySummary": info.get("capabilitySummary"),
        },
        "tags": PUBLIC_APP_TAGS,
        "transport": release_info.BRIDGE_TRANSPORT,
        "endpoint": routes.endpoint,
        "http": {
            f"POST {routes.endpoint}": "JSON-RPC MCP messages",
            f"OPTIONS {routes.endpoint}": "transport preflight / allowed methods",
            f"HEAD {routes.endpoint}": "reachability probe / zero-byte metadata headers",
            f"GET {routes.endpoint}": "operator discovery; use POST for MCP clients",
        },
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
        },
        "methods": [
            "initialize",
            "notifications/initialized",
            "ping",
            "tools/list",
            "tools/call",
            "resources/list",
            "resources/templates/list",
            "prompts/list",
        ],
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
            summary["stdout"] = _stream_summary(payload, "stdout")
        if "stderr" in payload and payload.get("stderr"):
            summary["stderr"] = _stream_summary(payload, "stderr")
        if not summary:
            summary = {"keys": sorted(str(k) for k in payload.keys())[:40]}
        return summary
    if isinstance(payload, list):
        return {"list_count": len(payload), "first": payload[:3]}
    return payload
def _compact_stream_preview(text: str, *, max_bytes: int = PUBLIC_CONTENT_STREAM_PREVIEW_BYTES) -> str:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return text
    marker = f"...[northstar-public-content-preview-truncated-tail bytes={len(raw)}]\n"
    keep = max(1, max_bytes - len(marker.encode("utf-8", errors="replace")))
    return marker + raw[-keep:].decode("utf-8", errors="replace")


def _stream_summary(payload: dict[str, Any], name: str) -> dict[str, Any]:
    text = str(payload.get(name, "") or "")
    byte_count = int(payload.get(f"{name}_bytes", len(text.encode("utf-8", errors="replace"))) or 0)
    truncated = bool(payload.get(f"{name}_truncated", False))
    policy = payload.get("output_policy", {}) if isinstance(payload.get("output_policy"), dict) else {}
    mode = str(policy.get(name, "bounded"))
    return {
        "bytes": byte_count,
        "truncated": truncated,
        "mode": mode,
        "line_count": len(text.splitlines()),
        "preview": _format_console_text(_compact_stream_preview(text)),
    }
def _render_public_text(payload: Any, *, is_error: bool = False) -> str:
    title = "North Star Bridge Error" if is_error else "North Star Bridge Result"
    lines: list[str] = [title, "=" * len(title)]
    if isinstance(payload, dict):
        summary = _content_summary(payload)
        scalar_summary = {k: v for k, v in summary.items() if k not in {"stdout", "stderr"}}
        if scalar_summary:
            lines.extend(["", "Summary", "-------", _json_block(scalar_summary)])
        for stream_name in ("stdout", "stderr"):
            if stream_name not in summary:
                continue
            stream = summary[stream_name]
            if not isinstance(stream, dict):
                continue
            header = stream_name.upper()
            meta = (
                f"bytes={stream.get('bytes', 0)} "
                f"lines={stream.get('line_count', 0)} "
                f"mode={stream.get('mode', 'bounded')} "
                f"truncated={str(stream.get('truncated', False)).lower()}"
            )
            lines.extend([
                "",
                f"{header} ({meta})",
                "-" * (len(header) + len(meta) + 3),
                str(stream.get("preview", "")),
            ])
        if "stdout" not in summary and "stderr" not in summary:
            lines.extend(["", "Payload", "-------", _json_block(payload)])
        return "\n".join(lines).rstrip() + "\n"
    return "\n".join([*lines, "", _json_block(payload)]).rstrip() + "\n"
def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"
def _text_block(text: str) -> str:
    return "```text\n" + text.rstrip() + "\n```"
def _format_console_text(text: str) -> str:
    if not text:
        return "```text\n<empty>\n```"
    stripped = text.strip()
    parsed = _try_parse_json(stripped)
    if parsed is not None:
        return _json_block(parsed)
    return _text_block(_wrap_long_lines(text.rstrip()))
def _try_parse_json(text: str) -> Any | None:
    if not text:
        return None
    if text[0] not in "[{\"":
        return None
    try:
        return json.loads(text)
    except Exception:
        return None
def _wrap_long_lines(text: str, *, width: int = 180) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if len(line) <= width:
            out.append(line)
            continue
        current = line
        while len(current) > width:
            out.append(current[:width] + " ↩")
            current = "    " + current[width:]
        out.append(current)
    return "\n".join(out)
def _tool_result_payload(payload: Any) -> Dict[str, Any]:
    payload = _bounded_payload(payload)
    result: Dict[str, Any] = {
        "content": [{"type": "text", "text": _render_public_text(payload, is_error=False)}],
        "isError": False,
    }
    if isinstance(payload, dict):
        result["structuredContent"] = payload
    return result
def _tool_error_payload(error: Any) -> Dict[str, Any]:
    error = _bounded_payload(error)
    # MCP clients may validate structuredContent against the declared
    # outputSchema even for tool-execution errors. BridgeError payloads are
    # generic error envelopes, not success envelopes, so keep them in content
    # only and avoid breaking the message stream with schema-incompatible
    # structuredContent.
    return {
        "content": [{"type": "text", "text": _render_public_text(error, is_error=True)}],
        "isError": True,
    }
def _sanitize_public_arguments(public_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if public_name == "execute_suite_command":
        # Public execution is deliberately narrower than the internal
        # northstar.suite_command tool: no allow_unlisted, no arbitrary shell,
        # bounded timeout, and only the declared allow-list inside suite.py may run.
        command_id = str(arguments.get("command_id", "")).strip()
        sanitized: Dict[str, Any] = {"command_id": command_id, "allow_unlisted": False}
        try:
            raw_timeout = arguments.get("timeout_sec", DEFAULT_PUBLIC_SUITE_TIMEOUT_SEC)
            timeout_sec = int(raw_timeout or DEFAULT_PUBLIC_SUITE_TIMEOUT_SEC)
        except Exception:
            timeout_sec = DEFAULT_PUBLIC_SUITE_TIMEOUT_SEC
        sanitized["timeout_sec"] = max(1, min(timeout_sec, MAX_PUBLIC_SUITE_TIMEOUT_SEC))
        if "requires_openai_key" in arguments:
            sanitized["requires_openai_key"] = bool(arguments.get("requires_openai_key"))
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
            info = server_info(ctx)
            agent_context = _agent_context(ctx, tools)
            return rpc_result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": info,
                "title": info["title"],
                "agentContext": agent_context,
                "workspace": agent_context["workspace"],
                "paths": agent_context["paths"],
                "access": agent_context["access"],
                "availableTools": agent_context["availableTools"],
                "_meta": {
                    "title": info["title"],
                    "server/title": info["title"],
                    "description": info["description"],
                    "product": info["product"],
                    "vendor": info["vendor"],
                    "agentContext": agent_context,
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "instructions": _agent_instructions(ctx, tools),
            })
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return rpc_result(request_id, {})
        if method == "tools/list":
            return rpc_result(request_id, {"tools": public_tool_descriptors(tools)})
        if method == "resources/list":
            return rpc_result(request_id, {"resources": []})
        if method == "resources/templates/list":
            return rpc_result(request_id, {"resourceTemplates": []})
        if method == "prompts/list":
            return rpc_result(request_id, {"prompts": []})
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
