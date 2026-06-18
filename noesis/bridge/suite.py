from __future__ import annotations

import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from .auth import openai_env
from .contracts import BridgeContext, BridgeError, MAX_EXEC_STDERR_BYTES, MAX_EXEC_STDOUT_BYTES
from .paths import slug, truncate_tail
from .memory import knowledge_update, task_record, task_update


def _suite_json_action(action_id: str) -> List[str]:
    return ["--run", action_id, "--json"]


def _suite_json_list_actions() -> List[str]:
    return ["--list-actions", "--json"]


READ_ONLY_COMMANDS = {
    "suite.list_actions": _suite_json_list_actions(),
    "build.status": _suite_json_action("build.status"),
    "tools.doctor": _suite_json_action("tools.doctor"),
    "tools.doctor.full": _suite_json_action("tools.doctor.full"),
    "diag.invariants": _suite_json_action("diag.invariants"),
    "diag.conformance": _suite_json_action("diag.conformance"),
    "diag.schema": _suite_json_action("diag.schema"),
    "diag.schema.runtime": _suite_json_action("diag.schema.runtime"),
    "diag.editor.shell": _suite_json_action("diag.editor.shell"),
    "diag.import.pipeline": _suite_json_action("diag.import.pipeline"),
    "diag.world.scene": _suite_json_action("diag.world.scene"),
    "diag.gameplay": _suite_json_action("diag.gameplay"),
    "diag.rendering": _suite_json_action("diag.rendering"),
    "diag.reference.completeness": _suite_json_action("diag.reference.completeness"),
    "diag.reference.completeness.strict": ["tools", "reference-completeness-strict"],
    "patch.verify": _suite_json_action("patch.verify"),
    "import.ui.assets.check": _suite_json_action("import.ui.assets.check"),
}


WRITE_COMMANDS = {
    "build.center": _suite_json_action("build.center"),
    "build.plugins": _suite_json_action("build.plugins"),
    "build.plugins.dev": _suite_json_action("build.plugins.dev"),
    "build.plugins.release": _suite_json_action("build.plugins.release"),
    "build.plugins.force.dev": _suite_json_action("build.plugins.force.dev"),
    "build.codecs": _suite_json_action("build.codecs"),
    "build.importers": _suite_json_action("build.importers"),
    "runtime.run": _suite_json_action("runtime.run"),
    "source.pack": _suite_json_action("source.pack"),
    "cache.clear": _suite_json_action("cache.clear"),
    "workspace.sync": _suite_json_action("workspace.sync"),
    "workspace.clean": _suite_json_action("workspace.clean"),
    "workspace.clean.full": _suite_json_action("workspace.clean.full"),
    "patch.apply": _suite_json_action("patch.apply"),
    "tools.collect": _suite_json_action("tools.collect"),
    "import.ui.assets": _suite_json_action("import.ui.assets"),
    "diag.operator.memory": _suite_json_action("diag.operator.memory"),
    "tools.operator.memory": ["tools", "operator-memory"],
    "tools.build.safe": _suite_json_action("tools.build.safe"),
    "tools.build.safe.validate": _suite_json_action("tools.build.safe.validate"),
    "tools.validate.build": _suite_json_action("tools.validate.build"),
    "diag.dataset.lifecycle": _suite_json_action("diag.dataset.lifecycle"),
    "diag.dataset.maturity": _suite_json_action("diag.dataset.maturity"),
    "diag.dataset.maturity.strict": _suite_json_action("diag.dataset.maturity.strict"),
    "diag.dataset.entry_value": _suite_json_action("diag.dataset.entry_value"),
}


