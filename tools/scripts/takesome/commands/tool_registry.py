from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..paths import engine_core_root
from ..registry.registry_report import build_registry_report
from ..registry.tool_registry import discover_tools


class _LogLike(Protocol):
    def emit(self, message: str) -> None: ...


def run_tools_list(repo_root: Path, log: _LogLike | None = None) -> int:
    registry = discover_tools(repo_root)
    if log:
        log.emit("[INFO] Registered tools:")
        for tool in sorted(registry.tools, key=lambda item: item.tool_id):
            auto_run = "auto-run" if tool.safe_to_auto_run else "manual"
            log.emit(
                f"[TOOL] {tool.tool_id} category={tool.category} source={tool.source_type} "
                f"lifecycle={tool.lifecycle} safety={tool.safety} mode={auto_run}"
            )
        for result in registry.validation:
            for warning in result.warnings:
                log.emit(f"[WARN] {result.tool_id}: {warning}")
            for error in result.errors:
                log.emit(f"[ERROR] {result.tool_id}: {error}")
    return 0 if registry.ok else 2


def run_tools_validate(repo_root: Path, output_dir: Path | None = None, log: _LogLike | None = None) -> int:
    output_dir = output_dir or engine_core_root(repo_root) / "buildInfo" / "tools"
    report = build_registry_report(repo_root)
    report.write_all(output_dir)
    if log:
        log.emit(f"[INFO] Tool registry report written: {output_dir / 'TOOL_REGISTRY.md'}")
        for result in report.tool_registry.validation:
            for warning in result.warnings:
                log.emit(f"[WARN] {result.tool_id}: {warning}")
            for error in result.errors:
                log.emit(f"[ERROR] {result.tool_id}: {error}")
        if report.tool_registry.ok:
            log.emit("[OK] Tool registry validation passed.")
        else:
            log.emit("[ERROR] Tool registry validation failed.")
    return 0 if report.tool_registry.ok else 2


def run_tools_doctor(repo_root: Path, output_dir: Path | None = None, log: _LogLike | None = None) -> int:
    output_dir = output_dir or engine_core_root(repo_root) / "buildInfo" / "tools"
    report = build_registry_report(repo_root)
    report.write_all(output_dir)
    warning_count = sum(len(item.warnings) for item in report.tool_registry.validation)
    if log:
        log.emit(f"[INFO] Tool doctor report written: {output_dir / 'TOOL_AUDIT_FINDINGS.md'}")
        log.emit(f"[INFO] Tools: {len(report.tool_registry.tools)}")
        log.emit(f"[INFO] Warnings: {warning_count}")
        for result in report.tool_registry.validation:
            for warning in result.warnings:
                log.emit(f"[WARN] {result.tool_id}: {warning}")
            for error in result.errors:
                log.emit(f"[ERROR] {result.tool_id}: {error}")
        if report.tool_registry.ok:
            log.emit("[OK] Tool doctor passed.")
        else:
            log.emit("[ERROR] Tool doctor found blocking diagnostics.")
    return 0 if report.tool_registry.ok else 2
