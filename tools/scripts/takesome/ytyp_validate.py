from __future__ import annotations

import argparse
from pathlib import Path

from .ytyp_tooling import print_ytyp_tool_hint, repo_arg, run_ytyp_packer


def ytyp_validate_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] YTYP metadata validate started")
    print_ytyp_tool_hint(root)
    args = ["validate", "--root", str(root)]
    input_arg = getattr(ns, "input", "")
    if input_arg:
        args.extend(["--input", repo_arg(root, input_arg)])
    else:
        args.append("--all")
    rc = run_ytyp_packer(root, args)
    if rc == 0:
        print("[OK] YTYP metadata validate finished")
    return rc
