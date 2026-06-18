from __future__ import annotations

from pathlib import Path
from typing import Any

from .runs_constants import DASHBOARD_TITLE
from .runs_io import parse_utc, read_json, utc_now
from .runs_model import RunSummary

_dp = __import__("noesis.dashboard.providers", fromlist=["_"])
worker_payload = getattr(_dp, "worker_payload")
paths_payload = getattr(_dp, "paths_payload")
cluster_payload = getattr(_dp, "cluster_payload")
operator_tasks_payload = getattr(_dp, "operator_tasks_payload")


def first_failed_phase(report: dict[str, Any]) -> str:
    phases = report.get("phases")
    if isinstance(phases, dict):
        for name, phase in phases.items():
            if isinstance(phase, dict) and phase.get("status") not in {"ok", "skipped", None}:
                return str(name)
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else report
    reason = str(readiness.get("reason") or report.get("reason") or "").strip()
    if reason.endswith("_failed"):
        return reason[: -len("_failed")]
    return reason


def checksum_count(run_dir: Path) -> int:
    checksums = read_json(run_dir / "checksums.json")
    return len(checksums) if isinstance(checksums, dict) else 0


def summarize_run(run_dir: Path) -> RunSummary | None:
    readiness = read_json(run_dir / "merge-readiness.json")
    report = read_json(run_dir / "validation-report.json")
    manifest = read_json(run_dir / "manifest.json")
    if not readiness and not report:
        return None
    if not readiness:
        maybe = report.get("readiness")
        readiness = maybe if isinstance(maybe, dict) else {}
    summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    created_utc = str(manifest.get("utc") or "")
    completed_utc = str(readiness.get("utc") or "")
    start = parse_utc(created_utc)
    end = parse_utc(completed_utc)
    duration_ms = int((end - start).total_seconds() * 1000) if start and end else None
    previous = readiness.get("previousRejections")
    previous_count = len(previous) if isinstance(previous, list) else int(summary.get("previousRejections") or 0)
    return RunSummary(
        run_id=str(readiness.get("runId") or report.get("runId") or run_dir.name),
        status=str(readiness.get("status") or report.get("status") or "unknown"),
        scope=str(readiness.get("scope") or manifest.get("scope") or summary.get("scope") or ""),
        readiness_kind=str(readiness.get("readinessKind") or summary.get("readinessKind") or ""),
        reason=str(readiness.get("reason") or ""),
        failed_phase=first_failed_phase(report or {"readiness": readiness}),
        changed_files=int(summary.get("changedFiles") or 0),
        tests_passed=int(summary.get("testsPassed") or 0),
        tests_failed=int(summary.get("testsFailed") or 0),
        audit_issues=int(summary.get("auditIssues") or 0),
        previous_rejections=previous_count,
        whole_repository_ready=bool(readiness.get("wholeRepositoryReady", False)),
        created_utc=created_utc,
        completed_utc=completed_utc,
        duration_ms=duration_ms,
        artifact_checksum_count=checksum_count(run_dir),
        run_dir=str(run_dir),
    )


def load_runs(root: Path) -> list[RunSummary]:
    runs_root = root / ".noesis" / "runs"
    if not runs_root.exists():
        return []
    runs = [summary for path in sorted(runs_root.iterdir()) if path.is_dir() for summary in [summarize_run(path)] if summary]
    return sorted(runs, key=lambda item: item.run_id)


def dashboard_insights(runs: list[RunSummary]) -> dict[str, Any]:
    if not runs:
        return {"headline": "No runs yet", "lastStatus": "unknown", "lastCore": None, "lastFull": None, "topReasons": [], "attention": []}
    failures = [run for run in runs if run.status != "merge_ready"]
    reasons: dict[str, int] = {}
    for run in failures:
        key = run.reason or run.failed_phase or "unknown"
        reasons[key] = reasons.get(key, 0) + 1
    last_core = next((run for run in reversed(runs) if run.scope == "noesis-core"), None)
    last_full = next((run for run in reversed(runs) if run.scope == "full-repo"), None)
    latest = runs[-1]
    attention: list[str] = []
    if last_core and last_core.status != "merge_ready":
        attention.append(f"Latest NOESIS-core run is {last_core.status}: {last_core.reason or last_core.failed_phase}")
    if last_full and not last_full.whole_repository_ready:
        attention.append(f"Full-repo is not globally ready: {last_full.reason or last_full.failed_phase}")
    if latest.tests_failed:
        attention.append(f"Latest run has {latest.tests_failed} failed test(s).")
    if latest.audit_issues:
        attention.append(f"Latest run has {latest.audit_issues} audit issue(s).")
    return {
        "headline": "Global ready" if any(run.whole_repository_ready for run in runs[-3:]) else "Focused readiness only",
        "lastStatus": latest.status,
        "lastCore": last_core.to_json() if last_core else None,
        "lastFull": last_full.to_json() if last_full else None,
        "topReasons": [{"reason": key, "count": value} for key, value in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))[:8]],
        "attention": attention,
    }


def index_payload(root: Path) -> dict[str, Any]:
    runs = load_runs(root)
    failures = [run for run in runs if run.status != "merge_ready"]
    merge_ready = [run for run in runs if run.status == "merge_ready"]
    full_runs = [run for run in runs if run.scope == "full-repo"]
    core_runs = [run for run in runs if run.scope == "noesis-core"]
    return {
        "schema": "noesis.runs.index.v3",
        "title": DASHBOARD_TITLE,
        "generatedUtc": utc_now(),
        "root": str(root),
        "webContract": {"schema": "noesis.web.v1", "surface": "dashboard.runs", "mode": "static-and-local-http"},
        "worker": worker_payload(root),
        "cluster": cluster_payload(root),
        "paths": paths_payload(root),
        "operatorTasks": operator_tasks_payload(root, runs),
        "counts": {
            "runs": len(runs),
            "mergeReady": len(merge_ready),
            "rejected": len([run for run in runs if run.status == "rejected"]),
            "failedOrOther": len([run for run in runs if run.status not in {"merge_ready", "rejected"}]),
            "wholeRepositoryReady": len([run for run in runs if run.whole_repository_ready]),
            "coreRuns": len(core_runs),
            "fullRuns": len(full_runs),
            "latestChangedFiles": runs[-1].changed_files if runs else 0,
        },
        "latest": runs[-1].to_json() if runs else None,
        "insights": dashboard_insights(runs),
        "recent": [run.to_json() for run in runs[-100:]],
        "failures": [run.to_json() for run in failures[-100:]],
    }


def write_index(root: Path, *, html_enabled: bool = True) -> dict[str, Any]:
    from .publisher import publish_dashboard

    return publish_dashboard(root, index_payload(root), html_enabled=html_enabled)
