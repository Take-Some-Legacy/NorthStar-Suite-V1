from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from .ui_fonts import import_ui_fonts_command

COMMANDS = {
    "import-ui-fonts",
}


def register_ui_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("import-ui-fonts")
    p.add_argument("--manifest", default="", help="Path to editor.yft.import.json. Defaults to NewEngine/neocore2/assets/ui/fonts/editor.yft.import.json")
    p.add_argument("--output", "-o", default="", help="Output runtime .yft. Defaults to NewEngine/neocore2/assets/ui/fonts/editor.yft")


def dispatch_ui_command(command: str, root: Path, ns: argparse.Namespace) -> int | None:
    handlers: dict[str, Callable[[Path, argparse.Namespace], int]] = {
        "import-ui-fonts": import_ui_fonts_command,
    }
    handler = handlers.get(command)
    if handler is None:
        return None
    return handler(root, ns)
