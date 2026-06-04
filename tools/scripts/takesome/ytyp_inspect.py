from __future__ import annotations

import argparse
from pathlib import Path

from .ytyp_tooling import default_ytyp_asset, print_ytyp_tool_hint, repo_arg, run_ytyp_packer


def ytyp_inspect_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] YTYP metadata inspect started")
    print_ytyp_tool_hint(root)
    input_arg = getattr(ns, "input", "")
    if not input_arg:
        first = default_ytyp_asset(root)
        if first is None:
            print("[ERROR] no .ytyp asset found; pass --input")
            return 2
        input_arg = str(first)
        print(f"[INFO] default input: {first}")
    rc = run_ytyp_packer(root, ["inspect", "--input", repo_arg(root, input_arg)])
    if rc == 0:
        print("[OK] YTYP metadata inspect finished")
    return rc
