from __future__ import annotations

import os
from typing import Any, Dict

from .contracts import ToolSpec

PUBLIC_APP_TITLE = "North Star Suite"
PUBLIC_APP_DESCRIPTION = (
    "North Star Engine operator and workspace bridge for diagnostics, safe project inspection, "
    "Suite commands, dataset search, and controlled text-file maintenance."
)
PUBLIC_APP_TAGS = ["northstar", "suite", "game-engine", "developer-tools"]

PUBLIC_TOOL_TITLES: Dict[str, str] = {
    "get_status": "Get bridge status",
    "get_operator_snapshot": "Get operator snapshot",
    "read_text_file": "Read project text file",
    "search_project_text": "Search project text",
    "list_project_tree": "List project tree",
    "list_recent_logs": "List recent logs",
    "get_dataset_status": "Get dataset status",
    "search_dataset": "Search dataset",
    "list_suite_actions": "List Suite actions",
    "execute_suite_command": "Execute Suite command",
    "write_text_file": "Write text file",
    "delete_path": "Delete project path",
    "bridge_origin_status": "Check bridge origin",
    "reload_bridge_origin": "Reload bridge origin",
    "restart_bridge_origin": "Restart bridge origin",
}

PUBLIC_TOOL_MAP: Dict[str, str] = {
    "get_status": "northstar.status",
    "get_operator_snapshot": "northstar.operator_snapshot",
    "read_text_file": "northstar.read_text",
    "search_project_text": "northstar.search_text",
    "list_project_tree": "northstar.list_tree",
    "list_recent_logs": "northstar.list_logs",
    "get_dataset_status": "northstar.dataset_status",
    "search_dataset": "northstar.dataset_search_directories",
    "list_suite_actions": "northstar.suite_actions",
    # These three are part of the permanent public operator surface. They must
    # stay listed even when write mode is disabled; execution then returns a
    # write_disabled error instead of hiding capabilities from the client.
    "execute_suite_command": "northstar.suite_command",
    "write_text_file": "northstar.write_text",
    "delete_path": "northstar.delete_path",
    "bridge_origin_status": "northstar.bridge_restart",
    "reload_bridge_origin": "northstar.bridge_reload_origin",
    "restart_bridge_origin": "northstar.bridge_reload_origin",
    "repo_status": "northstar.repo_status",
    "repo_diff": "northstar.repo_diff",
    "repo_changed_files": "northstar.repo_changed_files",
    "repo_patch_preview": "northstar.repo_patch_preview",
    "repo_patch_apply": "northstar.repo_patch_apply",
    "validate_python_changed": "northstar.validate_python_changed",
    "bridge_inspect_tool_descriptors": "northstar.bridge_inspect_tool_descriptors",
    "repo_search_text": "northstar.repo_search_text",
    "archive_changed_files_zip": "northstar.archive_changed_files_zip",
    "archive_full_zip": "northstar.archive_full_zip",
    "archive_patch": "northstar.archive_patch",
    "terminal_simulate_resize": "northstar.terminal_simulate_resize",
    "python_symbols": "northstar.python_symbols",
    "python_import_graph": "northstar.python_import_graph",
    "python_call_graph": "northstar.python_call_graph",
    "repo_split_python_module": "northstar.repo_split_python_module",
    "validate_no_legacy": "northstar.validate_no_legacy",
    "validate_import_cycles": "northstar.validate_import_cycles",
    "validate_line_count": "northstar.validate_line_count",
}


