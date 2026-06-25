from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, Sequence

from .build_preflight_registry import run_registry_build_preflight
from .registry_report import run_registry_report
from .observability import run_suite_observability_check
from .suite_bridge_menu import run_suite_bridge_menu_generate
from .suite_registry import run_suite_list_actions, run_suite_validate_actions
from .tool_registry import run_tools_doctor, run_tools_list, run_tools_validate
from ..suite_intelligence import suite_intelligence_command
from ..suite_intelligence_loop import loop_args_from_env, suite_intelligence_loop_command
from ..deepseek_smoke import run_deepseek_smoke


class _LogLike(Protocol):
    def emit(self, message: str) -> None: ...

_FALSE_ENV_VALUES = {"0", "false", "no", "off"}


def _suite_intelligence_enabled() -> bool:
    return os.environ.get("NORTHSTAR_SUITE_INTELLIGENCE_ENABLED", "0").strip().lower() not in _FALSE_ENV_VALUES


def _suite_intelligence_disabled_result(command: str, log: _LogLike | None) -> int:
    message = f"{command} skipped: Suite Intelligence is disabled by NORTHSTAR_SUITE_INTELLIGENCE_ENABLED."
    if log is not None:
        log.emit(message)
    else:
        print(f"[INFO] {message}")
    return 0


def try_handle_registry_command(argv: Sequence[str], repo_root: Path, log: _LogLike | None = None, parsed_args: SimpleNamespace | None = None) -> int | None:
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
    if command == "observability":
        return run_suite_observability_check(repo_root, log=log)
    if command == "suite-actions-list":
        return run_suite_list_actions(repo_root, log=log)
    if command == "suite-actions-validate":
        return run_suite_validate_actions(repo_root, log=log)
    if command == "suite-bridge-menu-generate":
        return run_suite_bridge_menu_generate(repo_root, log=log)
    if command == "suite-intelligence":
        if not _suite_intelligence_enabled():
            return _suite_intelligence_disabled_result(command, log)
        args = SimpleNamespace(
            goal=os.environ.get("NORTHSTAR_SUITE_INTELLIGENCE_GOAL", ""),
            output=os.environ.get("NORTHSTAR_SUITE_INTELLIGENCE_OUTPUT", ""),
            top=int(os.environ.get("NORTHSTAR_SUITE_INTELLIGENCE_TOP", "8") or "8"),
            json=os.environ.get("NORTHSTAR_SUITE_INTELLIGENCE_JSON", "").lower() in {"1", "true", "yes"},
            no_openai=os.environ.get("NORTHSTAR_SUITE_INTELLIGENCE_NO_OPENAI", "").lower() in {"1", "true", "yes"},
            self_check=os.environ.get("NORTHSTAR_SUITE_INTELLIGENCE_SELF_CHECK", "").lower() in {"1", "true", "yes"},
            openai_model=os.environ.get("NORTHSTAR_SUITE_OPENAI_MODEL", ""),
        )
        return suite_intelligence_command(repo_root, args)
    if command == "suite-intelligence-loop":
        if not _suite_intelligence_enabled():
            return _suite_intelligence_disabled_result(command, log)
        return suite_intelligence_loop_command(repo_root, loop_args_from_env(parsed_args=parsed_args))
    if command == "suite-intelligence-loop-check":
        if not _suite_intelligence_enabled():
            return _suite_intelligence_disabled_result(command, log)
        base = parsed_args or SimpleNamespace()
        setattr(base, "cycles", 1)
        return suite_intelligence_loop_command(repo_root, loop_args_from_env(cycles=1, parsed_args=base))
    if command == "suite-intelligence-smoke-deepseek":
        return run_deepseek_smoke(repo_root, SimpleNamespace())
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
    "observability",
    "suite-actions-list",
    "suite-actions-validate",
    "suite-bridge-menu-generate",
    "suite-intelligence",
    "suite-intelligence-loop",
    "suite-intelligence-loop-check",
    "suite-intelligence-smoke-deepseek",
    "tools-list",
    "tools-validate",
    "tools-doctor",
)
