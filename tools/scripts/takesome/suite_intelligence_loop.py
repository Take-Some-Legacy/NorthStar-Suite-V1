from __future__ import annotations

try:
    from .noesis_task_artifact_writer import maybe_write_task_artifacts
except Exception:  # pragma: no cover - task artifact writer must never break the workloop
    maybe_write_task_artifacts = None

try:
    from .noesis_chat import emit_from_current_state
except Exception:  # pragma: no cover - chat must never break the workloop
    emit_from_current_state = None

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from .paths import rel
from .assistant_memory import load_assistant_memory, write_memory_snapshot
from .assistant_presence import build_assigned_task, update_assistant_presence, write_assigned_task
from .stage_detector import detect_workloop_stage
from .task_classifier import classify_task_candidates
from .task_scanner import scan_task_context, write_task_scan
from .workloop_policy import decide_next_assignment
from .workloop_trace import append_workloop_trace, finalize_workloop_decision
from .suite.registry import build_suite_registry
from .suite_intelligence import (
    ask_openai_for_task_plan,
    candidate_to_json,
    classify_signals,
    collect_context_logs,
    detect_torch_status,
    detect_external_torch_status,
    detect_torch_status_for_python,
    resolve_python_executable,
    openai_status_to_json,
    read_openai_key,
    run_self_checks,
    scan_suite_workspace,
    score_actions,
    torch_status_to_json,
)

DEFAULT_GOAL = "Keep Noesis Suite healthy: detect bugs, errors, stale tools, and next useful improvements."
DEFAULT_LOCAL_MODEL_ROOT = Path(r"D:\LLM\DeepSeek-R1-Distill-Qwen-7B-PyTorch")