PUBLIC_INPUT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "list_suite_actions": {
        "type": "object",
        "properties": {
            "timeout_sec": {"type": "integer", "minimum": 5, "maximum": 300}
        },
        "required": [],
        "additionalProperties": False,
    },
    "bridge_origin_status": {"type": "object", "properties": {"ok": {"type": "boolean"}, "command": {"type": "string"}, "exit_code": {"type": "integer"}, "stdout": {"type": "string"}, "stderr": {"type": "string"}, "truncated": {"type": "boolean"}}, "additionalProperties": True},
    "reload_bridge_origin": {"type": "object", "properties": {"schema": {"const": "northstar.bridge.reload_origin.v1"}, "ok": {"type": "boolean"}, "scheduled": {"type": "boolean"}, "pid": {"type": "integer"}, "host": {"type": "string"}, "port": {"type": "integer"}, "report_path": {"type": "string"}}, "additionalProperties": True},
    "restart_bridge_origin": {"type": "object", "properties": {"schema": {"const": "northstar.bridge.reload_origin.v1"}, "ok": {"type": "boolean"}, "scheduled": {"type": "boolean"}, "pid": {"type": "integer"}, "host": {"type": "string"}, "port": {"type": "integer"}, "report_path": {"type": "string"}}, "additionalProperties": True},
    "execute_suite_command": {
        "type": "object",
        "properties": {
            "command_id": {
                "type": "string",
                "description": "Allow-listed Suite command id, for example diag.operator.memory or tools.operator.memory.",
                "pattern": "^[A-Za-z0-9_.:-]+$"
            },
            "timeout_sec": {"type": "integer", "minimum": 0, "description": "0 or omitted means no Suite-side timeout for long operations."},
            "requires_openai_key": {"type": "boolean"},
            "allow_unlisted": {"type": "boolean", "description": "When write mode is enabled, run any SuiteRegistry action id through suite --run. This is still not arbitrary shell."}
        },
        "required": ["command_id"],
        "additionalProperties": False,
    },
    "write_text_file": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository-relative project path."},
            "content": {"type": "string"},
            "create_parents": {"type": "boolean"}
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    },
    "delete_path": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repository-relative project path."},
            "recursive": {"type": "boolean"},
            "dry_run": {"type": "boolean"}
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    "bridge_origin_status": {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Local bridge origin host. Defaults to 127.0.0.1."},
            "port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "timeout": {"type": "number", "minimum": 0.1, "maximum": 10},
            "wait_sec": {"type": "number", "minimum": 1, "maximum": 120},
            "dry_run": {"type": "boolean"}
        },
        "required": [],
        "additionalProperties": False,
    },
    "reload_bridge_origin": {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Local bridge origin host. Defaults to 127.0.0.1."},
            "port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "timeout": {"type": "number", "minimum": 0.1, "maximum": 10},
            "wait_sec": {"type": "number", "minimum": 1, "maximum": 120},
            "delay_sec": {"type": "number", "minimum": 0.5, "maximum": 15},
            "dry_run": {"type": "boolean"}
        },
        "required": [],
        "additionalProperties": False,
    },
    "restart_bridge_origin": {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Local bridge origin host. Defaults to 127.0.0.1."},
            "port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "timeout": {"type": "number", "minimum": 0.1, "maximum": 10},
            "wait_sec": {"type": "number", "minimum": 1, "maximum": 120},
            "delay_sec": {"type": "number", "minimum": 0.5, "maximum": 15},
            "dry_run": {"type": "boolean"}
        },
        "required": [],
        "additionalProperties": False,
    },
}