def _automation_env(ctx: BridgeContext, env_overrides: Optional[Dict[str, str]]) -> Dict[str, str]:
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NORTHSTAR_SUITE_STDIO_ENCODING": "utf-8",
        "NORTHSTAR_SUITE_STDIO_ERRORS": "replace",
        "NEWENGINE_PARENT_SCRIPT": "1",
        "NEWENGINE_NO_PAUSE": "1",
        "NEWENGINE_PLUGIN_TARGET": env.get("NEWENGINE_PLUGIN_TARGET", "all"),
        "NORTHSTAR_WORKSPACE_ROOT": str(ctx.root),
        "NORTHSTAR_SUITE_WORKSPACE_ROOT": str(ctx.root),
        "TAKESOME_WORKSPACE_ROOT": str(ctx.root),
        "NORTHSTAR_TOOL_ROOT": str(ctx.operator_root),
        "NORTHSTAR_SUITE_TOOL_ROOT": str(ctx.operator_root),
        "TAKESOME_TOOL_ROOT": str(ctx.operator_root),
        "NEWENGINE_PROJECT_ROOT": str(ctx.root),
        "NEWENGINE_REPO_ROOT": str(ctx.operator_root),
    })
    if ctx.write_enabled:
        env["NORTHSTAR_AI_BRIDGE_WRITE"] = "1"
    if env_overrides:
        env.update(env_overrides)
    return env


def _with_sudo(ctx: BridgeContext, args: List[str]) -> List[str]:
    # Sudo/write policy is config-driven; do not inject legacy -sudo flags.
    return list(args)


def _suite_command_base(ctx: BridgeContext) -> List[str]:
    return [*ctx.python_cmd, *ctx.suite_module_args]


def _normalize_suite_args(ctx: BridgeContext, args: List[str]) -> List[str]:
    resolved = list(args)
    # Bridge compatibility: ctx.suite_module_args already targets `python -m noesis suite`.
    # Some callers historically passed an additional leading `suite`, producing
    # `python -m noesis suite suite ...`. Drop only that duplicate prefix.
    if resolved[:1] == ["suite"] and ctx.suite_module_args[-1:] == ["suite"]:
        return resolved[1:]
    return resolved


