from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_dp = __import__("noesis.dashboard.providers", fromlist=["_"])
worker_payload = getattr(_dp, "worker_payload")
paths_payload = getattr(_dp, "paths_payload")
load_suite_actions = getattr(_dp, "load_suite_actions")
operator_tasks_payload = getattr(_dp, "operator_tasks_payload")

from .edit_model import EditField, edit_model


DASHBOARD_TITLE = "NOESIS Run Dashboard"
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8798


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: str
    scope: str
    readiness_kind: str
    reason: str
    failed_phase: str
    changed_files: int
    tests_passed: int
    tests_failed: int
    audit_issues: int
    previous_rejections: int
    whole_repository_ready: bool
    created_utc: str
    completed_utc: str
    duration_ms: int | None
    artifact_checksum_count: int
    run_dir: str

    def to_json(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "status": self.status,
            "scope": self.scope,
            "readinessKind": self.readiness_kind,
            "reason": self.reason,
            "failedPhase": self.failed_phase,
            "changedFiles": self.changed_files,
            "testsPassed": self.tests_passed,
            "testsFailed": self.tests_failed,
            "auditIssues": self.audit_issues,
            "previousRejections": self.previous_rejections,
            "wholeRepositoryReady": self.whole_repository_ready,
            "createdUtc": self.created_utc,
            "completedUtc": self.completed_utc,
            "durationMs": self.duration_ms,
            "artifactChecksumCount": self.artifact_checksum_count,
            "runDir": self.run_dir,
            "artifacts": artifact_links(Path(self.run_dir), self.run_id),
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        return {}
    return {}


def read_text(path: Path, *, limit: int = 40_000) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:limit] + "\n... <truncated>" if len(text) > limit else text
    except Exception:
        return ""


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


def artifact_links(run_dir: Path, run_id: str) -> list[dict[str, str]]:
    candidates = [
        "merge-readiness.json",
        "validation-report.json",
        "validation-report.md",
        "full-repo-report.json",
        "audit-report.json",
        "test-report.json",
        "build-report.json",
        "forbidden-files-report.json",
        "checksums.json",
        "proof-of-work.log",
        "changed-files.json",
        "manifest.json",
    ]
    artifacts: list[dict[str, str]] = []
    for name in candidates:
        path = run_dir / name
        if path.exists():
            artifacts.append({"name": name, "path": str(path), "url": f"/api/runs/{run_id}/artifacts/{name}"})
    return artifacts


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



def print_table(runs: list[RunSummary]) -> None:
    if not runs:
        print("No NOESIS runs found.")
        return
    print(f"{'RUN':32} {'STATUS':12} {'SCOPE':10} {'PHASE':18} {'CHG':>4} {'T':>3}/{ 'F':<3} REASON")
    for run in runs:
        print(f"{run.run_id:32} {run.status:12} {run.scope:10} {run.failed_phase[:18]:18} {run.changed_files:4d} {run.tests_passed:3d}/{run.tests_failed:<3d} {run.reason[:70]}")


def _coerce_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(item.get("runId") or ""),
        "status": str(item.get("status") or ""),
        "scope": str(item.get("scope") or ""),
        "readiness_kind": str(item.get("readinessKind") or ""),
        "reason": str(item.get("reason") or ""),
        "failed_phase": str(item.get("failedPhase") or ""),
        "changed_files": int(item.get("changedFiles") or 0),
        "tests_passed": int(item.get("testsPassed") or 0),
        "tests_failed": int(item.get("testsFailed") or 0),
        "audit_issues": int(item.get("auditIssues") or 0),
        "previous_rejections": int(item.get("previousRejections") or 0),
        "whole_repository_ready": bool(item.get("wholeRepositoryReady", False)),
        "created_utc": str(item.get("createdUtc") or ""),
        "completed_utc": str(item.get("completedUtc") or ""),
        "duration_ms": item.get("durationMs") if isinstance(item.get("durationMs"), int) else None,
        "artifact_checksum_count": int(item.get("artifactChecksumCount") or 0),
        "run_dir": str(item.get("runDir") or ""),
    }


def command_list(root: Path, args: argparse.Namespace) -> int:
    payload = write_index(root, html_enabled=not args.no_html)
    runs = [RunSummary(**_coerce_summary(item)) for item in payload.get("recent", [])]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_table(runs[-args.limit :])
        print(f"\nIndex: {root / '.noesis' / 'index' / 'runs.json'}")
        if not args.no_html:
            print(f"HTML:  {root / '.noesis' / 'dashboard' / 'index.html'}")
    return 0


def run_payload(root: Path, run_id: str) -> dict[str, Any] | None:
    run_dir = root / ".noesis" / "runs" / run_id
    if not run_dir.exists():
        return None
    return {
        "runId": run_id,
        "runDir": str(run_dir),
        "readiness": read_json(run_dir / "merge-readiness.json"),
        "report": read_json(run_dir / "validation-report.json"),
        "fullRepoReport": read_json(run_dir / "full-repo-report.json"),
        "proofLog": read_text(run_dir / "proof-of-work.log"),
        "artifacts": artifact_links(run_dir, run_id),
    }


def patch_candidates(run_dir: Path) -> list[Path]:
    names = ["repo.patch", "changes.patch", "diff.patch"]
    found: list[Path] = []
    for name in names:
        candidate = run_dir / name
        if candidate.is_file():
            found.append(candidate)
    for candidate in sorted(run_dir.glob("*.patch")):
        if candidate not in found:
            found.append(candidate)
    return found


