from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from . import bridge_restart, dataset, repo, status as bridge_status
from .contracts import BridgeContext, BridgeError, now_utc
from .memory import cache_set, knowledge_update, note_append, note_read, state_get, state_set, task_record, task_update
from .paths import slug
from .suite import suite_command

DEFAULT_PHASES = [
    "observe.snapshot",
    "dataset.status",
    "dataset.browser",
    "patch.verify",
    "tools.doctor",
    "diag.invariants",
    "diag.conformance",
    "build.status",
    "analyze.system",
]

PHASE_PRESETS: Dict[str, List[str]] = {
    "observe": ["observe.snapshot", "bridge.restart.status", "dataset.status", "dataset.browser", "logs.list"],
    "verify": ["patch.verify", "tools.doctor", "diag.invariants", "diag.conformance", "build.status"],
    "dataset": ["dataset.status", "dataset.materialize", "dataset.index", "dataset.browser", "dataset.status"],
    "dataset.browser": ["dataset.status", "dataset.browser"],
    "references": ["dataset.status", "dataset.browser", "dataset.search_logic"],
    "restart": ["bridge.restart.status", "bridge.restart.stop-origin", "bridge.restart.wait-down"],
    "restart.check": ["bridge.restart.status", "bridge.restart.wait-up"],
    "p0": [
        "observe.snapshot",
        "bridge.restart.status",
        "dataset.status",
        "dataset.browser",
        "patch.verify",
        "tools.doctor",
        "diag.invariants",
        "diag.conformance",
        "build.status",
        "analyze.system",
    ],
}

SUITE_ACTION_PREFIXES = (
    "build.",
    "cache.",
    "diag.",
    "import.",
    "patch.",
    "runtime.",
    "source.",
    "suite.",
    "tools.",
    "workspace.",
)


def _ok(value: Dict[str, Any]) -> bool:
    if "ok" in value:
        return bool(value.get("ok"))
    if "error" in value:
        return False
    return True


def _state_unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value and "_digest" in value:
        return value.get("value")
    return value


def _operator_state(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    raw = ((snapshot.get("operator_state") or {}).get("value") or {}) if isinstance(snapshot, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): _state_unwrap(v) for k, v in raw.items()}


def _restart_args(args: Dict[str, Any], command: str) -> Dict[str, Any]:
    return {
        "command": command,
        "host": args.get("bridge_host", args.get("host", "127.0.0.1")),
        "port": args.get("bridge_port", args.get("port", 8797)),
        "timeout": args.get("bridge_timeout", args.get("timeout", 1.0)),
        "wait_sec": args.get("bridge_wait_sec", args.get("wait_sec", 30.0)),
        "dry_run": bool(args.get("dry_run", False)),
    }


