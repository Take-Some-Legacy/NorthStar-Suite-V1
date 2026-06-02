from __future__ import annotations

from pathlib import Path
from typing import Sequence, Protocol

from .build_preflight_registry import run_registry_build_preflight
from .registry_report import run_registry_report
from .suite_bridge_menu import run_suite_bridge_menu_generate
from .suite_registry import run_suite_list_actions, run_suite_validate_actions
from .tool_registry import run_tools_doctor, run_tools_list, run_tools_validate


class _LogLike(Protocol):
    def emit(self, message: str) -> None: ...


def try_handle_registry_command(argv: Sequence[str], repo_root: Path, log: _LogLike | None = None) -> int | None:
    """Small integration hook for the existing `takesome.py` CLI.

    Current CLI code can call this before the legacy command switch.  Returning
    `None` means the command is not owned by the descriptor registry layer.
    """

    if not argv:
        return None

    command = argv[0]
    if command == "registry-report":
        return run_registry_report(repo_root, log=log)
    if command == "registry-preflight":
        return run_registry_build_preflight(repo_root, log=log)
    if command == "suite-actions-list":
        return run_suite_list_actions(repo_root, log=log)
    if command == "suite-actions-validate":
        return run_suite_validate_actions(repo_root, log=log)
    if command == "suite-bridge-menu-generate":
        return run_suite_bridge_menu_generate(repo_root, log=log)
    if command == "tools-list":
        return run_tools_list(repo_root, log=log)
    if command == "tools-validate":
        return run_tools_validate(repo_root, log=log)
    if command == "tools-doctor":
        return run_tools_doctor(repo_root, log=log)

    return None


REGISTRY_COMMAND_IDS = (
    "registry-report",
    "registry-preflight",
    "suite-actions-list",
    "suite-actions-validate",
    "suite-bridge-menu-generate",
    "tools-list",
    "tools-validate",
    "tools-doctor",
)
