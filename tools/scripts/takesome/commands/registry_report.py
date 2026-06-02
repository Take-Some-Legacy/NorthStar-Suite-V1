from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..paths import engine_core_root
from ..registry.registry_report import build_registry_report


class _LogLike(Protocol):
    def emit(self, message: str) -> None: ...


def run_registry_report(repo_root: Path, output_dir: Path | None = None, log: _LogLike | None = None) -> int:
    output_dir = output_dir or engine_core_root(repo_root) / "buildInfo" / "tools"
    report = build_registry_report(repo_root)
    report.write_all(output_dir)

    if log:
        log.emit(f"[INFO] Tool registry written: {output_dir / 'TOOL_REGISTRY.json'}")
        log.emit(f"[INFO] Suite actions written: {output_dir / 'SUITE_ACTIONS.json'}")
        if report.ok:
            log.emit("[OK] Suite/tooling registry validation passed.")
        else:
            log.emit("[ERROR] Suite/tooling registry validation found blocking diagnostics.")
            log.emit(f"[NEXT] Open {output_dir / 'TOOL_AUDIT_FINDINGS.md'}")
    return 0 if report.ok else 2
