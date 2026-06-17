from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from . import operator_fs

COMMANDS = {
    "ns-list-dir",
    "ns-read-file",
    "ns-search-text",
    "ns-file-stat",
    "ns-tree",
    "ns-count-lines",
}


def register_operator_fs_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("ns-list-dir", help="Read-only bounded directory listing for AI/operator fs inspection.")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--include-skipped", action="store_true")

    p = sub.add_parser("ns-read-file", help="Read-only bounded UTF-8 text file read for AI/operator fs inspection.")
    p.add_argument("path")
    p.add_argument("--max-bytes", type=int, default=65536)
    p.add_argument("--offset", type=int, default=0)

    p = sub.add_parser("ns-search-text", help="Read-only bounded text search for AI/operator fs inspection.")
    p.add_argument("query")
    p.add_argument("--root", action="append")
    p.add_argument("--glob", action="append")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--regex", action="store_true")
    p.add_argument("--case-sensitive", action="store_true")

    p = sub.add_parser("ns-file-stat", help="Read-only file stat for AI/operator fs inspection.")
    p.add_argument("paths", nargs="+")

    p = sub.add_parser("ns-tree", help="Read-only bounded tree listing for AI/operator fs inspection.")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--limit", type=int, default=500)

    p = sub.add_parser("ns-count-lines", help="Read-only bounded source line counter for AI/operator fs inspection.")
    p.add_argument("--root", action="append")
    p.add_argument("--glob", action="append")
    p.add_argument("--limit", type=int, default=2000)


def dispatch_operator_fs_command(command: str, root: Path, ns: argparse.Namespace) -> int | None:
    handlers: dict[str, Callable[[Path, argparse.Namespace], int]] = {
        "ns-list-dir": operator_fs.ns_list_dir_command,
        "ns-read-file": operator_fs.ns_read_file_command,
        "ns-search-text": operator_fs.ns_search_text_command,
        "ns-file-stat": operator_fs.ns_file_stat_command,
        "ns-tree": operator_fs.ns_tree_command,
        "ns-count-lines": operator_fs.ns_count_lines_command,
    }
    handler = handlers.get(command)
    if handler is None:
        return None
    return handler(root, ns)
