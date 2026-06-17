from __future__ import annotations

# Compatibility entrypoint for existing CLI imports. The suite implementation is
# intentionally owned by noesis/suite/suite/* so this file does not
# become a second command registry or renderer.

from .suite.shell import SUITE_VERSION, list_actions, run_action_by_key, suite_command

__all__ = ["SUITE_VERSION", "list_actions", "run_action_by_key", "suite_command"]
