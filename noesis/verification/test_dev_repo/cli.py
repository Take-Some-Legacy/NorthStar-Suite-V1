from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from noesis.verification.test_dev_repo.common import (
    CommandResult,
    Phase,
    ProofLog,
    default_run_id,
    ensure_parent,
    relpath,
    run_cmd,
    sha256_file,
    utc_now,
    write_json,
    write_text,
)

from noesis.verification.test_dev_repo.audit import audit_structure
from noesis.verification.test_dev_repo.changeset import apply_current_changes
from noesis.verification.test_dev_repo.forbidden_files import scan_forbidden_files, scan_secret_content
from noesis.verification.test_dev_repo.workspace import create_worktree
from noesis.verification.test_dev_repo.runtime_boundaries import scan_forbidden_runtime_roots
from noesis.verification.test_dev_repo.full_repo import run_full_repo_gate

from noesis.verification.test_dev_repo.contract import (
    readiness_kind_for_scope,
    scope_description,
    scope_warning,
)

FINAL_OK = "merge_ready"
FINAL_REJECTED = "rejected"
STATE_CREATED = "created"
STATE_PREPARED = "prepared"
STATE_CHANGES_APPLIED = "changes_applied"
STATE_AUDIT_RUNNING = "audit_running"
STATE_AUDIT_FAILED = "audit_failed"
STATE_TESTS_RUNNING = "tests_running"
STATE_TESTS_FAILED = "tests_failed"
STATE_BUILD_RUNNING = "build_running"
STATE_BUILD_FAILED = "build_failed"
STATE_VERIFIED = "verified"

def run_suite_action(repo: Path, action_id: str, timeout: int = 240) -> CommandResult:
    return run_cmd([sys.executable, "-m", "noesis", "suite", "--run", action_id, "--json"], cwd=repo, timeout=timeout)


def run_tests(repo: Path, proof: ProofLog) -> Phase:
    test_label = "suite.actions.validate+tools.validate+" + "noesis.dashboard.verify"
    proof.emit("TEST", command=test_label, status="running")
    commands = [
        run_suite_action(repo, "suite.actions.validate", timeout=240),
        run_suite_action(repo, "tools.validate", timeout=300),
        run_suite_action(repo, "noesis.dashboard.verify", timeout=240),
    ]
    failed = [c for c in commands if not c.ok]
    status = "ok" if not failed else "failed"
    proof.emit("TEST", command=test_label, status=status, passed=len(commands) - len(failed), failed=len(failed))
    return Phase(
        name="tests",
        status=status,
        reason="; ".join(" ".join(c.command) for c in failed),
        data={"commands": [c.to_json() for c in commands], "passed": len(commands) - len(failed), "failed": len(failed)},
    )


def changed_python_files(change_data: dict[str, Any], repo: Path | None = None) -> list[str]:
    out: list[str] = []
    for item in change_data.get("applied", []):
        path = str(item.get("path") or "")
        op = str(item.get("operation") or "")
        if op != "delete" and path.endswith(".py"):
            out.append(path)
    if not out and repo is not None and not (repo / ".git").exists():
        roots = [repo / "noesis"]
        for root in roots:
            if root.exists():
                out.extend(p.relative_to(repo).as_posix() for p in root.rglob("*.py"))
    return sorted(dict.fromkeys(out))


def run_build(repo: Path, change_data: dict[str, Any], proof: ProofLog) -> Phase:
    py_files = changed_python_files(change_data, repo)
    proof.emit("BUILD", command="py_compile_changed_python", status="running", files=len(py_files))
    commands: list[CommandResult] = []
    if py_files:
        commands.append(run_cmd([sys.executable, "-m", "py_compile", *py_files], cwd=repo, timeout=180))
    else:
        commands.append(CommandResult(command=["build", "no-python-files"], cwd=str(repo), exit_code=0, duration_ms=0, stdout_tail="no changed python files", stderr_tail=""))
    failed = [c for c in commands if not c.ok]
    status = "ok" if not failed else "failed"
    proof.emit("BUILD", command="py_compile_changed_python", status=status, duration_ms=sum(c.duration_ms for c in commands))
    return Phase(
        name="build",
        status=status,
        reason="; ".join(" ".join(c.command) for c in failed),
        data={"commands": [c.to_json() for c in commands], "compiledPythonFiles": py_files},
    )


