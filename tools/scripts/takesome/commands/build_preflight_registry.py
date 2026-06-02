from __future__ import annotations

from pathlib import Path
from typing import Protocol
import json
import subprocess
import sys

from ..registry.registry_report import build_registry_report
from ..registry.suite_bridge_menu import write_bridge_menu_json


class _LogLike(Protocol):
    def emit(self, message: str) -> None: ...


def run_registry_build_preflight(repo_root: Path, output_dir: Path | None = None, log: _LogLike | None = None) -> int:
    """Validate Suite/tooling registries for build preflight.

    Policy:
      - registry ERROR blocks the build with exit code 2;
      - registry WARN remains visible but non-blocking.
    """

    output_dir = output_dir or repo_root / "NewEngine" / "neocore2" / "buildInfo" / "tools"
    report = build_registry_report(repo_root)
    report.write_all(output_dir)
    bridge_menu_path = write_bridge_menu_json(repo_root, output_path=output_dir / "SUITE_ACTIONS_BRIDGE_MENU.json")
    suite_cli_errors, suite_cli_warnings = _verify_suite_list_actions_cli(repo_root, output_dir, len(report.suite_registry.actions))
    bridge_errors, bridge_warnings = _verify_bridge_menu_json(bridge_menu_path, len(report.suite_registry.actions))

    tool_errors = sum(len(item.errors) for item in report.tool_registry.validation)
    tool_warnings = sum(len(item.warnings) for item in report.tool_registry.validation)
    suite_errors = sum(len(item.errors) for item in report.suite_registry.validation) + len(suite_cli_errors) + len(bridge_errors)
    suite_warnings = sum(len(item.warnings) for item in report.suite_registry.validation) + len(suite_cli_warnings) + len(bridge_warnings)
    preflight_ok = report.ok and not suite_cli_errors and not bridge_errors

    if log:
        log.emit("[INFO] Registry build preflight")
        log.emit(f"[INFO] Report: {output_dir / 'SUITE_TOOLING_REGISTRY.json'}")
        log.emit(f"[INFO] Bridge menu: {bridge_menu_path}")
        log.emit(f"[INFO] ToolRegistry errors={tool_errors} warnings={tool_warnings}")
        log.emit(f"[INFO] SuiteActionRegistry errors={suite_errors} warnings={suite_warnings}")
        for result in report.tool_registry.validation:
            for warning in result.warnings:
                log.emit(f"[WARN] tool {result.tool_id}: {warning}")
            for error in result.errors:
                log.emit(f"[ERROR] tool {result.tool_id}: {error}")
        for result in report.suite_registry.validation:
            for warning in result.warnings:
                log.emit(f"[WARN] suite action {result.action_id}: {warning}")
            for error in result.errors:
                log.emit(f"[ERROR] suite action {result.action_id}: {error}")
        for warning in suite_cli_warnings:
            log.emit(f"[WARN] suite --list-actions --json: {warning}")
        for error in suite_cli_errors:
            log.emit(f"[ERROR] suite --list-actions --json: {error}")
        for warning in bridge_warnings:
            log.emit(f"[WARN] bridge menu: {warning}")
        for error in bridge_errors:
            log.emit(f"[ERROR] bridge menu: {error}")
        if preflight_ok:
            if tool_warnings or suite_warnings:
                log.emit("[OK] Registry preflight passed with non-blocking warnings.")
            else:
                log.emit("[OK] Registry preflight passed.")
        else:
            log.emit("[ERROR] Registry preflight failed; registry ERROR blocks plugin rebuild.")
            log.emit(f"[NEXT] Open {output_dir / 'TOOL_AUDIT_FINDINGS.md'}")

    return 0 if preflight_ok else 2


def _verify_suite_list_actions_cli(repo_root: Path, output_dir: Path, expected_action_count: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    cmd = [
        sys.executable,
        str(repo_root / "tools" / "scripts" / "takesome.py"),
        "suite",
        "--list-actions",
        "--json",
        "--output-dir",
        str(output_dir / "suite-list-actions"),
    ]
    completed = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, timeout=60)
    if completed.returncode != 0:
        errors.append(f"command exited with {completed.returncode}")
        if completed.stderr.strip():
            errors.append(f"stderr: {completed.stderr.strip()[:1000]}")
        return errors, warnings
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"stdout is not JSON: {exc}")
        return errors, warnings

    result = envelope.get("result") or {}
    if result.get("registry_schema") != "northstar.suite_action_registry.v1":
        errors.append("missing descriptor registry marker: result.registry_schema")
    if result.get("registry_ok") is not True:
        errors.append("suite action registry is not ok in CLI output")
    action_count = int(result.get("descriptor_action_count") or result.get("action_count") or 0)
    if action_count != expected_action_count:
        errors.append(f"descriptor_action_count mismatch: expected {expected_action_count}, got {action_count}")

    actions = result.get("actions") or []
    if not actions:
        errors.append("CLI output contains no actions")
    for action in actions:
        descriptor_path = str(action.get("descriptor_path") or "")
        if not descriptor_path.startswith("tools/suite/actions/"):
            errors.append(f"action {action.get('key', '<unknown>')} is not descriptor-backed: {descriptor_path!r}")
    validation = result.get("validation") or []
    for item in validation:
        for warning in item.get("warnings", []):
            warnings.append(f"{item.get('action_id', '<unknown>')}: {warning}")
        for error in item.get("errors", []):
            errors.append(f"{item.get('action_id', '<unknown>')}: {error}")
    return errors, warnings


def _verify_bridge_menu_json(path: Path, expected_action_count: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - preflight should report exact file failure.
        return [f"failed to read bridge menu JSON {path}: {exc}"], warnings

    if payload.get("schema") != "northstar.suite.bridge_menu_actions.v1":
        errors.append("bridge menu schema mismatch")
    if payload.get("source") != "tools/suite/actions/*.json":
        errors.append("bridge menu source is not descriptor glob")
    if payload.get("ok") is not True:
        errors.append("bridge menu registry status is not ok")
    if int(payload.get("action_count") or 0) != expected_action_count:
        errors.append(f"bridge action_count mismatch: expected {expected_action_count}, got {payload.get('action_count')}")
    for action in payload.get("actions") or []:
        descriptor_path = str(action.get("descriptor_path") or "")
        if not descriptor_path.startswith("tools/suite/actions/"):
            errors.append(f"bridge action {action.get('key', '<unknown>')} is not descriptor-backed: {descriptor_path!r}")
    for item in payload.get("validation") or []:
        for warning in item.get("warnings", []):
            warnings.append(f"{item.get('action_id', '<unknown>')}: {warning}")
        for error in item.get("errors", []):
            errors.append(f"{item.get('action_id', '<unknown>')}: {error}")
    return errors, warnings
