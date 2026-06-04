from __future__ import annotations

import argparse
from pathlib import Path

from .ytyp_tooling import print_ytyp_tool_hint, repo_arg, run_ytyp_packer


def ytyp_build_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] YTYP metadata build started")
    print_ytyp_tool_hint(root)
    args = ["compile", "--root", str(root)]
    if getattr(ns, "input", ""):
        args.extend(["--input", repo_arg(root, ns.input)])
    else:
        args.append("--all")
    if getattr(ns, "output", ""):
        args.extend(["--output", repo_arg(root, ns.output)])
    if getattr(ns, "check", False):
        args.append("--check")
    rc = run_ytyp_packer(root, args)
    if rc == 0:
        print("[OK] YTYP metadata build finished")
    return rc
