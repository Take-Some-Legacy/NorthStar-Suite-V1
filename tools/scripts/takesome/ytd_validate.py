from __future__ import annotations

import argparse
from pathlib import Path

from .ytd_tooling import default_ytd_asset, print_ytd_tool_hint, repo_arg, run_ytd_packer


def ytd_validate_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] YTD validate started")
    print_ytd_tool_hint(root)
    input_arg = getattr(ns, "input", "")
    if not input_arg:
        first = default_ytd_asset(root)
        if first is None:
            print("[ERROR] no .ytd asset found; pass --input")
            return 2
        input_arg = str(first)
        print(f"[INFO] default input: {first}")
    rc = run_ytd_packer(root, ["validate", "--input", repo_arg(root, input_arg)])
    if rc == 0:
        print("[OK] YTD validate finished")
    return rc