PUBLIC_OUTPUT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "get_status": {"type": "object", "properties": {"bridge": {"type": "object"}, "workspace": {"type": "object"}, "dataset": {"type": "object"}}, "additionalProperties": True},
    "get_operator_snapshot": {"type": "object", "properties": {"status": {"type": "object"}, "logs": {"type": "object"}, "dataset": {"type": "object"}}, "additionalProperties": True},
    "read_text_file": {"type": "object", "properties": {"kind": {"type": "string"}, "path": {"type": "string"}, "truncated": {"type": "boolean"}, "content": {"type": "string"}, "entries": {"type": "array"}}, "additionalProperties": True},
    "search_project_text": {"type": "object", "properties": {"query": {"type": "string"}, "hits": {"type": "array"}, "truncated": {"type": "boolean"}}, "additionalProperties": True},
    "list_project_tree": {"type": "object", "properties": {"path": {"type": "string"}, "items": {"type": "array"}, "truncated": {"type": "boolean"}}, "additionalProperties": True},
    "list_recent_logs": {"type": "object", "properties": {"logs": {"type": "array"}}, "required": ["logs"], "additionalProperties": True},
    "get_dataset_status": {"type": "object", "properties": {"dataSetDirectory": {"type": "string"}, "preferredMode": {"type": "string"}, "zipFallback": {"type": "boolean"}, "archive_count": {"type": "integer"}, "extracted_count": {"type": "integer"}}, "additionalProperties": True},
    "search_dataset": {"type": "object", "properties": {"query": {"type": "string"}, "base": {"type": "string"}, "hits": {"type": "array"}, "truncated": {"type": "boolean"}}, "additionalProperties": True},
    "list_suite_actions": {"type": "object", "properties": {"ok": {"type": "boolean"}, "exit_code": {"type": "integer"}, "elapsed_ms": {"type": "integer"}, "stdout": {"type": "string"}, "stderr": {"type": "string"}, "truncated": {"type": "boolean"}}, "additionalProperties": True},
    "write_text_file": {"type": "object", "properties": {"ok": {"type": "boolean"}, "path": {"type": "string"}, "bytes_written": {"type": "integer"}, "backup": {"type": ["string", "null"]}}, "additionalProperties": True},
    "delete_path": {"type": "object", "properties": {"ok": {"type": "boolean"}, "deleted": {"type": "boolean"}, "path": {"type": "string"}, "kind": {"type": "string"}, "backup": {"type": ["string", "null"]}}, "additionalProperties": True},
    "bridge_origin_status": {"type": "object", "properties": {"ok": {"type": "boolean"}, "command": {"type": "string"}, "exit_code": {"type": "integer"}, "stdout": {"type": "string"}, "stderr": {"type": "string"}, "truncated": {"type": "boolean"}}, "additionalProperties": True},
    "reload_bridge_origin": {"type": "object", "properties": {"schema": {"const": "northstar.bridge.reload_origin.v1"}, "ok": {"type": "boolean"}, "scheduled": {"type": "boolean"}, "pid": {"type": "integer"}, "host": {"type": "string"}, "port": {"type": "integer"}, "report_path": {"type": "string"}}, "additionalProperties": True},
    "restart_bridge_origin": {"type": "object", "properties": {"schema": {"const": "northstar.bridge.reload_origin.v1"}, "ok": {"type": "boolean"}, "scheduled": {"type": "boolean"}, "pid": {"type": "integer"}, "host": {"type": "string"}, "port": {"type": "integer"}, "report_path": {"type": "string"}}, "additionalProperties": True},
    "execute_suite_command": {
        "type": "object",
        "required": ["schema", "ok", "command_id", "exit_code", "elapsed_ms", "stdout", "stderr", "truncated", "allowed_surface"],
        "properties": {
            "schema": {"const": "northstar.suite.execute_command.v1"},
            "ok": {"type": "boolean"},
            "command_id": {"type": "string"},
            "exit_code": {"type": "integer"},
            "elapsed_ms": {"type": "integer"},
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "truncated": {"type": "boolean"},
            "allowed_surface": {"enum": ["read_only", "write_allowlist", "unknown"]}
        },
        "additionalProperties": True,
    },
}


def _public_schema(tool: ToolSpec, public_name: str = "") -> Dict[str, Any]:
    if public_name in PUBLIC_INPUT_SCHEMAS:
        return dict(PUBLIC_INPUT_SCHEMAS[public_name])
    schema = dict(tool.input_schema or {"type": "object", "properties": {}, "required": []})
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    schema.setdefault("required", [])
    schema.setdefault("additionalProperties", False)
    return schema


def _public_description(public_name: str, internal: ToolSpec) -> str:
    descriptions = {
        "get_status": "Return North Star bridge, Suite and repository status without mutating the workspace.",
        "get_operator_snapshot": "Return a read-only operator snapshot with status, recent logs and dataset overview.",
        "read_text_file": "Read a whitelisted repository text file or list a whitelisted directory.",
        "search_project_text": "Search whitelisted North Star project text roots.",
        "list_project_tree": "List a shallow repository tree for whitelisted roots.",
        "list_recent_logs": "List recent build, run and incident logs.",
        "get_dataset_status": "Return dataSetDirectory status and newest archives/directories.",
        "search_dataset": "Search materialized dataset directories first.",
        "list_suite_actions": "List SuiteRegistry actions available through the bridge. Use this before execute_suite_command when unsure which command id is allowed.",
        "execute_suite_command": "Execute one Suite command through a bounded, schema-described bridge result. Allow-listed commands always work; with write mode, allow_unlisted=true may run any SuiteRegistry action id. This is still not arbitrary shell.",
        "write_text_file": "Write a repository-relative project text file with backup. Always listed; execution requires write mode.",
        "delete_path": "Delete a repository-relative project file or directory. Always listed; execution requires write mode; directories require recursive=true.",
        "bridge_origin_status": "Check the local North Star AI bridge HTTP origin without mutating it. Uses the safe restart helper status command.",
        "reload_bridge_origin": "Schedule a safe detached reload of the local bridge HTTP origin. Requires write mode; never stops cloudflared/tunnel processes.",
        "restart_bridge_origin": "Alias for reload_bridge_origin: schedule a safe detached local-origin reload so the agent can reconnect after restart.",
    }
    return descriptions.get(public_name, internal.description)


