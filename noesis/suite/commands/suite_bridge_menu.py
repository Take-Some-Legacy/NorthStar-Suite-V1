from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..registry.suite_bridge_menu import write_bridge_menu_json


class _LogLike(Protocol):
    def emit(self, message: str) -> None: ...


def run_suite_bridge_menu_generate(repo_root: Path, output_path: Path | None = None, log: _LogLike | None = None) -> int:
    written = write_bridge_menu_json(repo_root, output_path=output_path)
    if log:
        log.emit(f"[OK] Suite bridge menu generated from descriptors: {written}")
    return 0
