from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

STATE_DIR = Path(".takesome") / "long_tasks"
BOARD_PATH = STATE_DIR / "board.json"
ITERATIONS_DIR = STATE_DIR / "iterations"
DOC_PATH = Path("docs") / "suite" / "LONG_TERM_TASKS.md"
SCHEMA = "northstar.suite.long_tasks.v1"
REPORTS_DIR = STATE_DIR / "reports"

VERIFY_PIPELINE: tuple[dict[str, Any], ...] = (
    dict(id="dataset-ingest", action="diag.dataset.ingest", kind="dataset", required=True, timeout_sec=0),
    {"id": "verify-build-tools", "action": "tools.validate.build", "kind": "verification", "required": True, "timeout_sec": 300},
    {"id": "pre-build-status", "action": "build.status", "kind": "verification", "required": False, "timeout_sec": 300},
    {"id": "build-active-plugins", "action": "build.plugins", "kind": "build", "required": True, "timeout_sec": 0},
    {"id": "post-build-status", "action": "build.status", "kind": "verification", "required": True, "timeout_sec": 300},
    {"id": "architecture-invariants", "action": "diag.invariants", "kind": "verification", "required": True, "timeout_sec": 600},
    {"id": "capability-conformance", "action": "diag.conformance", "kind": "verification", "required": True, "timeout_sec": 600},
    {"id": "render-maturity", "action": "diag.rendering", "kind": "profiling", "required": False, "timeout_sec": 600},
    {"id": "collect-run-report", "action": "tools.collect", "kind": "profiling", "required": False, "timeout_sec": 0},
)


IMPLEMENTATION_TASKS: tuple[dict[str, Any], ...] = (
    {
        "id": "impl.ui-maturity-loop",
        "kind": "implementation",
        "lane": "engine-feature",
        "domain": "engine.ui / AureliaUI",
        "title": "Finish modern UI runtime loop",
        "status": "backlog",
        "priority": 90,
        "iteration_budget": 12,
        "acceptance": [
            ".neui theme/component libraries affect mounted surfaces",
            "UI tree/layout/hit-test/focus/style/atlas diagnostics are inspectable",
            "standard widgets work through generic engine.ui composition, not product-specific renderer branches",
        ],
        "next_actions": [
            "audit current .neui import/runtime path",
            "split generic widgets from product-specific Asset Browser code",
            "add one diagnostics surface per UI ownership boundary",
        ],
        "evidence_paths": ["docs/SUITE.md", "assets/ui", "NewEngine/neocore2/logs"],
    },
    {
        "id": "impl.world-scene-loop",
        "kind": "implementation",
        "lane": "engine-feature",
        "domain": "engine.world / engine.scene / engine.entity",
        "title": "Build world/scene/save-load foundation",
        "status": "backlog",
        "priority": 88,
        "iteration_budget": 16,
        "acceptance": [
            "World construction owns archetypes, placement and streaming cells",
            "Providers never receive raw ECS World or native EntityId across service boundary",
            "Save/load snapshots and streaming dependencies are visible as DTOs and diagnostics",
        ],
        "next_actions": [
            "map current scene/runtime ownership",
            "define world snapshot DTOs and apply-stage boundaries",
            "create conformance checks for opaque entity handles",
        ],
        "evidence_paths": ["docs/architecture", "NewEngine/neocore2"],
    },
    {
        "id": "impl.render-visibility-loop",
        "kind": "implementation",
        "lane": "engine-feature",
        "domain": "engine.render / visibility providers",
        "title": "Evolve raster shadows toward capability-gated visibility stack",
        "status": "backlog",
        "priority": 82,
        "iteration_budget": 14,
        "acceptance": [
            "Raster CSM/local/contact shadow baseline is stable and profiled",
            "RT/path-tracing tiers are modeled as explicit capabilities, not hidden render branches",
            "Diagnostics explain active/shadowed visibility providers and quality tier",
        ],
        "next_actions": [
            "inventory current render feature switches",
            "write visibility capability matrix",
            "add render maturity scan checks for shadows/debug overlays",
        ],
        "evidence_paths": ["docs/render", "docs/knowledge"],
    },
    {
        "id": "impl.asset-pipeline-loop",
        "kind": "implementation",
        "lane": "engine-feature",
        "domain": "engine.assets / ListFile / import pipeline",
        "title": "Make asset pipeline preview/edit routes provider-owned and conformance-tested",
        "status": "backlog",
        "priority": 80,
        "iteration_budget": 10,
        "acceptance": [
            "Asset Browser consumes provider preview/edit contracts instead of guessing semantics",
            "NEF8/ListFile body schemas are validated for .ytd/.ydd/.ytyp/.nemat families",
            "Package writer is an explicit capability, not a hidden side effect",
        ],
        "next_actions": [
            "audit preview providers and unknown asset fallbacks",
            "add conformance tests for extension/content_kind mismatch",
            "record mutation capability matrix",
        ],
        "evidence_paths": ["docs/knowledge", "Importers", "NewEngine/neocore2"],
    },
    {
        "id": "impl.ai-foundation-loop",
        "kind": "implementation",
        "lane": "engine-feature",
        "domain": "engine.ai / tags / tasks / intents",
        "title": "Create engine.ai skeleton as DTO intent provider domain",
        "status": "backlog",
        "priority": 78,
        "iteration_budget": 12,
        "acceptance": [
            "AI provider receives AiFrameInput and returns AiFrameOutput",
            "AI emits intents/tasks/tags, never direct ECS mutation",
            "NullAI and utility-planner conformance tests exist",
        ],
        "next_actions": [
            "define AiFrameInput/AiFrameOutput DTO contracts",
            "add NullAI provider route and diagnostics",
            "seed tags/tasks dictionary examples",
        ],
        "evidence_paths": ["docs/architecture", "NewEngine/neocore2"],
    },
)


