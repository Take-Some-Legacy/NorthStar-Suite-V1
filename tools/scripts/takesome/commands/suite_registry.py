from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..registry.registry_report import build_registry_report
from ..registry.suite_action_registry import discover_suite_actions


class _LogLike(Protocol):
    def emit(self, message: str) -> None: ...


def run_suite_list_actions(repo_root: Path, log: _LogLike | None = None) -> int:
    registry = discover_suite_actions(repo_root)
    if log:
        log.emit("[INFO] Registered Suite actions:")
        for action in sorted(registry.actions, key=lambda item: (item.group, item.action_id)):
            menu = "menu" if action.safe_for_menu else "hidden"
            command = " ".join([action.command, *action.args]).strip()
            log.emit(f"[ACTION] {action.action_id} group={action.group} mode={menu} danger={action.danger_level} command='{command}'")
        for result in registry.validation:
            for warning in result.warnings:
                log.emit(f"[WARN] {result.action_id}: {warning}")
            for error in result.errors:
                log.emit(f"[ERROR] {result.action_id}: {error}")
    return 0 if registry.ok else 2


def run_suite_validate_actions(repo_root: Path, output_dir: Path | None = None, log: _LogLike | None = None) -> int:
    output_dir = output_dir or repo_root / "NewEngine" / "neocore2" / "buildInfo" / "tools"
    report = build_registry_report(repo_root)
    report.write_all(output_dir)
    if log:
        log.emit(f"[INFO] Suite actions report written: {output_dir / 'SUITE_ACTIONS.md'}")
        for result in report.suite_registry.validation:
            for warning in result.warnings:
                log.emit(f"[WARN] {result.action_id}: {warning}")
            for error in result.errors:
                log.emit(f"[ERROR] {result.action_id}: {error}")
        if report.suite_registry.ok:
            log.emit("[OK] Suite action registry validation passed.")
        else:
            log.emit("[ERROR] Suite action registry validation failed.")
    return 0 if report.suite_registry.ok else 2
