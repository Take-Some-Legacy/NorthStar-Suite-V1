from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCAN_SCHEMA = "noesis.suite.task_scan.v1"
CONTROL_DIR = ".takesome"


def utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def intelligence_dir(root: Path) -> Path:
    return root / CONTROL_DIR / "intelligence"


def _run_git(root: Path, args: list[str], *, timeout: int = 10) -> str:
    try:
        completed = subprocess.run(["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except Exception:
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def _safe_read_tail(path: Path, *, chars: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-chars:]
    except OSError:
        return ""


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _count_recent_logs(root: Path) -> dict[str, Any]:
    paths: list[Path] = []
    for pattern in ("lastbuild.log", "lastbuild-all.log", "buildERR-*.log"):
        paths.extend(path for path in root.glob(pattern) if path.is_file())
    incidents = root / CONTROL_DIR / "incidents"
    if incidents.exists():
        paths.extend(path for path in incidents.glob("*/summary.md") if path.is_file())
    paths = sorted(set(paths), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return {"count": len(paths), "paths": [str(path.relative_to(root)) if path.is_relative_to(root) else str(path) for path in paths[:8]]}


def scan_task_context(root: Path, *, cycle: dict[str, Any] | None = None) -> dict[str, Any]:
    state_dir = intelligence_dir(root)
    git_status = _run_git(root, ["status", "--short"])
    branch = _run_git(root, ["branch", "--show-current"]).strip() or "unknown"
    recent_commits = _run_git(root, ["log", "--oneline", "-5"]).splitlines()
    status_lines = [line for line in git_status.splitlines() if line.strip()]
    changed_files = [line[3:].strip() if len(line) > 3 else line.strip() for line in status_lines]
    sensitive_runtime_changes = [path for path in changed_files if path.startswith(f"{CONTROL_DIR}/") and not path.startswith(f"{CONTROL_DIR}/config/")]
    inbox_text = _safe_read_tail(state_dir / "inbox.md", chars=4000).strip()
    operator_request = _safe_read_tail(state_dir / "operator-request.md", chars=4000).strip()
    operator_response = _safe_read_tail(state_dir / "operator-response.md", chars=4000).strip()
    assigned_task = _safe_json(state_dir / "assigned-task.json")
    presence = _safe_json(state_dir / "assistant-presence.json")
    loop_state = _safe_json(state_dir / "loop-state.json")
    logs = _count_recent_logs(root)

    cycle_obj = cycle if isinstance(cycle, dict) else {}
    self_checks = cycle_obj.get("self_checks") if isinstance(cycle_obj.get("self_checks"), list) else []
    failing_checks = [check for check in self_checks if isinstance(check, dict) and not check.get("ok")]
    recommendations = cycle_obj.get("recommendations") if isinstance(cycle_obj.get("recommendations"), list) else []

    return {
        "schema": SCAN_SCHEMA,
        "generated_utc": utc_iso(),
        "repo": {
            "branch": branch,
            "changed_file_count": len(changed_files),
            "changed_files_sample": changed_files[:30],
            "sensitive_runtime_changes": sensitive_runtime_changes[:20],
            "recent_commits": recent_commits[:5],
        },
        "intelligence": {
            "inbox_available": bool(inbox_text),
            "operator_request_available": bool(operator_request),
            "operator_response_available": bool(operator_response),
            "assigned_task_status": assigned_task.get("status"),
            "assigned_task_id": (assigned_task.get("task") or {}).get("id") if isinstance(assigned_task.get("task"), dict) else "",
            "presence_state": presence.get("state"),
            "last_loop_cycle": loop_state.get("cycle"),
        },
        "cycle": {
            "cycle": cycle_obj.get("cycle"),
            "self_check_count": len(self_checks),
            "failing_check_count": len(failing_checks),
            "failing_checks": [str(check.get("name") or "unnamed_check") for check in failing_checks[:10]],
            "recommendation_count": len(recommendations),
        },
        "logs": logs,
        "signals": {
            "dirty_worktree": bool(changed_files),
            "runtime_state_in_worktree": bool(sensitive_runtime_changes),
            "has_inbox": bool(inbox_text),
            "has_operator_response": bool(operator_response),
            "has_failing_checks": bool(failing_checks),
            "has_recommendations": bool(recommendations),
            "has_recent_logs": bool(logs.get("count")),
        },
    }


def write_task_scan(root: Path, scan: dict[str, Any]) -> dict[str, Any]:
    out = intelligence_dir(root) / "task-scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(scan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    return scan