def collect_checksums(paths: Iterable[Path], *, root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        if path.exists() and path.is_file():
            result[relpath(root, path)] = sha256_file(path)
    return result


def verify_artifacts(run_dir: Path, repo: Path, proof: ProofLog) -> Phase:
    required = [
        run_dir / "manifest.json",
        run_dir / "audit-report.json",
        run_dir / "test-report.json",
        run_dir / "build-report.json",
        run_dir / "changed-files.json",
        run_dir / "proof-of-work.log",
    ]
    missing = [p.as_posix() for p in required if not p.exists()]
    checksums = collect_checksums(required, root=run_dir.parent.parent)
    write_json(run_dir / "checksums.json", checksums, proof, kind="checksums")
    status = "ok" if not missing else "failed"
    proof.emit("VERIFY", kind="artifact-checksums", status=status, files=len(checksums), missing=len(missing))
    return Phase(name="verify", status=status, reason="missing artifacts" if missing else "", data={"missing": missing, "checksums": checksums})


def manifest_for(run_id: str, source_root: Path, run_dir: Path, workspace_repo: Path, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema": "noesis.test_dev_repo.manifest.v1",
        "runId": run_id,
        "utc": utc_now(),
        "sourceRoot": str(source_root),
        "runDirectory": str(run_dir),
        "workspace": str(workspace_repo),
        "workflow": "testDevRepo-oriented",
        "scope": args.scope,
        "readinessKind": readiness_kind_for_scope(args.scope),
        "wholeRepositoryReadyTarget": args.scope == "full-repo",
        "finalStatePolicy": {
            "mergeReadyRequiresVerified": True,
            "verifiedRequires": ["audit.ok", "tests.ok", "build.ok", "verify.ok"],
            "patchOnlyReadyForbidden": True,
        },
        "options": {"applyCurrentDiff": bool(args.apply_current_diff), "scope": args.scope},
    }


def _first_nonempty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _failed_command_text(phase: dict[str, Any]) -> str:
    chunks: list[str] = []
    for command in phase.get("commands", []):
        if isinstance(command, dict) and not command.get("ok", False):
            chunks.append(str(command.get("stderrTail") or ""))
            chunks.append(str(command.get("stdoutTail") or ""))
    return "\n".join(chunk for chunk in chunks if chunk)


def _extract_path_line(text: str) -> tuple[str, int | None]:
    file_match = re.search(r'File "([^"]+)", line (\d+)', text)
    if file_match:
        return file_match.group(1).replace("\\", "/"), int(file_match.group(2))
    colon_match = re.search(r'([^\s:\n]+\.[A-Za-z0-9_]+):(\d+):', text)
    if colon_match:
        return colon_match.group(1).replace("\\", "/"), int(colon_match.group(2))
    return "", None


def _short_failure_reason(phase_name: str, phase: dict[str, Any]) -> str:
    command_text = _failed_command_text(phase)
    syntax_match = re.search(r"SyntaxError:[^\n]+", command_text)
    if syntax_match:
        return syntax_match.group(0).strip()
    blocking = phase.get("blockingIssues")
    if isinstance(blocking, list) and blocking:
        return "; ".join(str(item) for item in blocking[:4])
    reason = str(phase.get("reason") or "").strip()
    if reason:
        return reason[:500]
    return f"{phase_name}_failed"


def summarize_rejection(run_id: str, report: dict[str, Any], *, fixed: bool) -> dict[str, Any]:
    phases = report.get("phases", {}) if isinstance(report, dict) else {}
    readiness = report.get("readiness", {}) if isinstance(report, dict) else {}
    failure_reason = str(readiness.get("reason") or report.get("reason") or "")
    failed_phase_name = failure_reason.removesuffix("_failed") if failure_reason.endswith("_failed") else ""
    failed_phase: dict[str, Any] = {}
    if failed_phase_name and isinstance(phases.get(failed_phase_name), dict):
        failed_phase = phases[failed_phase_name]
    else:
        for name, phase in phases.items():
            if isinstance(phase, dict) and phase.get("status") != "ok":
                failed_phase_name = str(name)
                failed_phase = phase
                break
    command_text = _failed_command_text(failed_phase)
    path, line = _extract_path_line(command_text)
    conflicts = failed_phase.get("conflicts") if isinstance(failed_phase, dict) else None
    if not path and isinstance(conflicts, list) and conflicts:
        first_conflict = conflicts[0] if isinstance(conflicts[0], dict) else {}
        path = str(first_conflict.get("path") or "")
        line_value = first_conflict.get("line")
        line = int(line_value) if isinstance(line_value, int) else None
    return {
        "runId": run_id,
        "phase": failed_phase_name or failure_reason or "unknown",
        "reason": _short_failure_reason(failed_phase_name or "unknown", failed_phase),
        "path": path,
        "line": line,
        "fixed": fixed,
    }


def collect_previous_rejections(noesis_root: Path, current_run_id: str, *, fixed: bool, limit: int = 20) -> list[dict[str, Any]]:
    runs_root = noesis_root / "runs"
    if not runs_root.exists():
        return []
    rejections: list[dict[str, Any]] = []
    for run_dir in sorted((p for p in runs_root.iterdir() if p.is_dir()), key=lambda p: p.name):
        if run_dir.name == current_run_id:
            continue
        report_path = run_dir / "validation-report.json"
        readiness_path = run_dir / "merge-readiness.json"
        try:
            if report_path.exists():
                report = json.loads(report_path.read_text(encoding="utf-8"))
            elif readiness_path.exists():
                report = {"readiness": json.loads(readiness_path.read_text(encoding="utf-8")), "phases": {}}
            else:
                continue
        except Exception:
            continue
        status = str(report.get("status") or report.get("readiness", {}).get("status") or "")
        if status != FINAL_REJECTED:
            continue
        rejections.append(summarize_rejection(run_dir.name, report, fixed=fixed))
    return rejections[-limit:]


def render_markdown(run_id: str, status: str, phases: dict[str, Phase], readiness: dict[str, Any]) -> str:
    lines = [
        f"# NOESIS testDevRepo validation — {run_id}",
        "",
        f"Final status: `{status}`",
        "",
        "## Contract",
        "",
        "NOESIS does not produce patches. NOESIS produces verified workspaces.",
        "",
        "```text",
        "merge_ready = audit.ok && tests.ok && build.ok && verify.ok",
        "```",
        "",
        "## Phases",
        "",
        "| Phase | Status | Reason |",
        "|---|---|---|",
    ]
    for name, phase in phases.items():
        lines.append(f"| {name} | {phase.status} | {phase.reason or '-'} |")
    lines.extend(["", "## Merge readiness", "", "```json", json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def verify_command(source_root: Path, args: argparse.Namespace) -> int:
    run_id = args.run_id or default_run_id()
    noesis_root = source_root / ".noesis"
    run_dir = noesis_root / "runs" / run_id
    workspace_repo = noesis_root / "workspaces" / f"testDevRepo-{run_id}" / "repo"
    run_dir.mkdir(parents=True, exist_ok=True)
    proof = ProofLog(run_id, run_dir / "proof-of-work.log")
    proof.emit("RUN", phase="start", task="test-dev-repo-verify", scope=args.scope)

    phases: dict[str, Phase] = {}
    manifest = manifest_for(run_id, source_root, run_dir, workspace_repo, args)
    write_json(run_dir / "manifest.json", manifest, proof, kind="manifest")

    worktree_result = create_worktree(source_root, workspace_repo, proof)
    phases["workspace"] = Phase("workspace", "ok" if worktree_result.ok else "failed", "" if worktree_result.ok else "git worktree add failed", {"command": worktree_result.to_json()})
    if not worktree_result.ok:
        return finalize(run_id, run_dir, workspace_repo, phases, proof, status=FINAL_REJECTED, reason="workspace_create_failed", scope=args.scope)

    change_data = apply_current_changes(source_root, workspace_repo, proof) if args.apply_current_diff else {"mode": "none", "applied": [], "changedFiles": 0}
    phases["changes"] = Phase("changes", "ok", data=change_data)
    write_json(run_dir / "changed-files.json", change_data, proof, kind="changed-files")

    phases["runtime-boundaries"] = scan_forbidden_runtime_roots(workspace_repo, proof)
    write_json(run_dir / "runtime-boundaries-report.json", phases["runtime-boundaries"].to_json(), proof, kind="runtime-boundaries-report")
    if not phases["runtime-boundaries"].ok:
        return finalize(run_id, run_dir, workspace_repo, phases, proof, status=FINAL_REJECTED, reason="forbidden_runtime_roots_present", scope=args.scope)

    phases["forbidden"] = scan_forbidden_files(change_data, proof)
    write_json(run_dir / "forbidden-files-report.json", phases["forbidden"].to_json(), proof, kind="forbidden-files-report")
    if not phases["forbidden"].ok:
        return finalize(run_id, run_dir, workspace_repo, phases, proof, status=FINAL_REJECTED, reason="forbidden_files_detected", scope=args.scope)

    phases["audit"] = audit_structure(workspace_repo, proof)
    write_json(run_dir / "audit-report.json", phases["audit"].to_json(), proof, kind="audit-report")
    if not phases["audit"].ok:
        return finalize(run_id, run_dir, workspace_repo, phases, proof, status=FINAL_REJECTED, reason="audit_failed", scope=args.scope)

    phases["tests"] = run_tests(workspace_repo, proof)
    write_json(run_dir / "test-report.json", phases["tests"].to_json(), proof, kind="test-report")
    if not phases["tests"].ok:
        return finalize(run_id, run_dir, workspace_repo, phases, proof, status=FINAL_REJECTED, reason="tests_failed", scope=args.scope)

    phases["build"] = run_build(workspace_repo, change_data, proof)
    write_json(run_dir / "build-report.json", phases["build"].to_json(), proof, kind="build-report")
    if not phases["build"].ok:
        return finalize(run_id, run_dir, workspace_repo, phases, proof, status=FINAL_REJECTED, reason="build_failed", scope=args.scope)

    phases["verify"] = verify_artifacts(run_dir, workspace_repo, proof)
    if not phases["verify"].ok:
        return finalize(run_id, run_dir, workspace_repo, phases, proof, status=FINAL_REJECTED, reason="verify_failed", scope=args.scope)

    if args.scope == "full-repo":
        phases["full-repo"] = run_full_repo_gate(workspace_repo, run_dir, proof)
        return finalize(
            run_id,
            run_dir,
            workspace_repo,
            phases,
            proof,
            status=FINAL_REJECTED,
            reason="full_repo_gate_skeleton_not_enforcement_ready",
            scope=args.scope,
        )
    proof.emit("MARK", status=FINAL_OK)
    return finalize(run_id, run_dir, workspace_repo, phases, proof, status=FINAL_OK, reason="", scope=args.scope)


def finalize(run_id: str, run_dir: Path, workspace_repo: Path, phases: dict[str, Phase], proof: ProofLog, *, status: str, reason: str, scope: str = "noesis-core") -> int:
    full_repo_phase = phases.get("full-repo")
    full_repo_data = full_repo_phase.data if full_repo_phase else {}
    checks = {
        "workspaceCreated": phases.get("workspace", Phase("workspace")).ok,
        "changesApplied": phases.get("changes", Phase("changes")).ok,
        "auditPassed": phases.get("audit", Phase("audit")).ok,
        "testsPassed": phases.get("tests", Phase("tests")).ok,
        "buildPassed": phases.get("build", Phase("build")).ok,
        "artifactsVerified": phases.get("verify", Phase("verify")).ok,
        "fullRepoGate": bool(full_repo_phase and full_repo_phase.ok),
        "fullRepoEnforcementReady": bool(full_repo_data.get("enforcementReady", False)),
    }
    verified = checks["auditPassed"] and checks["testsPassed"] and checks["buildPassed"] and checks["artifactsVerified"]
    if status == FINAL_OK and not verified:
        status = FINAL_REJECTED
        reason = reason or "merge_ready_invariant_failed"
    previous_rejections = collect_previous_rejections(run_dir.parent.parent, run_id, fixed=(status == FINAL_OK and verified))
    if previous_rejections:
        proof.emit("HISTORY", kind="previous-rejections", count=len(previous_rejections), fixed=(status == FINAL_OK and verified))
    readiness = {
        "schema": "noesis.merge_readiness.v2",
        "runId": run_id,
        "workspace": str(workspace_repo),
        "status": status,
        "scope": scope,
        "readinessKind": readiness_kind_for_scope(scope),
        "wholeRepositoryReady": bool(status == FINAL_OK and verified and scope == "full-repo"),
        "scopeDescription": scope_description(scope),
        "scopeWarning": scope_warning(scope),
        "reason": reason,
        "checks": checks | {"verified": verified},
        "previousRejections": previous_rejections,
        "summary": {
            "changedFiles": phases.get("changes", Phase("changes")).data.get("changedFiles", 0),
            "testsPassed": phases.get("tests", Phase("tests")).data.get("passed", 0),
            "testsFailed": phases.get("tests", Phase("tests")).data.get("failed", 0),
            "auditIssues": len(phases.get("audit", Phase("audit")).data.get("blockingIssues", [])),
            "previousRejections": len(previous_rejections),
            "scope": scope,
            "readinessKind": readiness_kind_for_scope(scope),
            "wholeRepositoryReady": bool(status == FINAL_OK and verified and scope == "full-repo"),
            "fullRepoMode": full_repo_data.get("mode", "not-requested"),
            "fullRepoEnforcementReady": bool(full_repo_data.get("enforcementReady", False)),
            "fullRepoBlockingChecks": full_repo_data.get("blockingChecks", []),
        },
        "utc": utc_now(),
    }
    write_json(run_dir / "merge-readiness.json", readiness, proof, kind="merge-readiness")
    write_json(run_dir / "validation-report.json", {"runId": run_id, "status": status, "phases": {k: v.to_json() for k, v in phases.items()}, "readiness": readiness}, proof, kind="validation-report")
    write_text(run_dir / "validation-report.md", render_markdown(run_id, status, phases, readiness), proof, kind="validation-report-md")
    proof.emit("RUN", phase="done", status=status, reason=reason)
    print(json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status == FINAL_OK else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m noesis noesis-test-dev-repo", description="NOESIS verified testDevRepo workflow runner.")
    parser.add_argument("mode", nargs="?", default="verify", choices=["verify"], help="Workflow mode.")
    parser.add_argument("--run-id", default="", help="Explicit run id. Defaults to noesis-YYYYMMDD-HHMMSSZ.")
    parser.add_argument("--scope", default="noesis-core", choices=["noesis-core", "full-repo"])
    parser.add_argument("--apply-current-diff", action="store_true", default=True, help="Copy current source worktree changes into the testDevRepo before validation.")
    parser.add_argument("--no-apply-current-diff", dest="apply_current_diff", action="store_false", help="Validate plain HEAD worktree without copying current changes.")
    return parser


def main(argv: list[str] | None = None, *, source_root: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = source_root or Path.cwd()
    if not (root / ".git").exists() and not (root / "suite.bat").exists():
        print(f"[ERROR] Not a Suite repository root: {root}")
        return 2
    if args.mode == "verify":
        return verify_command(root, args)
    parser.error("unknown mode")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
