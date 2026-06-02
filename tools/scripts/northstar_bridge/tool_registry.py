from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .contracts import BridgeContext, BridgeError, MAX_EXEC_STDERR_BYTES, MAX_EXEC_STDOUT_BYTES, ToolSpec
from .paths import rel, safe_path, truncate_tail

_TOOL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_MAX_STDIN_BYTES = 128 * 1024
_DEFAULT_TIMEOUT_SEC = 120
_MAX_TIMEOUT_SEC = 0  # 0 means no descriptor-side timeout cap for long native tools

# These are not Suite commands. They are normal project tools discovered from
# PATH or from tools/**/tool.json and surfaced as MCP tools with one shared,
# bounded execution DTO. Add a binary to PATH or add tools/<name>/tool.json and
# it appears without writing a new Python handler or manual description row.
PATH_CANDIDATES: tuple[str, ...] = (
    "rg",
    "grep",
    "sed",
    "awk",
    "fd",
    "find",
    "git",
    "cargo",
    "python",
    "py",
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "mkdir",
    "cp",
    "mv",
    "rm",
)

READ_ONLY_COMMANDS: set[str] = {"rg", "grep", "awk", "fd", "ls", "cat", "head", "tail", "wc"}
READ_ONLY_GIT_SUBCOMMANDS: set[str] = {
    "status", "diff", "log", "show", "grep", "ls-files", "branch", "remote",
    "rev-parse", "describe", "tag", "config", "submodule", "stash", "blame",
}


@dataclass(frozen=True)
class ProjectTool:
    public_name: str
    command: list[str]
    source: str
    kind: str
    description: str
    default_cwd: str = "."
    descriptor_id: str = ""
    always_write: bool = False


def tool_input_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "args": {"type": "array", "items": {"type": "string"}, "description": "Arguments passed to the tool. No shell parsing is performed."},
            "cwd": {"type": "string", "description": "Repository-relative working directory. Defaults to project root."},
            "stdin": {"type": "string", "description": "Optional UTF-8 stdin, bounded by the bridge."},
            "timeout_sec": {"type": "integer", "minimum": 0, "description": "0 or omitted means no tool-side timeout."},
            "max_stdout_bytes": {"type": "integer", "minimum": 1024, "maximum": MAX_EXEC_STDOUT_BYTES},
            "max_stderr_bytes": {"type": "integer", "minimum": 1024, "maximum": MAX_EXEC_STDERR_BYTES},
            "release": {"type": "boolean", "description": "Descriptor tools only: run release target when supported."},
            "dry_run": {"type": "boolean", "description": "Recorded in output for destructive command planning; the tool itself only receives args you pass."},
        },
        "required": [],
        "additionalProperties": False,
    }


def tool_output_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["schema", "ok", "tool", "exit_code", "elapsed_ms", "stdout", "stderr", "truncated"],
        "properties": {
            "schema": {"const": "northstar.project_tool.run.v1"},
            "ok": {"type": "boolean"},
            "tool": {"type": "string"},
            "source": {"type": "string"},
            "kind": {"type": "string"},
            "cwd": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "command_preview": {"type": "array", "items": {"type": "string"}},
            "mutating": {"type": "boolean"},
            "write_enabled": {"type": "boolean"},
            "exit_code": {"type": "integer"},
            "elapsed_ms": {"type": "integer"},
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "stdout_bytes": {"type": "integer"},
            "stderr_bytes": {"type": "integer"},
            "truncated": {"type": "boolean"},
        },
        "additionalProperties": True,
    }


def registry_input_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "include_unavailable": {"type": "boolean"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        },
        "required": [],
        "additionalProperties": False,
    }