def _public_title(public_name: str) -> str:
    if public_name in PUBLIC_TOOL_TITLES:
        return PUBLIC_TOOL_TITLES[public_name]
    words = public_name.replace("tool_", "").replace("_", " ").replace("-", " ").strip()
    return words[:1].upper() + words[1:] if words else public_name


def _tool_security() -> list[Dict[str, Any]]:
    return [{"type": "noauth"}]


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on", "force", "sudo"}


def _suite_assume_yes_active() -> bool:
    return _truthy_env("NORTHSTAR_SUITE_YES")


def _suite_sudo_active() -> bool:
    return _suite_assume_yes_active() or _truthy_env("NORTHSTAR_SUITE_SUDO") or _truthy_env("NORTHSTAR_BRIDGE_SUDO")


def _tool_risk_tier(public_name: str = "") -> str:
    read_only_project_tools = {"tool_registry", "grep", "rg", "awk", "fd", "find", "ls", "cat", "head", "tail", "wc"}
    if public_name in {"delete_path", "rm", "reload_bridge_origin", "restart_bridge_origin"}:
        return "sudo_write" if _suite_assume_yes_active() else "dangerous"
    if public_name in {"execute_suite_command", "write_text_file"}:
        return "sudo_write" if _suite_assume_yes_active() else "write"
    if public_name and public_name not in PUBLIC_TOOL_MAP:
        if public_name in read_only_project_tools:
            return "read_only"
        return "sudo_write" if _suite_assume_yes_active() else "write"
    return "read_only"


def _tool_annotations(public_name: str = "") -> Dict[str, Any]:
    tier = _tool_risk_tier(public_name)
    read_only = tier == "read_only"

    # serverBridge --yes sets NORTHSTAR_SUITE_YES=1.  In that mode the local
    # operator has explicitly armed sudo/write bridge work, so the public MCP
    # surface must downgrade dangerous tools to sudo_write instead of advertising
    # them as destructive.  The actual write gate still remains ctx.write_enabled.
    return {
        "readOnlyHint": read_only,
        "destructiveHint": tier == "dangerous",
        "openWorldHint": False,
        "idempotentHint": read_only,
    }


def tool_descriptor(tool: ToolSpec) -> Dict[str, Any]:
    """Internal/operator descriptor used by /tools.

    MCP-facing clients receive public_tool_descriptors() instead.  Keeping this
    raw descriptor preserves the local operator bridge while the public MCP
    surface stays safe and ChatGPT-friendly.
    """
    descriptor = {"name": tool.name, "title": _public_title(tool.name), "description": tool.description, "inputSchema": tool.input_schema}
    if tool.output_schema:
        descriptor["outputSchema"] = tool.output_schema
    return descriptor


def _public_descriptor(public_name: str, internal: ToolSpec) -> Dict[str, Any]:
    security = _tool_security()
    return {
        "name": public_name,
        "title": _public_title(public_name),
        "description": _public_description(public_name, internal),
        "inputSchema": _public_schema(internal, public_name),
        "outputSchema": PUBLIC_OUTPUT_SCHEMAS.get(public_name, internal.output_schema or {"type": "object", "additionalProperties": True}),
        "securitySchemes": security,
        "annotations": _tool_annotations(public_name),
        "_meta": {
            "securitySchemes": security,
            "openai/toolInvocation/invoking": f"Running {public_name}",
            "openai/toolInvocation/invoked": f"Finished {public_name}",
            "northstar/tags": PUBLIC_APP_TAGS,
            "northstar/assumeYes": _suite_assume_yes_active(),
            "northstar/riskTier": _tool_risk_tier(public_name),
        },
    }


def _is_dynamic_project_tool(name: str) -> bool:
    # Internal northstar.* tools are intentionally hidden behind the curated
    # public map. Auto-discovered project tools use plain names like grep/sed
    # or tool_<descriptor_id>, so they can be surfaced directly without adding
    # a new manual map row and description every time.
    return bool(name) and not name.startswith("northstar.")


def public_tool_descriptors(tools: Dict[str, ToolSpec]) -> list[Dict[str, Any]]:
    descriptors: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for public_name, internal_name in PUBLIC_TOOL_MAP.items():
        internal = tools.get(internal_name)
        if internal is None:
            continue
        descriptors.append(_public_descriptor(public_name, internal))
        seen.add(public_name)

    for internal_name, internal in sorted(tools.items(), key=lambda item: item[0].lower()):
        if internal_name in seen or not _is_dynamic_project_tool(internal_name):
            continue
        descriptors.append(_public_descriptor(internal_name, internal))
        seen.add(internal_name)
    return descriptors
