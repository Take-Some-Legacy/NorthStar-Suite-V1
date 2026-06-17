from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .runs_constants import DASHBOARD_HOST, DASHBOARD_PORT
from .runs_index import write_index
from .runs_io import utc_now
from .runs_model import RunSummary
from .runs_patch import patch_payload, run_payload


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