def _safe_public_name(raw: str, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", raw.strip()).strip("_")
    if not text or not text[0].isalpha():
        text = fallback
    text = text[:64]
    return text if _TOOL_NAME_RE.match(text) else fallback


def _which(command: str) -> Optional[list[str]]:
    if command == "python":
        # Prefer a normal python executable if it is on PATH; ctx.python_cmd is
        # inserted later as a guaranteed fallback.
        found = shutil.which("python")
        return [found] if found else None
    found = shutil.which(command)
    return [found] if found else None


def discover_project_tools(ctx: BridgeContext, *, include_unavailable: bool = False) -> list[ProjectTool]:
    tools: list[ProjectTool] = []
    seen: set[str] = set()

    for command in PATH_CANDIDATES:
        resolved = _which(command)
        if resolved is None and command == "python" and ctx.python_cmd:
            resolved = list(ctx.python_cmd)
        if resolved is None:
            if include_unavailable:
                tools.append(ProjectTool(command, [command], "missing-path", "external-cli", f"Unavailable project tool candidate `{command}`."))
            continue
        public = _safe_public_name(command, f"tool_{len(tools)}")
        if public in seen:
            continue
        seen.add(public)
        tools.append(ProjectTool(
            public_name=public,
            command=resolved,
            source="path" if command != "python" or resolved != ctx.python_cmd else "bridge-python",
            kind="external-cli",
            description=f"Run discovered project tool `{command}` inside the North Star repository. Arguments are passed directly without shell parsing; output is bounded.",
            always_write=command in {"cargo", "python", "py", "mkdir", "cp", "mv", "rm"},
        ))

    # Reuse existing first-party tools/**/tool.json descriptors. No extra bridge
    # handler is required per tool: descriptors become MCP tools automatically.
    try:
        from takesome.tools.descriptors import discover_tools as discover_descriptors
        descriptors, _warnings = discover_descriptors(ctx.root)
    except Exception:
        descriptors = []

    for descriptor in descriptors:
        public = _safe_public_name("tool_" + descriptor.id, f"tool_{len(tools)}")
        if public in seen:
            continue
        seen.add(public)
        tools.append(ProjectTool(
            public_name=public,
            command=["__takesome_tool_descriptor__", descriptor.id],
            source="tools-descriptor",
            kind=str(descriptor.kind),
            description=f"Run descriptor-discovered tool `{descriptor.id}`: {descriptor.description or descriptor.name}. Descriptor: {rel(ctx.root, descriptor.descriptor_path)}.",
            descriptor_id=descriptor.id,
            always_write=True,
        ))
    return tools


def _safe_cwd(ctx: BridgeContext, raw: str) -> Path:
    raw = str(raw or ".").strip()
    if raw in {"", "."}:
        return ctx.root.resolve()
    path = safe_path(ctx, raw, must_exist=True)
    if not path.is_dir():
        raise BridgeError("cwd must be a directory", "invalid_cwd", {"cwd": rel(ctx.root, path)})
    return path


def _has_any(args: Iterable[str], names: Iterable[str]) -> bool:
    lookup = set(names)
    return any(arg == name or arg.startswith(name + "=") for arg in args for name in lookup)


def _is_mutating(tool: ProjectTool, args: list[str]) -> bool:
    name = tool.public_name.lower()
    if tool.always_write:
        return True
    if name == "sed":
        return _has_any(args, ["-i", "--in-place"])
    if name == "find":
        return _has_any(args, ["-delete", "-exec", "-execdir", "-ok", "-okdir"])
    if name == "git":
        sub = ""
        for arg in args:
            if not arg.startswith("-"):
                sub = arg.lower()
                break
        return sub not in READ_ONLY_GIT_SUBCOMMANDS
    if name in READ_ONLY_COMMANDS:
        return False
    return True


def _tool_env(ctx: BridgeContext) -> Dict[str, str]:
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NORTHSTAR_PROJECT_TOOL": "1",
        "NORTHSTAR_REPO_ROOT": str(ctx.root),
    })
    if ctx.write_enabled:
        env["NORTHSTAR_AI_BRIDGE_WRITE"] = "1"
    return env


def _bounded_limits(args: Dict[str, Any]) -> tuple[int, int, int]:
    timeout_sec = max(0, int(args.get("timeout_sec", 0) or 0))
    max_out = max(1024, min(int(args.get("max_stdout_bytes", MAX_EXEC_STDOUT_BYTES)), MAX_EXEC_STDOUT_BYTES))
    max_err = max(1024, min(int(args.get("max_stderr_bytes", MAX_EXEC_STDERR_BYTES)), MAX_EXEC_STDERR_BYTES))
    return timeout_sec, max_out, max_err


