from __future__ import annotations

import argparse
from pathlib import Path

from .ytd_tooling import default_ytd_asset, print_ytd_tool_hint, repo_arg, run_ytd_packer


def ytd_extract_command(root: Path, ns: argparse.Namespace) -> int:
    print("[INFO] YTD extract started")
    print_ytd_tool_hint(root)
    input_arg = getattr(ns, "input", "")
    if not input_arg:
        first = default_ytd_asset(root)
        if first is None:
            print("[ERROR] no .ytd asset found; pass --input")
            return 2
        input_arg = str(first)
        print(f"[INFO] default input: {first}")
    output_arg = getattr(ns, "output", "") or ".takesome/extract/ytd"
    args = ["extract", "--input", repo_arg(root, input_arg), "--output", repo_arg(root, output_arg)]
    if getattr(ns, "entry", ""):
        args.extend(["--entry", ns.entry])
    rc = run_ytd_packer(root, args)
    if rc == 0:
        print("[OK] YTD extract finished")
    return rc
