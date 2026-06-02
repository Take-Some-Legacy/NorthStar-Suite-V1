from __future__ import annotations

import argparse
from pathlib import Path

from .ui_tooling import first_neui_asset, print_ui_tool_hint, repo_arg, run_neui_packer


def ui_inspect_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] UI inspect started")
    print_ui_tool_hint(root)
    input_arg = getattr(ns, "input", "")
    if not input_arg:
        first = first_neui_asset(root)
        if first is None:
            print("[ERROR] no .neui asset found; pass --input or run build-ui first")
            return 2
        input_arg = str(first)
        print(f"[INFO] default input: {first}")
    args = ["inspect", "--input", repo_arg(root, input_arg)]
    rc = run_neui_packer(root, args)
    if rc == 0:
        print("[OK] UI inspect finished")
    return rc