def suite_intelligence_loop_command(root: Path, args: argparse.Namespace) -> int:
    """Resident Suite Intelligence loop.

    Foreground-owned resident loop:
    - scans Suite/workspace state;
    - self-checks its own wiring;
    - ranks next executable Suite actions;
    - calls OpenAI on a throttle when configured;
    - writes operator-request.md when it needs human/assistant input;
    - optionally waits for operator-response.md before continuing.
    """

    interval_sec = max(5, int(getattr(args, "interval_sec", 30) or 30))
    cycles = max(0, int(getattr(args, "cycles", 0) or 0))
    top = max(1, int(getattr(args, "top", 8) or 8))
    openai_every = max(1, int(getattr(args, "openai_every", 3) or 3))
    no_openai = bool(getattr(args, "no_openai", False))
    json_mode = bool(getattr(args, "json", False))
    wait_for_operator = bool(getattr(args, "wait_for_operator", False))
    operator_timeout_sec = max(0, int(getattr(args, "operator_timeout_sec", 0) or 0))
    goal = str(getattr(args, "goal", "") or "").strip() or DEFAULT_GOAL
    model = str(getattr(args, "openai_model", "") or os.environ.get("NORTHSTAR_SUITE_OPENAI_MODEL") or "gpt-5.5").strip()
    local_model_root = Path(str(getattr(args, "local_model_root", "") or os.environ.get("NORTHSTAR_LOCAL_MODEL_ROOT") or DEFAULT_LOCAL_MODEL_ROOT))

    state_dir = root / ".takesome" / "intelligence"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "loop-state.json"
    events_path = state_dir / "loop-events.jsonl"
    inbox_path = state_dir / "inbox.md"
    request_path = state_dir / "operator-request.md"
    response_path = state_dir / "operator-response.md"
    pilot_status_path = state_dir / "pilot-status.md"
    trace_path = state_dir / "workloop-trace.jsonl"
    trace_summary_path = state_dir / "workloop-trace.md"

    if not json_mode:
        print("[INFO] Noesis Suite Intelligence loop started.")
        print(f"[INFO] State: {rel(root, state_path)}")
        print(f"[INFO] Events: {rel(root, events_path)}")
        print(f"[INFO] Inbox: {rel(root, inbox_path)}")
        print(f"[INFO] Operator request: {rel(root, request_path)}")
        print(f"[INFO] Operator response: {rel(root, response_path)}")
        print(f"[INFO] Pilot status: {rel(root, pilot_status_path)}")
        print(f"[INFO] Workloop trace: {rel(root, trace_path)}")
        print(f"[INFO] Workloop trace summary: {rel(root, trace_summary_path)}")
        print(f"[INFO] Local model root: {local_model_root}")
        print(f"[INFO] cycles={'infinite' if cycles == 0 else cycles}, interval_sec={interval_sec}, openai_every={openai_every}")

    cycle_index = 0
    while True:
        cycle_index += 1
        update_assistant_presence(
            root,
            state="thinking",
            phase="cycle_start",
            cycle={"cycle": cycle_index},
            message="Starting Noesis Suite intelligence cycle and checking current work status.",
        )
        openai_allowed = (not no_openai) and (cycle_index == 1 or cycle_index % openai_every == 0)
        cycle = run_intelligence_cycle(
            root=root,
            cycle_index=cycle_index,
            goal=merge_goal_with_inbox(goal, inbox_path),
            top=top,
            model=model,
            openai_allowed=openai_allowed,
            local_model_root=local_model_root,
        )
        update_assistant_presence(
            root,
            state="working",
            phase="cycle_scanned",
            cycle=cycle,
            message="Cycle scan and recommendation ranking completed; preparing operator request and workloop decision.",
        )
        write_operator_request(root, request_path, cycle)
        append_workloop_trace(root, state_dir, cycle=cycle, phase="operator_request_written", message="Operator request file was written for this cycle.", extra={"path": rel(root, request_path)})
        update_assistant_presence(
            root,
            state="waiting",
            phase="operator_wait",
            cycle=cycle,
            message="Waiting for operator response or deciding whether to assign a safe next task.",
        )
        if wait_for_operator:
            cycle["operator_response"] = wait_for_operator_response(response_path, timeout_sec=operator_timeout_sec)
        else:
            cycle["operator_response"] = read_operator_response(response_path)
        append_workloop_trace(root, state_dir, cycle=cycle, phase="operator_response_read", message="Operator response was read and will be interpreted by markdown rules.", operator_response=cycle["operator_response"], extra={"path": rel(root, response_path)})

        memory = load_assistant_memory(root)
        append_workloop_trace(root, state_dir, cycle=cycle, phase="memory_loaded", message="Assistant memory loaded before task scan and stage detection.", operator_response=cycle["operator_response"], extra={"has_summary": isinstance(memory.get("summary"), dict) if isinstance(memory, dict) else False})
        task_scan = write_task_scan(root, scan_task_context(root, cycle=cycle))
        append_workloop_trace(root, state_dir, cycle=cycle, phase="task_scan_written", message="Task scan was written; stage detection can use repo/log/operator signals.", operator_response=cycle["operator_response"], extra={"path": rel(root, state_dir / "task-scan.json")})
        stage = detect_workloop_stage(
            cycle=cycle,
            memory=memory,
            task_scan=task_scan,
            operator_response=cycle["operator_response"],
        )
        append_workloop_trace(root, state_dir, cycle=cycle, phase="stage_detected", message="Workloop stage was detected from markdown-rule-aware operator response and scan signals.", stage=stage, operator_response=cycle["operator_response"])
        classified = classify_task_candidates(
            cycle.get("recommendations", []),
            stage=stage,
            memory=memory,
            task_scan=task_scan,
        )
        append_workloop_trace(root, state_dir, cycle=cycle, phase="candidates_classified", message="Task candidates were classified before final assignment policy.", stage=stage, operator_response=cycle["operator_response"], extra={"candidate_count": len(classified.get("candidates", [])) if isinstance(classified.get("candidates"), list) else 0})
        decision = decide_next_assignment(
            root=root,
            cycle=cycle,
            memory=memory,
            task_scan=task_scan,
            stage=stage,
            classified=classified,
            operator_response=cycle["operator_response"],
        )
        append_workloop_trace(root, state_dir, cycle=cycle, phase="decision_initial", message="Initial workloop decision was created; final persistence will happen after assignment materialization.", stage=stage, decision=decision, operator_response=cycle["operator_response"])
        assignment = None
        if decision.get("assign"):
            assignment = build_assigned_task(
                root,
                cycle,
                reason="; ".join(str(reason) for reason in decision.get("reasons", []) if reason),
                operator_response=cycle["operator_response"],
                selected_candidate=decision.get("selected_candidate") if isinstance(decision.get("selected_candidate"), dict) else None,
                execution_policy=str(decision.get("execution_policy") or "assignment_only_no_auto_execute"),
                status=str(decision.get("status") or "assigned"),
                stage=stage,
                decision=decision,
            )
            write_assigned_task(root, assignment)
            append_workloop_trace(root, state_dir, cycle=cycle, phase="assignment_written", message="Assigned task JSON and Markdown were written from the final selected candidate.", stage=stage, decision=decision, assignment=assignment, operator_response=cycle["operator_response"])

        decision = finalize_workloop_decision(
            state_dir,
            decision,
            stage=stage,
            assignment=assignment,
            recommendations=cycle.get("recommendations", []) if isinstance(cycle.get("recommendations"), list) else [],
            cycle=cycle,
        )
        append_workloop_trace(root, state_dir, cycle=cycle, phase="decision_finalized", message="Final MD-rule-aware decision was persisted as the single source for console/status/runtime files.", stage=stage, decision=decision, assignment=assignment, operator_response=cycle["operator_response"])

        cycle["task_scan"] = task_scan
        cycle["stage"] = stage
        cycle["task_candidates"] = classified
        cycle["workloop_decision"] = decision
        cycle["assigned_task"] = assignment
        cycle["assistant_memory"] = write_memory_snapshot(root, memory, cycle=cycle)
        presence_state = "blocked" if stage.get("blocked") else ("assigned" if assignment else str(stage.get("state") or "working"))
        cycle["assistant_presence"] = update_assistant_presence(
            root,
            state=presence_state,
            phase="workloop_decision",
            cycle=cycle,
            operator_response=cycle["operator_response"],
            assignment=assignment,
            message="Noesis workloop memory, scan, stage detection and assignment policy completed.",
            extra={"decision": decision, "stage": stage},
        )
        append_workloop_trace(root, state_dir, cycle=cycle, phase="presence_updated", message="Assistant presence was updated with the same final decision and assignment.", stage=stage, decision=decision, assignment=assignment, operator_response=cycle["operator_response"])

        write_pilot_status(root, pilot_status_path, cycle)
        state_path.write_text(json.dumps(cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(cycle, ensure_ascii=False) + "\n")
        append_workloop_trace(root, state_dir, cycle=cycle, phase="cycle_persisted", message="Full cycle state and event payload were persisted.", stage=stage, decision=decision, assignment=assignment, operator_response=cycle["operator_response"], extra={"state": rel(root, state_path), "events": rel(root, events_path)})
        # noesis_task_artifact_writer_after_cycle_persisted
        if maybe_write_task_artifacts is not None:
            try:
                maybe_write_task_artifacts(root, force=False)
            except Exception as exc:
                print(f"[WARN] noesis task artifact writer failed: {exc}", flush=True)
        # noesis_chat_emit_after_cycle_persisted
        if emit_from_current_state is not None:
            try:
                emit_from_current_state(root, force=False)
            except Exception as exc:
                print(f"[WARN] noesis chat emit failed: {exc}", flush=True)

        if json_mode:
            print(json.dumps(cycle, ensure_ascii=False, indent=2))
        else:
            print(render_cycle_line(cycle))
            advice = str(cycle.get("openai_advice") or "").strip()
            if advice:
                print("[OPENAI] " + advice.replace("\n", "\n[OPENAI] "))
            request = str(cycle.get("operator_request") or "").strip()
            if request:
                print(f"[ASK] {rel(root, request_path)}")

        if cycles and cycle_index >= cycles:
            return 0 if all(check.get("ok") for check in cycle.get("self_checks", [])) else 1
        time.sleep(interval_sec)


def run_intelligence_cycle(*, root: Path, cycle_index: int, goal: str, top: int, model: str, openai_allowed: bool, local_model_root: Path) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    suite_torch_status = detect_torch_status()
    configured_pilot_python = os.environ.get("NORTHSTAR_SUITE_LLM_PYTHON", "").strip()
    pilot_python, pilot_python_source = resolve_python_executable(configured_pilot_python)
    pilot_torch_status = detect_torch_status_for_python(pilot_python)
    torch_status = pilot_torch_status if pilot_torch_status.available else suite_torch_status
    log_text, log_sources = collect_context_logs(root)
    scan = scan_suite_workspace(root)
    scan["local_model_root"] = str(local_model_root)
    scan["local_model_root_exists"] = int(local_model_root.exists())
    scan["local_model_files"] = count_local_model_files(local_model_root)
    signals = classify_signals(goal, log_text)
    registry = build_suite_registry(root)
    candidates = score_actions(registry.actions(), goal=goal, signals=signals, torch_status=torch_status)
    selected = candidates[:top]
    self_checks = run_self_checks(root, registry_actions=[candidate.action_id for candidate in candidates], torch_status=torch_status)
    self_checks.append({
        "name": "Suite LLM pilot Python resolved",
        "ok": pilot_torch_status.available,
        "detail": f"python={pilot_python}; source={pilot_python_source}; {_torch_line_safe(pilot_torch_status)}",
    })

    openai_key, openai_source = read_openai_key(root)
    openai_status = {
        "configured": bool(openai_key),
        "source": openai_source,
        "model": model,
        "attempted": False,
        "ok": False,
        "summary": "",
        "error": "",
    }
    openai_advice = ""
    if openai_allowed:
        status_obj, openai_advice = ask_openai_for_task_plan(
            root=root,
            goal=goal,
            model=model,
            scan=scan,
            signals=signals,
            recommendations=[candidate_to_json(candidate) for candidate in selected],
            log_sources=[rel(root, path) for path in log_sources],
        )
        openai_status = openai_status_to_json(status_obj)

    request = build_operator_request(cycle_index=cycle_index, self_checks=self_checks, openai_status=openai_status, selected=[candidate_to_json(candidate) for candidate in selected])
    return {
        "schema": "noesis.suite_intelligence.loop_cycle.v3",
        "cycle": cycle_index,
        "started_utc": started,
        "goal": goal,
        "torch": torch_status_to_json(torch_status),
        "suite_python_torch": torch_status_to_json(suite_torch_status),
        "pilot": {
            "domain": "suite.tool_plane",
            "not_engine_ai": True,
            "provider": os.environ.get("NORTHSTAR_SUITE_LLM_PROVIDER", "deepseek-pytorch-local"),
            "configured_python": configured_pilot_python,
            "python": pilot_python,
            "python_source": pilot_python_source,
            "torch": torch_status_to_json(pilot_torch_status),
            "active_for_ranking": bool(pilot_torch_status.available),
            "model_root": str(local_model_root),
            "model_root_exists": bool(local_model_root.exists()),
            "model_files": count_local_model_files(local_model_root),
        },
        "openai": openai_status,
        "openai_advice": openai_advice,
        "self_checks": self_checks,
        "scan": scan,
        "signals": signals,
        "log_sources": [rel(root, path) for path in log_sources],
        "recommendations": [candidate_to_json(candidate) for candidate in selected],
        "operator_request": request,
        "next_command": f"python tools/scripts/takesome.py suite --run {selected[0].action_id}" if selected else "",
    }


def build_operator_request(*, cycle_index: int, self_checks: list[dict[str, object]], openai_status: dict[str, object], selected: list[dict[str, object]]) -> str:
    failed = [check for check in self_checks if not check.get("ok")]
    lines: list[str] = []
    if failed:
        lines.append(f"Cycle {cycle_index}: Suite Intelligence self-check has {len(failed)} failing checks.")
        for check in failed:
            lines.append(f"- {check.get('name')}: {check.get('detail')}")
    if openai_status.get("attempted") and not openai_status.get("ok"):
        lines.append(f"Cycle {cycle_index}: cloud planner call failed: {openai_status.get('error')}")
    if selected:
        top = selected[0]
        lines.append(f"Cycle {cycle_index}: proposed next action is {top.get('action_id')} with score={top.get('score')}.")
        lines.append("Approve, override, or provide a new operator instruction in operator-response.md.")
    return "\n".join(lines).strip()



def _torch_line_safe(status: Any) -> str:
    try:
        if not status.available:
            return f"PyTorch unavailable: {status.error}"
        if status.cuda_available:
            names = ", ".join(status.cuda_devices) if status.cuda_devices else "CUDA device"
            return f"PyTorch {status.version}; CUDA devices={status.cuda_device_count}; selected={status.selected_device}; names={names}"
        return f"PyTorch {status.version}; CUDA unavailable; selected=cpu"
    except Exception as exc:
        return f"invalid torch status: {type(exc).__name__}: {exc}"


def write_pilot_status(root: Path, status_path: Path, cycle: dict[str, Any]) -> None:
    recommendations = cycle.get("recommendations", []) if isinstance(cycle.get("recommendations"), list) else []
    top = recommendations[0] if recommendations and isinstance(recommendations[0], dict) else {}
    openai = cycle.get("openai", {}) if isinstance(cycle.get("openai"), dict) else {}
    pilot = cycle.get("pilot", {}) if isinstance(cycle.get("pilot"), dict) else {}
    torch_info = pilot.get("torch", {}) if isinstance(pilot.get("torch"), dict) else {}
    lines = [
        "# Noesis Suite Intelligence — Pilot Status",
        "",
        f"cycle: {cycle.get('cycle')}",
        f"started_utc: {cycle.get('started_utc')}",
        "domain: suite.tool_plane",
        "not_engine_ai: true",
        "",
        "## What I checked",
        f"- self_checks_failed: {len([c for c in cycle.get('self_checks', []) if isinstance(c, dict) and not c.get('ok')])}",
        f"- changed_files: {cycle.get('scan', {}).get('changed_files') if isinstance(cycle.get('scan'), dict) else 'unknown'}",
        f"- local_model_root: {cycle.get('scan', {}).get('local_model_root') if isinstance(cycle.get('scan'), dict) else 'unknown'}",
        f"- local_model_files: {cycle.get('scan', {}).get('local_model_files') if isinstance(cycle.get('scan'), dict) else 'unknown'}",
        "",
        "## What I think is happening",
        f"- OpenAI attempted: {openai.get('attempted')} ok: {openai.get('ok')}",
        f"- OpenAI error: {openai.get('error') or ''}",
        f"- Pilot python: {pilot.get('python') or ''}",
        f"- Pilot torch: version={torch_info.get('version')} cuda={torch_info.get('cuda_available')} devices={torch_info.get('cuda_device_count')} selected={torch_info.get('selected_device')}",
        "",
        "## What I propose next",
        f"- action_id: {top.get('action_id') or 'none'}",
        f"- score: {top.get('score') or ''}",
        f"- label: {top.get('label') or ''}",
        "",
        "## Noesis Workloop",
        f"- stage: {(cycle.get('stage') or {}).get('stage') if isinstance(cycle.get('stage'), dict) else ''}",
        f"- decision: {(cycle.get('workloop_decision') or {}).get('status') if isinstance(cycle.get('workloop_decision'), dict) else ''}",
        f"- assigned_task: {((cycle.get('assigned_task') or {}).get('task') or {}).get('id') if isinstance(cycle.get('assigned_task'), dict) else ''}",
        "",
        "## Supporting facts",
    ]
    for reason in top.get("reasons", []) if isinstance(top.get("reasons"), list) else []:
        lines.append(f"- {reason}")
    lines.extend([
        "",
        "## Operator correction channel",
        "Write corrections/new task requests to `.takesome/intelligence/inbox.md` or answer in `.takesome/intelligence/operator-response.md` using APPROVE / OVERRIDE / NOTE.",
        "",
    ])
    status_path.write_text("\n".join(lines), encoding="utf-8")


def write_operator_request(root: Path, request_path: Path, cycle: dict[str, Any]) -> None:
    request = str(cycle.get("operator_request") or "").strip()
    header = [
        "# Noesis Suite Intelligence — Operator Request",
        "",
        f"cycle: {cycle.get('cycle')}",
        f"started_utc: {cycle.get('started_utc')}",
        "",
    ]
    if request:
        body = request
    else:
        body = "No operator intervention requested. The loop is healthy."
    body += "\n\n## Response contract\nWrite one of:\n- APPROVE\n- OVERRIDE: <suite action id or instruction>\n- NOTE: <message>\n"
    request_path.write_text("\n".join(header) + body + "\n", encoding="utf-8")


def wait_for_operator_response(response_path: Path, *, timeout_sec: int) -> dict[str, object]:
    start = time.monotonic()
    seen_mtime = response_path.stat().st_mtime if response_path.exists() else 0.0
    while True:
        if response_path.exists() and response_path.stat().st_mtime > seen_mtime:
            return read_operator_response(response_path)
        if timeout_sec and time.monotonic() - start >= timeout_sec:
            return {"available": False, "timed_out": True, "path": str(response_path)}
        time.sleep(1.0)


def read_operator_response(response_path: Path) -> dict[str, object]:
    try:
        text = response_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return {"available": False, "path": str(response_path)}
    if not text:
        return {"available": False, "path": str(response_path)}
    return {"available": True, "path": str(response_path), "text": text[-4000:]}


def merge_goal_with_inbox(goal: str, inbox_path: Path) -> str:
    try:
        inbox = inbox_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        inbox = ""
    if not inbox:
        return goal
    return goal + "\n\nOperator inbox:\n" + inbox[-4000:]


def render_cycle_line(cycle: dict[str, Any]) -> str:
    checks = cycle.get("self_checks", []) if isinstance(cycle.get("self_checks"), list) else []
    failed = [check for check in checks if not check.get("ok")]
    recommendations = cycle.get("recommendations", []) if isinstance(cycle.get("recommendations"), list) else []
    decision = cycle.get("workloop_decision", {}) if isinstance(cycle.get("workloop_decision"), dict) else {}
    selected = decision.get("selected_candidate") if isinstance(decision.get("selected_candidate"), dict) else {}
    top_action = str(selected.get("action_id") or (recommendations[0].get("action_id") if recommendations and isinstance(recommendations[0], dict) else "none"))
    openai = cycle.get("openai", {}) if isinstance(cycle.get("openai"), dict) else {}
    openai_state = "ok" if openai.get("ok") else ("attempted_failed" if openai.get("attempted") else "skipped")
    response = cycle.get("operator_response", {}) if isinstance(cycle.get("operator_response"), dict) else {}
    response_state = "available" if response.get("available") else "none"
    stage = cycle.get("stage", {}) if isinstance(cycle.get("stage"), dict) else {}
    tag = "OK" if not failed else "WARN"
    return f"[{tag}] intelligence cycle={cycle.get('cycle')} stage={stage.get('stage', 'unknown')} decision={decision.get('status', 'none')} checks_failed={len(failed)} openai={openai_state} operator_response={response_state} next={top_action}"


def count_local_model_files(root: Path) -> int:
    if not root.exists() or not root.is_dir():
        return 0
    allowed = {".gguf", ".safetensors", ".json", ".model", ".bin"}
    try:
        return sum(1 for path in root.rglob("*") if path.is_file() and path.suffix.lower() in allowed)
    except OSError:
        return 0


def loop_args_from_env(*, cycles: int | None = None, parsed_args: argparse.Namespace | None = None) -> argparse.Namespace:
    parsed_args = parsed_args or argparse.Namespace()

    def env_bool(name: str) -> bool:
        return os.environ.get(name, "").lower() in {"1", "true", "yes"}

    def choose(name: str, env_name: str, default: object) -> object:
        value = getattr(parsed_args, name, None)
        if value not in (None, ""):
            return value
        raw = os.environ.get(env_name)
        return raw if raw not in (None, "") else default

    explicit_cycles = getattr(parsed_args, "cycles", None)
    if bool(getattr(parsed_args, "once", False)):
        explicit_cycles = 1

    return argparse.Namespace(
        goal=str(choose("goal", "NORTHSTAR_SUITE_INTELLIGENCE_GOAL", "") or ""),
        interval_sec=int(choose("interval_sec", "NORTHSTAR_SUITE_INTELLIGENCE_INTERVAL_SEC", "30") or "30"),
        cycles=(
            cycles
            if cycles is not None
            else int(explicit_cycles if explicit_cycles is not None else os.environ.get("NORTHSTAR_SUITE_INTELLIGENCE_CYCLES", "0") or "0")
        ),
        top=int(choose("top", "NORTHSTAR_SUITE_INTELLIGENCE_TOP", "8") or "8"),
        openai_every=int(choose("openai_every", "NORTHSTAR_SUITE_INTELLIGENCE_OPENAI_EVERY", "3") or "3"),
        no_openai=bool(getattr(parsed_args, "no_openai", False)) or env_bool("NORTHSTAR_SUITE_INTELLIGENCE_NO_OPENAI"),
        wait_for_operator=bool(getattr(parsed_args, "wait_for_operator", False)) or env_bool("NORTHSTAR_SUITE_INTELLIGENCE_WAIT_FOR_OPERATOR"),
        operator_timeout_sec=int(choose("operator_timeout_sec", "NORTHSTAR_SUITE_INTELLIGENCE_OPERATOR_TIMEOUT_SEC", "0") or "0"),
        openai_model=str(choose("openai_model", "NORTHSTAR_SUITE_OPENAI_MODEL", "") or ""),
        local_model_root=str(choose("local_model_root", "NORTHSTAR_LOCAL_MODEL_ROOT", str(DEFAULT_LOCAL_MODEL_ROOT)) or str(DEFAULT_LOCAL_MODEL_ROOT)),
        json=bool(getattr(parsed_args, "json", False)) or env_bool("NORTHSTAR_SUITE_INTELLIGENCE_JSON"),
    )
