from __future__ import annotations

import argparse
from pathlib import Path

from .ui_tooling import print_ui_tool_hint, repo_arg, run_neui_packer


def ui_validate_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] UI validate started")
    print_ui_tool_hint(root)
    args = ["validate", "--root", str(root)]
    if getattr(ns, "input", ""):
        args.extend(["--input", repo_arg(root, ns.input)])
    else:
        args.append("--all")
    rc = run_neui_packer(root, args)
    if rc == 0:
        print("[OK] UI validate finished")
    return rc