def _run_process(ctx: BridgeContext, tool: ProjectTool, command: list[str], tool_args: list[str], args: Dict[str, Any], *, mutating: bool) -> Dict[str, Any]:
    cwd = _safe_cwd(ctx, str(args.get("cwd", tool.default_cwd)))
    timeout_sec, max_out, max_err = _bounded_limits(args)
    stdin = str(args.get("stdin", ""))
    if len(stdin.encode("utf-8", errors="replace")) > _MAX_STDIN_BYTES:
        raise BridgeError("stdin is too large for project tool call", "stdin_too_large", {"max_bytes": _MAX_STDIN_BYTES})
    started = time.time()
    try:
        proc = subprocess.run(
            [*command, *tool_args],
            cwd=str(cwd),
            input=stdin if stdin else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=None,
            shell=False,
            env=_tool_env(ctx),
        )
    except subprocess.TimeoutExpired as exc:
        stdout, ot, stdout_bytes = truncate_tail(exc.stdout if isinstance(exc.stdout, str) else "", max_out)
        stderr, et, stderr_bytes = truncate_tail(exc.stderr if isinstance(exc.stderr, str) else "", max_err)
        raise BridgeError("project tool wait was interrupted", "tool_wait_interrupted", {
            "tool": tool.public_name,
            "timeout_sec": timeout_sec,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "truncated": ot or et,
        })

    stdout, ot, stdout_bytes = truncate_tail(proc.stdout, max_out)
    stderr, et, stderr_bytes = truncate_tail(proc.stderr, max_err)
    return {
        "schema": "northstar.project_tool.run.v1",
        "ok": proc.returncode == 0,
        "wait_policy": "wait_until_completion",
        "requested_timeout_sec": timeout_sec,
        "tool": tool.public_name,
        "source": tool.source,
        "kind": tool.kind,
        "cwd": rel(ctx.root, cwd),
        "args": tool_args,
        "command_preview": [Path(command[0]).name, *tool_args] if command else list(tool_args),
        "mutating": mutating,
        "write_enabled": ctx.write_enabled,
        "dry_run": bool(args.get("dry_run", False)),
        "exit_code": proc.returncode,
        "elapsed_ms": int((time.time() - started) * 1000),
        "stdout": stdout,
        "stdout_tail": stdout,
        "stdout_bytes": stdout_bytes,
        "stderr": stderr,
        "stderr_tail": stderr,
        "stderr_bytes": stderr_bytes,
        "truncated": ot or et,
        "output_policy": {"stdout": "tail", "stderr": "tail", "max_stdout_bytes": max_out, "max_stderr_bytes": max_err},
    }


def _run_descriptor_tool(ctx: BridgeContext, tool: ProjectTool, args: Dict[str, Any], tool_args: list[str], *, mutating: bool) -> Dict[str, Any]:
    if not ctx.takesome_py.exists():
        raise BridgeError("tools/scripts/takesome.py is missing", "takesome_missing")
    command = [*ctx.python_cmd, str(ctx.takesome_py), "tools", "run", tool.descriptor_id]
    if bool(args.get("release", False)):
        command.append("--release")
    if tool_args:
        command.append("--")
        command.extend(tool_args)
    return _run_process(ctx, tool, command, [], args, mutating=mutating)


def run_project_tool(ctx: BridgeContext, tool: ProjectTool, args: Dict[str, Any]) -> Dict[str, Any]:
    tool_args = [str(x) for x in (args.get("args") or [])]
    mutating = _is_mutating(tool, tool_args)
    if mutating and not ctx.write_enabled:
        raise BridgeError("project tool rejected because NORTHSTAR_AI_BRIDGE_WRITE is not enabled", "write_disabled", {"tool": tool.public_name})
    if tool.descriptor_id:
        return _run_descriptor_tool(ctx, tool, args, tool_args, mutating=mutating)
    return _run_process(ctx, tool, tool.command, tool_args, args, mutating=mutating)


def project_tool_registry(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 200)), 500))
    include_unavailable = bool(args.get("include_unavailable", False))
    tools = discover_project_tools(ctx, include_unavailable=include_unavailable)[:limit]
    return {
        "schema": "northstar.project_tool.registry.v1",
        "ok": True,
        "root": str(ctx.root),
        "write_enabled": ctx.write_enabled,
        "count": len(tools),
        "tools": [
            {
                "name": tool.public_name,
                "source": tool.source,
                "kind": tool.kind,
                "descriptor_id": tool.descriptor_id or None,
                "command": [Path(part).name if i == 0 else part for i, part in enumerate(tool.command)],
                "always_write": tool.always_write,
                "description": tool.description,
            }
            for tool in tools
        ],
        "truncated": len(discover_project_tools(ctx, include_unavailable=include_unavailable)) > limit,
    }


def build_project_tool_specs(ctx: BridgeContext) -> Dict[str, ToolSpec]:
    specs: Dict[str, ToolSpec] = {
        "tool_registry": ToolSpec(
            "tool_registry",
            "List project tools auto-discovered from PATH and tools/**/tool.json. This registry generates MCP tool descriptors without per-command bridge handlers.",
            registry_input_schema(),
            lambda args: project_tool_registry(ctx, args),
            {"type": "object", "additionalProperties": True},
        )
    }
    input_schema = tool_input_schema()
    output_schema = tool_output_schema()
    for tool in discover_project_tools(ctx):
        specs[tool.public_name] = ToolSpec(
            tool.public_name,
            tool.description,
            input_schema,
            lambda args, tool=tool: run_project_tool(ctx, tool, args),
            output_schema,
        )
    return specs
