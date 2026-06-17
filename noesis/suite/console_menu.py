from __future__ import annotations

# Compatibility import surface for existing callers. The implementation lives in
# noesis/suite/console/* so the console UI is no longer one god file.

from .console.action_menu import run_action_menu, run_confirm_button
from .console.dual_menu import run_dual_action_menu
from .console.input import interactive_menu_enabled
from .console.multiselect_menu import run_multi_select_menu
from .console.rows import (
    ConsoleActionMenuResult,
    ConsoleChoice,
    ConsoleConfirmResult,
    ConsoleMenuOption,
    ConsoleMultiSelectResult,
)

__all__ = [
    "ConsoleActionMenuResult",
    "ConsoleChoice",
    "ConsoleConfirmResult",
    "ConsoleMenuOption",
    "ConsoleMultiSelectResult",
    "interactive_menu_enabled",
    "run_action_menu",
    "run_confirm_button",
    "run_dual_action_menu",
    "run_multi_select_menu",
]