def patch_stats(patch_text: str) -> dict[str, Any]:
    files: set[str] = set()
    additions = 0
    deletions = 0
    hunks = 0
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                name = parts[3][2:] if parts[3].startswith("b/") else parts[3]
                files.add(name)
        elif line.startswith("@@"):
            hunks += 1
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return {"files": sorted(files), "fileCount": len(files), "additions": additions, "deletions": deletions, "hunks": hunks}


def patch_commands(run_id: str) -> dict[str, str]:
    return {
        "inspect": f"python -m noesis runs patch {run_id} --json",
        "show": f"python -m noesis runs patch {run_id} --show",
        "dryRun": f"python -m noesis runs patch {run_id} --check",
        "apply": f"python -m noesis runs patch {run_id} --apply",
    }


def patch_payload(root: Path, run_id: str, *, limit: int = 120000) -> dict[str, Any]:
    run_dir = root / ".noesis" / "runs" / run_id
    if not run_dir.exists():
        return {"ok": False, "error": "run_not_found", "runId": run_id}
    candidates = patch_candidates(run_dir)
    if not candidates:
        return {"ok": False, "error": "patch_not_found", "runId": run_id, "runDir": str(run_dir), "commands": patch_commands(run_id)}
    path = candidates[0]
    preview = read_text(path, limit=limit)
    return {
        "ok": True,
        "schema": "noesis.dashboard.patch.v1",
        "runId": run_id,
        "runDir": str(run_dir),
        "patchName": path.name,
        "patchPath": str(path),
        "stats": patch_stats(preview),
        "preview": preview,
        "commands": patch_commands(run_id),
    }


def command_patch(root: Path, args: argparse.Namespace) -> int:
    payload = patch_payload(root, args.run_id, limit=args.limit)
    if args.show:
        if not payload.get("ok"):
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
            return 2
        print(str(payload.get("preview") or ""))
        return 0
    if args.check or args.apply:
        mode = "apply" if args.apply else "check"
        payload["requestedMode"] = mode
        payload["message"] = "Use the Suite patch tool or git apply locally after reviewing the preview. Browser dashboard never mutates the repo directly."
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 2


def command_show(root: Path, args: argparse.Namespace) -> int:
    payload = run_payload(root, args.run_id)
    if payload is None:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_failures(root: Path, args: argparse.Namespace) -> int:
    payload = write_index(root, html_enabled=not args.no_html)
    failures = payload.get("failures", [])[-args.limit :]
    if args.json:
        print(json.dumps({"schema": "noesis.runs.failures.v1", "generatedUtc": utc_now(), "failures": failures}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_table([RunSummary(**_coerce_summary(item)) for item in failures])
    return 0


def command_serve(root: Path, args: argparse.Namespace) -> int:
    from .webapp import serve_dashboard

    return serve_dashboard(root, host=args.host, port=args.port, open_browser=args.open)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m noesis runs", description="Inspect NOESIS verification runs and serve dashboard UI.")
    sub = parser.add_subparsers(dest="command")
    list_parser = sub.add_parser("list", help="List recent runs and write .noesis/index/runs.json")
    list_parser.add_argument("--json", action="store_true")
    list_parser.add_argument("--limit", type=int, default=25)
    list_parser.add_argument("--no-html", action="store_true")
    show_parser = sub.add_parser("show", help="Show one run report")
    show_parser.add_argument("run_id")
    failures_parser = sub.add_parser("failures", help="Show recent rejected/non-ready runs")
    failures_parser.add_argument("--json", action="store_true")
    failures_parser.add_argument("--limit", type=int, default=25)
    failures_parser.add_argument("--no-html", action="store_true")
    index_parser = sub.add_parser("index", help="Regenerate dashboard index files")
    index_parser.add_argument("--json", action="store_true")
    index_parser.add_argument("--no-html", action="store_true")
    serve_parser = sub.add_parser("serve", help="Serve the dashboard on localhost")
    serve_parser.add_argument("--host", default=DASHBOARD_HOST)
    serve_parser.add_argument("--port", type=int, default=DASHBOARD_PORT)
    serve_parser.add_argument("--open", action="store_true", help="Open the dashboard in the default browser")
    patch_parser = sub.add_parser("patch", help="Inspect a run patch artifact and print safe apply commands")
    patch_parser.add_argument("run_id")
    patch_parser.add_argument("--json", action="store_true")
    patch_parser.add_argument("--show", action="store_true", help="Print patch text")
    patch_parser.add_argument("--check", action="store_true", help="Print dry-run intent and patch metadata")
    patch_parser.add_argument("--apply", action="store_true", help="Print explicit apply intent and patch metadata")
    patch_parser.add_argument("--limit", type=int, default=120000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd()
    command = args.command or "list"
    if command == "list":
        return command_list(root, args)
    if command == "show":
        return command_show(root, args)
    if command == "failures":
        return command_failures(root, args)
    if command == "index":
        payload = write_index(root, html_enabled=not args.no_html)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(root / ".noesis" / "index" / "runs.json")
            if not args.no_html:
                print(root / ".noesis" / "dashboard" / "index.html")
        return 0
    if command == "serve":
        return command_serve(root, args)
    if command == "patch":
        return command_patch(root, args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