def _native_phase_handlers() -> Dict[str, Callable[[BridgeContext, Dict[str, Any]], Dict[str, Any]]]:
    return {
        "observe.snapshot": lambda ctx, args: bridge_status.operator_snapshot(ctx, {
            "logs_limit": args.get("logs_limit", 20),
            "dataset_limit": args.get("dataset_limit", 20),
        }),
        "status": lambda ctx, args: bridge_status.status(ctx, {}),
        "status.bridge": lambda ctx, args: bridge_status.status(ctx, {}),
        "operator.snapshot": lambda ctx, args: bridge_status.operator_snapshot(ctx, {
            "logs_limit": args.get("logs_limit", 20),
            "dataset_limit": args.get("dataset_limit", 20),
        }),
        "bridge.restart.status": lambda ctx, args: bridge_restart.bridge_restart(ctx, _restart_args(args, "status")),
        "bridge.restart.stop-origin": lambda ctx, args: bridge_restart.bridge_restart(ctx, _restart_args(args, "stop-origin")),
        "bridge.restart.wait-down": lambda ctx, args: bridge_restart.bridge_restart(ctx, _restart_args(args, "wait-down")),
        "bridge.restart.wait-up": lambda ctx, args: bridge_restart.bridge_restart(ctx, _restart_args(args, "wait-up")),
        "bridge.restart.sequence": lambda ctx, args: bridge_restart.bridge_restart_sequence(ctx, _restart_args(args, "status")),
        "dataset.status": lambda ctx, args: dataset.status(ctx, {}),
        "dataset.materialize": lambda ctx, args: dataset.materialize_archives(ctx, {
            "limit": args.get("dataset_limit", 20),
            "force": args.get("force_dataset", False),
        }),
        "dataset.index": lambda ctx, args: dataset.rebuild_index(ctx, {}),
        "dataset.browser": lambda ctx, args: dataset.browse_directories(ctx, {
            "path": args.get("dataset_path", ""),
            "depth": args.get("dataset_browser_depth", 1),
            "limit": args.get("dataset_browser_limit", args.get("dataset_limit", 40)),
            "max_files": args.get("dataset_browser_max_files", 500),
            "profile": True,
        }),
        "dataset.profile": lambda ctx, args: dataset.profile_directory(ctx, {
            "path": args.get("dataset_path", ""),
            "max_files": args.get("dataset_profile_max_files", 8000),
            "sample_limit": args.get("dataset_profile_sample_limit", 100),
        }),
        "dataset.search_logic": lambda ctx, args: dataset.search_logic(ctx, {
            "query": args.get("dataset_query", args.get("query", "")),
            "path": args.get("dataset_path", ""),
            "limit": args.get("dataset_search_limit", args.get("dataset_limit", 100)),
            "case_sensitive": args.get("case_sensitive", False),
        }),
        "logs.list": lambda ctx, args: repo.list_logs(ctx, {"limit": args.get("logs_limit", 30)}),
        "memory.state": lambda ctx, args: state_get(ctx, {"namespace": "operator"}),
        "notes.read": lambda ctx, args: note_read(ctx, {"limit": 5, "max_bytes": 16 * 1024, "include_current_flow": True}),
        "analyze.system": _analyze_system,
    }


