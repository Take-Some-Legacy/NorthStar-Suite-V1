"""Registry primitives for North Star Suite tooling.

This package keeps Suite/tool discovery data-driven.  CLI and UI surfaces should
consume descriptors from here instead of hardcoding every command/tool button.
"""

from .suite_action_descriptor import SuiteActionDescriptor
from .suite_action_registry import SuiteActionRegistry, discover_suite_actions
from .tool_descriptor import ToolDescriptor, ToolValidationResult
from .tool_registry import ToolRegistry, discover_tools

__all__ = [
    "SuiteActionDescriptor",
    "SuiteActionRegistry",
    "ToolDescriptor",
    "ToolRegistry",
    "ToolValidationResult",
    "discover_suite_actions",
    "discover_tools",
]