RESEARCH_TASKS: tuple[dict[str, Any], ...] = (
    {
        "id": "research.visibility-cyberpunk",
        "kind": "research",
        "lane": "engine-research",
        "domain": "render shadows / visibility",
        "title": "Cyberpunk-style visibility stack research to North Star capability map",
        "status": "backlog",
        "priority": 75,
        "iteration_budget": 6,
        "acceptance": [
            "Separate raster, hybrid RT and path-traced visibility tiers",
            "Extract provider/capability implications for North Star render graph",
            "Produce implementation risks and conformance targets",
        ],
        "next_actions": [
            "summarize research note into capability table",
            "connect each technique to render diagnostics and profile policy",
        ],
        "evidence_paths": ["docs/render", "docs/knowledge"],
    },
    {
        "id": "research.rage-ytd-asset-graph",
        "kind": "research",
        "lane": "engine-research",
        "domain": "RAGE-style texture dictionaries / assets",
        "title": "YTD/ListFile texture dictionary research to asset provider contracts",
        "status": "backlog",
        "priority": 72,
        "iteration_budget": 5,
        "acceptance": [
            "Map texture dictionary semantics to engine.assets + domain gateways",
            "Separate bytes, semantics and renderer-ready packets",
            "Define preview/import conformance cases",
        ],
        "next_actions": [
            "turn YTD research into North Star texture-dictionary DTO sketch",
            "list preview/edit behaviors a provider may expose or declare null",
        ],
        "evidence_paths": ["docs/knowledge", "Importers"],
    },
    {
        "id": "research.daycycle-cdpr",
        "kind": "research",
        "lane": "engine-research",
        "domain": "world environment / time / shadows",
        "title": "Witcher/Cyberpunk day-cycle research to engine.time + environment plan",
        "status": "backlog",
        "priority": 70,
        "iteration_budget": 5,
        "acceptance": [
            "Time-of-day, sun/moon, weather and shadow updates route through explicit domains",
            "No environment god object accumulates render/world/time logic",
            "Diagnostics can explain current environment profile and active providers",
        ],
        "next_actions": [
            "separate engine.time, environment data and render application responsibilities",
            "write acceptance checklist for clouds/sky/time integration",
        ],
        "evidence_paths": ["docs/render", "docs/architecture"],
    },
    {
        "id": "research.engine-parity-godot-unreal-unity-rage",
        "kind": "research",
        "lane": "engine-research",
        "domain": "engine architecture parity",
        "title": "Long-horizon engine parity research without copying alien architecture",
        "status": "backlog",
        "priority": 68,
        "iteration_budget": 8,
        "acceptance": [
            "Compare feature maturity through North Star domains/gateways only",
            "Convert references into provider/capability/backlog items",
            "Avoid adding game/product-shaped backend APIs",
        ],
        "next_actions": [
            "normalize comparison dimensions",
            "score North Star by explicit domain readiness and diagnostics",
        ],
        "evidence_paths": ["docs/audits", "docs/architecture"],
    },
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _task_map(tasks: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(task["id"]): dict(task) for task in tasks}


def _default_board() -> dict[str, Any]:
    tasks = [dict(task) for task in (*IMPLEMENTATION_TASKS, *RESEARCH_TASKS)]
    return {
        "schema": SCHEMA,
        "created_at": _now(),
        "updated_at": _now(),
        "iteration": 0,
        "policy": {
            "max_active_tasks": 3,
            "loop": ["select", "execute", "verify", "record", "rebalance"],
            "evidence_required": True,
            "research_to_implementation_rule": "research output must become capability, DTO, conformance or roadmap evidence before it affects engine code",
            "done_definition": [
                "changed files are known",
                "diagnostic/build/check evidence is recorded",
                "profiling/timing report is recorded",
                "success gate passed before GitHub pin",
                "next iteration has one explicit next action or status is done",
            ],
            "verification_pipeline": [stage["id"] for stage in VERIFY_PIPELINE],
            "github_pin_requires": ["last_verification.status == success", "git repository exists", "NORTHSTAR_LONG_TASK_GITHUB_PUSH=1"],
        },
        "lanes": ["engine-feature", "engine-research"],
        "tasks": tasks,
        "iterations": [],
    }


def _ensure_dirs(root: Path) -> None:
    (root / STATE_DIR).mkdir(parents=True, exist_ok=True)
    (root / ITERATIONS_DIR).mkdir(parents=True, exist_ok=True)
    (root / REPORTS_DIR).mkdir(parents=True, exist_ok=True)
    (root / DOC_PATH.parent).mkdir(parents=True, exist_ok=True)


def _load_board(root: Path) -> dict[str, Any]:
    path = root / BOARD_PATH
    if not path.exists():
        return _default_board()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Long task board is not valid JSON: {path}: {exc}") from exc
    if data.get("schema") != SCHEMA:
        raise RuntimeError(f"Unsupported long task board schema: {data.get('schema')!r}")
    return data


def _save_board(root: Path, board: dict[str, Any]) -> Path:
    _ensure_dirs(root)
    board["updated_at"] = _now()
    path = root / BOARD_PATH
    path.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _merge_seed_tasks(board: dict[str, Any], seeds: Iterable[dict[str, Any]]) -> int:
    known = _task_map(board.get("tasks", []))
    added = 0
    for seed in seeds:
        task_id = str(seed["id"])
        if task_id in known:
            continue
        board.setdefault("tasks", []).append(dict(seed))
        added += 1
    return added


def _task_counts(board: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in board.get("tasks", []):
        key = f"{task.get('kind', 'unknown')}:{task.get('status', 'unknown')}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _next_candidates(board: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    max_active = int(board.get("policy", {}).get("max_active_tasks", 3))
    limit = max_active if limit is None else limit
    tasks = [dict(task) for task in board.get("tasks", []) if task.get("status") not in {"done", "blocked"}]
    tasks.sort(key=lambda t: (-int(t.get("priority", 0)), str(t.get("id", ""))))
    return tasks[: max(0, limit)]


def _write_doctrine(root: Path, board: dict[str, Any]) -> Path:
    _ensure_dirs(root)
    counts = _task_counts(board)
    lines = [
        "# North Star Suite — Long Term Tasks",
        "",
        "> This document is generated/maintained by `long.bootstrap` and describes how Suite should handle multi-iteration implementation and research work.",
        "",
        "## Purpose",
        "",
        "The Suite is no longer only a command launcher. It is the operator layer for repeated engine work: plan, run, verify, record and rebalance.",
        "",
        "```text",
        "task request",
        "  -> Suite Long Tasks board",
        "  -> bounded iteration",
        "  -> build/diagnostic/research evidence",
        "  -> next action or done state",
        "```",
        "",
        "## Invariants",
        "",
        "- Long tasks are explicit records, not memory-only chat promises.",
        "- Implementation tasks must end in changed files, diagnostics, tests, or a precise blocker.",
        "- Research tasks must produce reusable architecture evidence before changing engine code.",
        "- Each iteration is bounded and records what moved, what failed, and what the next step is.",
        "- Each implementation iteration must pass verification/build/conformance gates before it can be pinned to GitHub.",
        "- Timing and profiling evidence is part of the Definition of Done, not optional decoration.",
        "- Engine work still follows Engine as Host, Service as Plugin, Capability as Option and Runtime as DTO Pipeline.",
        "",
        "## Canonical files",
        "",
        "```text",
        f"{BOARD_PATH.as_posix()}                  # machine-readable board",
        f"{ITERATIONS_DIR.as_posix()}/iteration-*.md  # iteration records",
        f"{REPORTS_DIR.as_posix()}/verification-*.md  # verification, build and timing reports",
        f"{DOC_PATH.as_posix()}          # operator doctrine",
        "```",
        "",
        "## Current board counts",
        "",
    ]
    for key in sorted(counts):
        lines.append(f"- `{key}`: {counts[key]}")
    lines.extend(["", "## First candidates", ""])
    for task in _next_candidates(board, 5):
        lines.append(f"- `{task['id']}` — {task['title']} ({task['domain']})")
    lines.append("")
    path = root / DOC_PATH
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def bootstrap_long_tasks(root: Path) -> int:
    board = _load_board(root)
    added = _merge_seed_tasks(board, (*IMPLEMENTATION_TASKS, *RESEARCH_TASKS))
    board_path = _save_board(root, board)
    doc_path = _write_doctrine(root, board)
    print(f"[OK] Long task board ready: {board_path}")
    print(f"[OK] Long task doctrine ready: {doc_path}")
    print(f"[STATE] tasks={len(board.get('tasks', []))} added={added} iteration={board.get('iteration', 0)}")
    for task in _next_candidates(board, 3):
        print(f"[NEXT] {task['id']} :: {task['title']}")
    return 0


def long_tasks_status(root: Path) -> int:
    board = _load_board(root)
    print(f"[STATE] schema={board.get('schema')} iteration={board.get('iteration', 0)} updated_at={board.get('updated_at', '')}")
    for key, value in sorted(_task_counts(board).items()):
        print(f"[STATE] {key}={value}")
    for task in _next_candidates(board, 5):
        print(f"[NEXT] {task['id']} priority={task.get('priority')} status={task.get('status')} :: {task['title']}")
    return 0


def record_long_task_iteration(root: Path) -> int:
    board = _load_board(root)
    _merge_seed_tasks(board, (*IMPLEMENTATION_TASKS, *RESEARCH_TASKS))
    print("[DATASET] running dataSet ingest gate before iteration selection")
    dataset_gate = _run_suite_stage(root, "diag.dataset.ingest", 0)
    dataset_ok = dataset_gate.get("exit_code") == 0 and not dataset_gate.get("timed_out")
    gate_tag = "OK" if dataset_ok else "ERROR"
    print(f"[{gate_tag}] dataSet ingest gate exit={dataset_gate.get("exit_code")} time_ms={dataset_gate.get("duration_ms")}")
    current = int(board.get("iteration", 0)) + 1
    selected = _next_candidates(board)
    for task in board.get("tasks", []):
        if task.get("id") in {item["id"] for item in selected} and task.get("status") == "backlog":
            task["status"] = "active"
            task["last_selected_at"] = _now()
    record = {
        "iteration": current,
        "created_at": _now(),
        "selected_task_ids": [task["id"] for task in selected],
        "dataset_gate": dataset_gate,
        "required_evidence": [
            "dataSet ingest report / knowledge-particle cache evidence",
            "changed file list or research artifact path",
            "build/diagnostic command result or explicit blocker",
            "next action for each active task",
        ],
    }
    board["iteration"] = current
    board.setdefault("iterations", []).append(record)
    _save_board(root, board)

    _ensure_dirs(root)
    path = root / ITERATIONS_DIR / f"iteration-{current:04d}.md"
    lines = [
        f"# Long Task Iteration {current:04d}",
        "",
        f"Created: `{record['created_at']}`",
        "",
        "## dataSet gate",
        "",
        "- Action: `diag.dataset.ingest`",
        f"- Exit code: `{dataset_gate.get("exit_code")}`",
        f"- Timed out: `{dataset_gate.get("timed_out")}`",
        f"- Duration: `{dataset_gate.get("duration_ms")} ms`",
        "- Artifacts:",
        *[f"  - `{item.get("kind", "")}` — `{item.get("path", "")}`" for item in (dataset_gate.get("artifacts") or [])],
        "",
        "## Selected tasks",
        "",
    ]
    for task in selected:
        lines.extend([
            f"### `{task['id']}` — {task['title']}",
            "",
            f"- Kind: `{task['kind']}`",
            f"- Domain: `{task['domain']}`",
            f"- Priority: `{task.get('priority', 0)}`",
            "- Acceptance:",
        ])
        for item in task.get("acceptance", []):
            lines.append(f"  - {item}")
        lines.extend(["- Next actions:"])
        for item in task.get("next_actions", []):
            lines.append(f"  - {item}")
        lines.append("")
    lines.extend([
        "## Iteration result",
        "",
        "- Changed files:",
        "- Diagnostics/build evidence:",
        "- Research evidence:",
        "- Blockers:",
        "- Next iteration decision:",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Recorded long-task iteration: {path}")
    for task in selected:
        print(f"[NEXT] {task['id']} :: {task['title']}")
    return 0



def _suite_json_payload(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _run_suite_stage(root: Path, action_id: str, timeout_sec: int) -> dict[str, Any]:
    cmd = [sys.executable, "tools/scripts/takesome.py", "suite", "--json", "-sudo", "--run", action_id]
    started = time.perf_counter()
    started_at = _now()
    stdout_parts: list[str] = []
    stderr = ""
    timed_out = False
    exit_code = 0
    last_heartbeat = 0.0
    heartbeat_path = root / ".takesome" / "dataSet" / "index" / "ingest-pipeline" / "heartbeat.json"
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        deadline = None if timeout_sec <= 0 else time.monotonic() + timeout_sec
        while True:
            line = proc.stdout.readline()
            if line:
                stdout_parts.append(line)
                if sum(len(part) for part in stdout_parts) > 240000:
                    joined_tail = "".join(stdout_parts)[-180000:]
                    stdout_parts = [joined_tail]
                print(line, end="", flush=True)
            elif proc.poll() is not None:
                break
            else:
                now = time.monotonic()
                if action_id == "diag.dataset.ingest" and now - last_heartbeat >= 10.0 and heartbeat_path.exists():
                    try:
                        heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
                        print(
                            f"[ALIVE] dataSet ingest heartbeat stage={heartbeat.get('stage')} elapsed={heartbeat.get('elapsed_sec')}s",
                            flush=True,
                        )
                    except Exception:
                        pass
                    last_heartbeat = now
                if deadline is not None and now > deadline:
                    timed_out = True
                    proc.kill()
                    break
                time.sleep(0.1)
        if not timed_out:
            exit_code = int(proc.wait())
        else:
            exit_code = 124
            try:
                remaining = proc.communicate(timeout=2)[0] or ""
                if remaining:
                    stdout_parts.append(remaining)
                    print(remaining, end="", flush=True)
            except Exception:
                pass
    except FileNotFoundError as exc:
        exit_code = 127
        stderr = str(exc)
    duration_ms = int(round((time.perf_counter() - started) * 1000.0))
    stdout = "".join(stdout_parts)
    payload = _suite_json_payload(stdout)
    artifacts = []
    diagnostics = []
    if isinstance(payload, dict):
        artifacts = payload.get("artifacts") or []
        diagnostics = payload.get("diagnostics") or []
        result = payload.get("result") or {}
        if isinstance(result, dict) and "exit_code" in result:
            try:
                exit_code = int(result.get("exit_code"))
            except Exception:
                pass
    return {
        "action": action_id,
        "command": cmd,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout_tail": stdout[-2500:],
        "stderr_tail": stderr[-2500:],
        "artifacts": artifacts,
        "diagnostics": diagnostics,
        "payload_status": payload.get("status") if isinstance(payload, dict) else None,
    }

def _latest_iteration_path(root: Path) -> Path | None:
    path = root / ITERATIONS_DIR
    if not path.exists():
        return None
    entries = sorted(path.glob("iteration-*.md"))
    return entries[-1] if entries else None


def _write_verification_report(root: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    _ensure_dirs(root)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = root / REPORTS_DIR / f"verification-{stamp}.json"
    md_path = root / REPORTS_DIR / f"verification-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# Long Task Verification Report — {stamp}",
        "",
        f"- Status: `{report['status']}`",
        f"- Started: `{report['started_at']}`",
        f"- Finished: `{report['finished_at']}`",
        f"- Duration: `{report['duration_ms']} ms`",
        f"- Required stages passed: `{report['required_passed']}`",
        f"- Latest iteration: `{report.get('latest_iteration') or ''}`",
        "",
        "## Stage timings",
        "",
        "| Stage | Action | Kind | Required | Exit | Timeout | Time ms |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for stage in report["stages"]:
        lines.append(
            f"| `{stage['id']}` | `{stage['action']}` | `{stage['kind']}` | `{stage['required']}` | `{stage['result']['exit_code']}` | `{stage['result']['timed_out']}` | `{stage['result']['duration_ms']}` |"
        )
    lines.extend(["", "## Artifacts", ""])
    for stage in report["stages"]:
        arts = stage["result"].get("artifacts") or []
        if not arts:
            continue
        lines.append(f"### `{stage['id']}`")
        for art in arts:
            lines.append(f"- `{art.get('kind', '')}` — `{art.get('path', '')}`")
        lines.append("")
    lines.extend(["", "## Diagnostics / tails", ""])
    for stage in report["stages"]:
        result = stage["result"]
        if result.get("diagnostics"):
            lines.append(f"### `{stage['id']}` diagnostics")
            lines.append("```json")
            lines.append(json.dumps(result.get("diagnostics"), ensure_ascii=False, indent=2)[-4000:])
            lines.append("```")
        if result.get("stderr_tail"):
            lines.append(f"### `{stage['id']}` stderr tail")
            lines.append("```text")
            lines.append(str(result.get("stderr_tail"))[-2000:])
            lines.append("```")
    lines.extend(["", "## GitHub pin gate", ""])
    gate = report.get("github_gate", {})
    for key, value in gate.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def _git_status(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"is_repo": False, "ok": False, "message": "not a git repository"}
    proc = subprocess.run(["git", "status", "--short"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    remote = subprocess.run(["git", "remote", "-v"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    return {
        "is_repo": True,
        "ok": proc.returncode == 0,
        "status_short": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "remotes": remote.stdout.strip(),
    }


def run_long_task_verification(root: Path) -> int:
    board = _load_board(root)
    latest_iteration = _latest_iteration_path(root)
    started_at = _now()
    started = time.perf_counter()
    stages: list[dict[str, Any]] = []
    required_passed = True
    print("[INFO] Long-task verification pipeline started.")
    for stage in VERIFY_PIPELINE:
        print(f"[STATE] stage={stage['id']} action={stage['action']} kind={stage['kind']} required={stage['required']}")
        result = _run_suite_stage(root, str(stage["action"]), int(stage.get("timeout_sec", 0)))
        passed = result["exit_code"] == 0 and not result["timed_out"]
        if bool(stage.get("required", False)) and not passed:
            required_passed = False
        stages.append({**stage, "passed": passed, "result": result})
        print(f"[{'OK' if passed else 'WARN'}] {stage['id']} exit={result['exit_code']} time_ms={result['duration_ms']}")
    duration_ms = int(round((time.perf_counter() - started) * 1000.0))
    git_state = _git_status(root)
    status = "success" if required_passed else "failed"
    report = {
        "schema": "northstar.suite.long_task_verification.v1",
        "status": status,
        "started_at": started_at,
        "finished_at": _now(),
        "duration_ms": duration_ms,
        "required_passed": required_passed,
        "latest_iteration": str(latest_iteration.relative_to(root)) if latest_iteration else None,
        "stages": stages,
        "github_gate": {
            "verification_success": required_passed,
            "git_repository": bool(git_state.get("is_repo")),
            "push_enabled_env": os.environ.get("NORTHSTAR_LONG_TASK_GITHUB_PUSH", "") in {"1", "true", "yes", "on"},
            "git_message": git_state.get("message", ""),
        },
    }
    json_path, md_path = _write_verification_report(root, report)
    board["last_verification"] = {
        "status": status,
        "required_passed": required_passed,
        "duration_ms": duration_ms,
        "json_path": str(json_path.relative_to(root)),
        "md_path": str(md_path.relative_to(root)),
        "finished_at": report["finished_at"],
    }
    _save_board(root, board)
    print(f"[OK] Verification JSON: {json_path}")
    print(f"[OK] Verification MD: {md_path}")
    print(f"[STATE] verification_status={status} duration_ms={duration_ms}")
    return 0 if required_passed else 1


def pin_long_task_success_to_github(root: Path) -> int:
    board = _load_board(root)
    verification = board.get("last_verification") or {}
    git_state = _git_status(root)
    if verification.get("status") != "success":
        print("[ERROR] Refusing GitHub pin: last long-task verification is not successful.")
        print(f"[STATE] last_verification={verification}")
        return 2
    if not git_state.get("is_repo"):
        print("[ERROR] Refusing GitHub pin: workspace is not a git repository.")
        return 2
    if not git_state.get("ok"):
        print(f"[ERROR] Refusing GitHub pin: git status failed: {git_state.get('stderr', '')}")
        return 2
    if os.environ.get("NORTHSTAR_LONG_TASK_GITHUB_PUSH", "").strip().lower() not in {"1", "true", "yes", "on"}:
        print("[WARN] GitHub pin is armed but not executed. Set NORTHSTAR_LONG_TASK_GITHUB_PUSH=1 to allow commit/push.")
        print(f"[STATE] changed_files={git_state.get('status_short', '')}")
        print("[STATE] command=git add . && git commit -m \"North Star long-task verification\" && git push")
        return 0
    changed = str(git_state.get("status_short", "")).strip()
    if not changed:
        print("[OK] Nothing to commit; successful verification already clean.")
        return 0
    cmds = [
        ["git", "add", "."],
        ["git", "commit", "-m", "North Star long-task verification"],
        ["git", "push"],
    ]
    for cmd in cmds:
        started = time.perf_counter()
        proc = subprocess.run(cmd, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
        elapsed = int(round((time.perf_counter() - started) * 1000.0))
        print(f"[STATE] {' '.join(cmd)} exit={proc.returncode} time_ms={elapsed}")
        if proc.stdout:
            print(proc.stdout[-2000:])
        if proc.returncode != 0:
            print("[ERROR] GitHub pin failed.")
            return proc.returncode
    print("[OK] Successful long-task verification pinned to GitHub.")
    return 0 if dataset_ok else 1


def seed_engine_research_backlog(root: Path) -> int:
    board = _load_board(root)
    added = _merge_seed_tasks(board, RESEARCH_TASKS)
    _save_board(root, board)
    _write_doctrine(root, board)
    print(f"[OK] Research backlog seeded: added={added}")
    for task in [task for task in board.get("tasks", []) if task.get("kind") == "research"]:
        print(f"[STATE] {task['id']} priority={task.get('priority')} status={task.get('status')} :: {task['title']}")
    return 0