def run_takesome(ctx: BridgeContext, args: List[str], timeout_sec: int = 120, env_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    resolved_args = _normalize_suite_args(ctx, _with_sudo(ctx, args))
    env = _automation_env(ctx, env_overrides)
    if ctx.sudo:
        env["NORTHSTAR_SUITE_SUDO"] = "1"
        env.setdefault("NORTHSTAR_SUITE_SUDO_REASON", "bridge")

    started = time.time()
    try:
        proc = subprocess.run(
            [*_suite_command_base(ctx), *resolved_args],
            cwd=str(ctx.operator_root),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=None,
            shell=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        out, ot, out_bytes = truncate_tail(exc.stdout if isinstance(exc.stdout, str) else "", MAX_EXEC_STDOUT_BYTES)
        err, et, err_bytes = truncate_tail(exc.stderr if isinstance(exc.stderr, str) else "", MAX_EXEC_STDERR_BYTES)
        raise BridgeError("Suite command wait was interrupted", "command_wait_interrupted", {"args": resolved_args, "requested_timeout_sec": timeout_sec, "stdout": out, "stdout_tail": out, "stdout_bytes": out_bytes, "stderr": err, "stderr_tail": err, "stderr_bytes": err_bytes, "truncated": ot or et, "wait_policy": "wait_until_completion"})

    out, ot, out_bytes = truncate_tail(proc.stdout, MAX_EXEC_STDOUT_BYTES)
    err, et, err_bytes = truncate_tail(proc.stderr, MAX_EXEC_STDERR_BYTES)
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "elapsed_ms": int((time.time() - started) * 1000),
        "args": resolved_args,
        "stdout": out,
        "stdout_tail": out,
        "stdout_bytes": out_bytes,
        "stderr": err,
        "stderr_tail": err,
        "stderr_bytes": err_bytes,
        "truncated": ot or et,
        "wait_policy": "wait_until_completion",
        "requested_timeout_sec": timeout_sec,
        "output_policy": {
            "stdout": "tail",
            "stderr": "tail",
            "max_stdout_bytes": MAX_EXEC_STDOUT_BYTES,
            "max_stderr_bytes": MAX_EXEC_STDERR_BYTES,
        },
    }


def _record_suite_command_memory(ctx: BridgeContext, command_id: str, result: Dict[str, Any], *, write_command: bool) -> None:
    if not ctx.write_enabled:
        return
    try:
        task_id = f"suite-command-{slug(command_id, 'suite')}-{int(time.time())}"
        task_record(ctx, {
            "task_id": task_id,
            "title": f"Suite command: {command_id}",
            "task": f"Run Suite command {command_id}",
            "intent": "Record Suite command execution and update current North Star operator knowledge.",
            "source": "northstar.suite_command",
            "status": "completed" if result.get("ok") else "failed",
            "phase": command_id,
            "tags": ["suite", "command", "write" if write_command else "read"],
            "state_snapshot": {"command_id": command_id, "exit_code": result.get("exit_code"), "elapsed_ms": result.get("elapsed_ms")},
            "summary": f"Suite command {command_id} returned ok={bool(result.get('ok'))} exit_code={result.get('exit_code')}",
        })
        task_update(ctx, {
            "task_id": task_id,
            "status": "completed" if result.get("ok") else "failed",
            "phase": "suite.result",
            "event_type": "suite.command.result",
            "summary": f"Suite command {command_id} finished",
            "state_delta": {"command_id": command_id, "result": {k: result.get(k) for k in ("ok", "exit_code", "elapsed_ms", "truncated")}},
            "diagnostics": [] if result.get("ok") else [{"command_id": command_id, "stderr": str(result.get("stderr", ""))[:2000], "stdout": str(result.get("stdout", ""))[:2000]}],
        })
        knowledge_update(ctx, {
            "type": "suite_command_result",
            "subject": f"Suite command result: {command_id}",
            "summary": f"{command_id}: ok={bool(result.get('ok'))}, exit_code={result.get('exit_code')}, elapsed_ms={result.get('elapsed_ms')}",
            "task_id": task_id,
            "tags": ["suite", "engine-state", "command"],
            "evidence": {"command_id": command_id, "result_keys": sorted(str(k) for k in result.keys())},
        })
    except Exception:
        return


def suite_command(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    import re

    command_id = str(args.get("command_id", "")).strip()
    if not re.match(r"^[A-Za-z0-9_.:-]+$", command_id):
        raise BridgeError("invalid Suite command id", "invalid_command", {"command_id": command_id})

    raw_timeout = args.get("timeout_sec", 0)
    try:
        timeout_sec = int(raw_timeout or 0)
    except Exception:
        timeout_sec = 0
    if timeout_sec < 0:
        timeout_sec = 0

    env = openai_env(ctx, bool(args.get("requires_openai_key", False)))

    if command_id in READ_ONLY_COMMANDS:
        result = run_takesome(ctx, READ_ONLY_COMMANDS[command_id], timeout_sec, env)
        _record_suite_command_memory(ctx, command_id, result, write_command=False)
        return result

    if command_id in WRITE_COMMANDS:
        if not ctx.write_enabled:
            raise BridgeError("write command rejected because NORTHSTAR_AI_BRIDGE_WRITE is not enabled", "write_disabled", {"command_id": command_id})
        result = run_takesome(ctx, WRITE_COMMANDS[command_id], timeout_sec, env)
        _record_suite_command_memory(ctx, command_id, result, write_command=True)
        return result

    if (bool(args.get("allow_unlisted", False)) or ctx.sudo) and ctx.write_enabled:
        result = run_takesome(ctx, ["suite", "--run", command_id, "--json"], timeout_sec, env)
        _record_suite_command_memory(ctx, command_id, result, write_command=True)
        return result

    raise BridgeError("unknown Suite bridge command id", "unknown_command", {"command_id": command_id, "allowed": sorted([*READ_ONLY_COMMANDS, *WRITE_COMMANDS])})
