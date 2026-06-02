from __future__ import annotations

import argparse
from pathlib import Path

from .ytd_tooling import print_ytd_tool_hint, repo_arg, run_ytd_packer


def ytd_build_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] YTD build started")
    print_ytd_tool_hint(root)
    args = ["pack"]
    if getattr(ns, "input_dir", ""):
        args.extend(["--input-dir", repo_arg(root, ns.input_dir)])
    for texture in getattr(ns, "texture", []) or []:
        args.extend(["--texture", texture])
    if getattr(ns, "output", ""):
        args.extend(["--output", repo_arg(root, ns.output)])
    else:
        print("[ERROR] build-ytd requires --output")
        return 2
    if getattr(ns, "linear", False):
        args.append("--linear")
    if getattr(ns, "no_mips", False):
        args.append("--no-mips")
    if getattr(ns, "raw_data", False):
        args.append("--raw-data")
    if not getattr(ns, "input_dir", "") and not getattr(ns, "texture", []):
        print("[ERROR] build-ytd requires --input-dir or one/more --texture name=path")
        return 2
    rc = run_ytd_packer(root, args)
    if rc == 0:
        print("[OK] YTD build finished")
    return rc