def _analyze_system(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = bridge_status.operator_snapshot(ctx, {
        "logs_limit": args.get("logs_limit", 20),
        "dataset_limit": args.get("dataset_limit", 20),
    })
    ds = snapshot.get("dataset", {}) if isinstance(snapshot, dict) else {}
    st = snapshot.get("status", {}) if isinstance(snapshot, dict) else {}
    markers = ((st.get("workspace") or {}).get("markers") or {}) if isinstance(st, dict) else {}
    extracted_count = int(ds.get("extracted_count", 0) or 0) if isinstance(ds, dict) else 0
    archive_count = int(ds.get("archive_count", 0) or 0) if isinstance(ds, dict) else 0
    browser = ds.get("browser", {}) if isinstance(ds, dict) else {}
    op_state = _operator_state(snapshot)
    warnings: List[str] = []
    if not markers.get("aiBridge.bat"):
        warnings.append("aiBridge.bat marker is missing; launcher drift repair is required")
    if archive_count and not extracted_count:
        warnings.append("dataset archives exist but extracted directory mirrors are empty; run dataset.materialize")
    if extracted_count and not op_state.get("dataset_browser_last"):
        warnings.append("dataset is materialized but no browser result is cached yet; run dataset.browser")
    if not op_state.get("bridge_restart_last"):
        warnings.append("bridge restart status has not been sampled in operator memory yet; run bridge.restart.status")
    return {
        "ok": True,
        "summary": {
            "bridge_alive": bool(st),
            "dataset_archives": archive_count,
            "dataset_extracted": extracted_count,
            "dataset_browser_enabled": bool(browser.get("enabled")) if isinstance(browser, dict) else False,
            "dataset_browser_last": op_state.get("dataset_browser_last"),
            "bridge_restart_last": op_state.get("bridge_restart_last"),
            "workspace_markers": markers,
            "last_spiral": op_state.get("last_spiral"),
            "warnings": warnings,
        },
        "recommended_next": [
            "bridge.restart.status",
            "dataset.materialize" if archive_count and not extracted_count else "dataset.browser",
            "dataset.index",
            "patch.verify",
            "tools.doctor",
            "diag.invariants",
            "build.status",
        ],
    }


def _expand_phases(raw_phases: Any) -> List[str]:
    if not raw_phases:
        return list(DEFAULT_PHASES)
    out: List[str] = []
    for item in list(raw_phases):
        key = str(item).strip()
        if key:
            out.extend(PHASE_PRESETS.get(key, [key]))
    return out or list(DEFAULT_PHASES)


def _run_phase(ctx: BridgeContext, phase: str, args: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]:
    handlers = _native_phase_handlers()
    if phase in handlers:
        return handlers[phase](ctx, args)
    if phase.startswith(SUITE_ACTION_PREFIXES):
        return suite_command(ctx, {
            "command_id": phase,
            "timeout_sec": timeout_sec,
            "allow_unlisted": bool(args.get("allow_unlisted", False)),
        })
    raise BridgeError("unknown spiral phase", "unknown_phase", {"phase": phase, "known_native": sorted(handlers), "suite_prefixes": list(SUITE_ACTION_PREFIXES)})


def _record_state(ctx: BridgeContext, namespace: str, key: str, value: Any) -> None:
    if ctx.write_enabled:
        state_set(ctx, {"namespace": namespace, "key": key, "value": value})


def _record_cache(ctx: BridgeContext, namespace: str, key: str, value: Any) -> None:
    if ctx.write_enabled:
        cache_set(ctx, {"namespace": namespace, "key": key, "value": value})


def _compact_result(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {"type": type(result).__name__}
    compact: Dict[str, Any] = {"keys": sorted(str(k) for k in result.keys())[:24]}
    for key in ("ok", "reason", "query", "base", "truncated", "completed_steps", "write_enabled", "command", "exit_code", "elapsed_ms", "error", "message", "path", "browser_path", "knowledge_path", "file_count", "directory_count", "topic_count"):
        if key in result:
            compact[key] = result.get(key)
    if "items" in result and isinstance(result["items"], list):
        compact["item_count"] = len(result["items"])
        compact["top_items"] = [{"path": item.get("path"), "logic_score": item.get("logic_score"), "file_count_sampled": item.get("file_count_sampled"), "logic_dirs": item.get("logic_dirs")} for item in result["items"][:10] if isinstance(item, dict)]
    if "profile" in result and isinstance(result["profile"], dict):
        profile = result["profile"]
        compact["profile"] = {"path": profile.get("path"), "logic_score": profile.get("logic_score"), "file_count_sampled": profile.get("file_count_sampled"), "extension_summary": profile.get("extension_summary"), "logic_dirs": profile.get("logic_dirs"), "logic_files": profile.get("logic_files", [])[:10]}
    if "hits" in result and isinstance(result["hits"], list):
        compact["hit_count"] = len(result["hits"])
        compact["top_hits"] = result["hits"][:20]
    if "steps" in result and isinstance(result["steps"], list):
        compact["step_count"] = len(result["steps"])
        compact["steps"] = [_compact_result(step) if isinstance(step, dict) else {"value": str(step)[:200]} for step in result["steps"][:8]]
    if "stdout" in result:
        compact["stdout_preview"] = str(result.get("stdout", ""))[:1000]
    if "stderr" in result and result.get("stderr"):
        compact["stderr_preview"] = str(result.get("stderr", ""))[:1000]
    if "summary" in result:
        compact["summary"] = result.get("summary")
    return compact


def _record_dataset_browser_handoff(ctx: BridgeContext, task_id: str, phase: str, result: Dict[str, Any]) -> None:
    if not phase.startswith("dataset."):
        return
    compact = _compact_result(result)
    _record_state(ctx, "operator", "dataset_browser_last", {"phase": phase, "task_id": task_id, "updated_at": now_utc(), "result": compact})
    _record_cache(ctx, "dataset-browser", f"{task_id}-{phase}", compact)


def _record_bridge_restart_handoff(ctx: BridgeContext, task_id: str, phase: str, result: Dict[str, Any]) -> None:
    if not phase.startswith("bridge.restart"):
        return
    compact = _compact_result(result)
    event = {"phase": phase, "task_id": task_id, "updated_at": now_utc(), "result": compact}
    _record_state(ctx, "operator", "bridge_restart_last", event)
    _record_cache(ctx, "bridge-restart", "latest", event)
    _record_cache(ctx, "bridge-restart", f"{task_id}-{phase}", event)


def _note(ctx: BridgeContext, title: str, phase: str, task_id: str, body: Any, tags: List[str]) -> None:
    note_append(ctx, {"title": title, "phase": phase, "task_id": task_id, "note": body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2), "tags": tags})


def workflow_spiral(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    task = str(args.get("task", "North Star spiral workflow"))
    task_id = str(args.get("task_id") or slug(task, "spiral"))
    phases = _expand_phases(args.get("phases"))
    if bool(args.get("check_bridge", False)) and "bridge.restart.status" not in phases:
        phases.insert(1 if phases and phases[0].startswith("observe") else 0, "bridge.restart.status")
    if bool(args.get("materialize_dataset", False)) and "dataset.materialize" not in phases:
        insert_at = 1 if phases and phases[0].startswith("observe") else 0
        phases.insert(insert_at, "dataset.materialize")
        if "dataset.index" not in phases:
            phases.insert(insert_at + 1, "dataset.index")
        if "dataset.browser" not in phases:
            phases.insert(insert_at + 2, "dataset.browser")
    if bool(args.get("browse_dataset", False)) and "dataset.browser" not in phases:
        phases.insert(1 if phases and phases[0].startswith("observe") else 0, "dataset.browser")
    if bool(args.get("include_build", False)) and "build.plugins.dev" not in phases:
        phases.append("build.plugins.dev")
    if bool(args.get("include_runtime", False)) and "runtime.run" not in phases:
        phases.append("runtime.run")

    max_steps = max(1, min(int(args.get("max_steps", len(phases))), 50))
    timeout_sec = max(5, min(int(args.get("timeout_sec", 300)), 3600))
    stop_on_failure = bool(args.get("stop_on_failure", True))
    run_id = f"{task_id}-{slug(now_utc())}"
    planned = phases[:max_steps]

    _note(ctx, "workflow spiral start", "start", task_id, {"task": task, "run_id": run_id, "phases": planned, "timeout_sec": timeout_sec, "write_enabled": ctx.write_enabled}, ["workflow", "spiral", "start"])
    _record_state(ctx, "operator", "current_spiral", {"task": task, "task_id": task_id, "run_id": run_id, "phases": phases, "started_at": now_utc(), "status": "running", "dataset_path": args.get("dataset_path", ""), "dataset_query": args.get("dataset_query", args.get("query", ""))})
    if ctx.write_enabled:
        try:
            task_record(ctx, {
                "task_id": task_id,
                "title": task,
                "task": task,
                "intent": task,
                "status": "running",
                "phase": "start",
                "source": "workflow_spiral",
                "tags": ["workflow", "spiral"],
                "constraints": {"phases": phases, "max_steps": max_steps, "timeout_sec": timeout_sec, "stop_on_failure": stop_on_failure},
                "state_snapshot": {"dataset_path": args.get("dataset_path", ""), "dataset_query": args.get("dataset_query", args.get("query", ""))},
                "summary": "workflow spiral started",
            })
        except Exception:
            pass

    results: List[Dict[str, Any]] = []
    for index, phase in enumerate(planned, 1):
        started_at = now_utc()
        _note(ctx, "workflow spiral phase", phase, task_id, f"Starting phase {index}/{len(planned)}: {phase}", ["workflow", "spiral", "phase"])
        try:
            result = _run_phase(ctx, phase, args, timeout_sec)
        except BridgeError as exc:
            result = {"ok": False, "error": exc.code, "message": str(exc), **exc.data}
        except Exception as exc:
            result = {"ok": False, "error": "phase_exception", "message": str(exc), "phase": phase}

        step = {"index": index, "phase": phase, "ok": _ok(result), "started_at": started_at, "finished_at": now_utc(), "result": result}
        results.append(step)
        compact_step = {k: v for k, v in step.items() if k != "result"}
        compact_step["result"] = _compact_result(result)
        _record_state(ctx, "operator", "last_spiral_step", compact_step)
        _record_cache(ctx, "workflow", task_id, {"last_step": compact_step, "completed_steps": len(results), "run_id": run_id})
        _record_dataset_browser_handoff(ctx, task_id, phase, result)
        _record_bridge_restart_handoff(ctx, task_id, phase, result)
        if ctx.write_enabled:
            try:
                task_update(ctx, {
                    "task_id": task_id,
                    "status": "running" if step["ok"] else "blocked",
                    "phase": phase,
                    "event_type": "workflow.phase.result",
                    "summary": f"phase {index}/{len(planned)} {phase} {'ok' if step['ok'] else 'failed'}",
                    "state_delta": {"step": compact_step},
                    "diagnostics": [] if step["ok"] else [compact_step["result"]],
                    "next_actions": [] if step["ok"] else [{"priority": "P0", "action": "inspect failed workflow phase", "phase": phase}],
                })
            except Exception:
                pass
        _note(ctx, "workflow spiral phase result", phase, task_id, {"phase": phase, "ok": step["ok"], "compact_result": compact_step["result"]}, ["workflow", "spiral", "result", "ok" if step["ok"] else "failed"])
        if not step["ok"] and stop_on_failure:
            break

    final_ok = all(bool(step["ok"]) for step in results)
    final_state = {"task": task, "task_id": task_id, "run_id": run_id, "status": "completed" if final_ok else "stopped_on_failure", "completed_steps": len(results), "planned_steps": len(phases), "finished_at": now_utc(), "failed_phase": next((step["phase"] for step in results if not step["ok"]), None), "next_phase": phases[len(results)] if len(results) < len(phases) else None}
    compact_steps = [{k: v for k, v in step.items() if k != "result"} | {"result": _compact_result(step.get("result"))} for step in results]
    _record_state(ctx, "operator", "last_spiral", final_state)
    _record_state(ctx, "operator", "current_spiral", final_state)
    _record_cache(ctx, "workflow", f"{task_id}-last-result", {"state": final_state, "steps": compact_steps})
    if ctx.write_enabled:
        try:
            task_update(ctx, {
                "task_id": task_id,
                "status": final_state["status"],
                "phase": "final",
                "event_type": "workflow.final",
                "summary": f"workflow finished with status={final_state['status']} completed_steps={len(results)}",
                "state_delta": {"final_state": final_state, "steps": compact_steps},
                "next_actions": [{"action": final_state.get("next_phase"), "reason": "next planned phase"}] if final_state.get("next_phase") else [],
            })
            knowledge_update(ctx, {
                "type": "workflow_result",
                "subject": f"Workflow result: {task}",
                "summary": f"Task {task_id} finished with status={final_state['status']}; completed {len(results)}/{len(phases)} planned phases.",
                "task_id": task_id,
                "tags": ["workflow", "engine-state", "suite"],
                "evidence": {"state": final_state, "steps": compact_steps},
                "next_actions": [{"action": final_state.get("next_phase"), "reason": "next planned phase"}] if final_state.get("next_phase") else [],
            })
        except Exception:
            pass
    _note(ctx, "workflow spiral final", "final", task_id, {"state": final_state, "steps": compact_steps}, ["workflow", "spiral", "final", "ok" if final_ok else "failed"])
    return {"ok": final_ok, "task": task, "task_id": task_id, "run_id": run_id, "steps": results, "completed_steps": len(results), "write_enabled": ctx.write_enabled, "state": final_state}
