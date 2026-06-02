from __future__ import annotations

import argparse
from pathlib import Path

from .ui_tooling import print_ui_tool_hint, repo_arg, run_neui_packer


def ui_build_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] UI build started")
    print_ui_tool_hint(root)
    args = ["compile", "--root", str(root)]
    if getattr(ns, "input", ""):
        args.extend(["--input", repo_arg(root, ns.input)])
    if getattr(ns, "output", ""):
        args.extend(["--output", repo_arg(root, ns.output)])
    if getattr(ns, "check", False):
        args.append("--check")
    if not getattr(ns, "input", ""):
        args.append("--all")
    rc = run_neui_packer(root, args)
    if rc == 0:
        print("[OK] UI build finished")
    return rc
