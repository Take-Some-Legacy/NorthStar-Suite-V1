from __future__ import annotations

import argparse

from .commands.core_cli import dispatch_core_command, register_core_parsers
from .operator_fs_cli import dispatch_operator_fs_command, register_operator_fs_parsers
from .paths import repo_root
from .tool_descriptor_cli import dispatch_tool_descriptor_command, discover_suite_command_descriptors, register_tool_descriptor_parsers
from .ui_cli import dispatch_ui_command, register_ui_parsers


def main(argv: list[str]) -> int:
    root = repo_root()
    descriptor_driven_cli_tools = discover_suite_command_descriptors(root)

    parser = argparse.ArgumentParser(prog="python -m noesis")
    sub = parser.add_subparsers(dest="command", required=True)

    register_core_parsers(sub)
    register_ui_parsers(sub)
    register_tool_descriptor_parsers(sub, root, descriptor_driven_cli_tools)
    register_operator_fs_parsers(sub)

    ns = parser.parse_args(argv)

    core_result = dispatch_core_command(ns.command, root, ns)
    if core_result is not None:
        return core_result

    ui_result = dispatch_ui_command(ns.command, root, ns)
    if ui_result is not None:
        return ui_result

    descriptor_result = dispatch_tool_descriptor_command(ns.command, root, ns, descriptor_driven_cli_tools)
    if descriptor_result is not None:
        return descriptor_result

    operator_fs_result = dispatch_operator_fs_command(ns.command, root, ns)
    if operator_fs_result is not None:
        return operator_fs_result

    parser.error("unknown command")
    return 2
