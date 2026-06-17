from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from .paths import rel


def third_party_test_all_command(root: Path, ns: argparse.Namespace) -> int:
    """Run all third-party local smoke tests through the third_party testAll.bat aggregator."""

    bat = root / "tools" / "toolbelt" / "third_party" / "testAll.bat"
    if not bat.exists():
        print(f"[ERROR] missing third-party test runner: {rel(root, bat)}")
        return 2

    print("[INFO] third-party testAll started")
    print(f"[INFO] runner: {rel(root, bat)}")

    env = os.environ.copy()
    env["NORTHSTAR_TESTALL"] = "1"

    completed = subprocess.run(
        ["cmd.exe", "/d", "/q", "/c", str(bat)],
        input="\n",
        cwd=root,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print("[STDERR]")
        print(completed.stderr, end="")

    report = root / "tools" / "toolbelt" / "third_party" / ".testAll" / "last-run.txt"
    if report.exists():
        print(f"[INFO] report: {rel(root, report)}")
    else:
        print(f"[ERROR] missing report: {rel(root, report)}")
        return 1

    if completed.stderr.strip():
        print("[ERROR] third-party testAll produced stderr")
        return 1

    if completed.returncode == 0:
        print("[OK] third-party testAll completed")
        return 0

    print(f"[ERROR] third-party testAll failed exit_code={completed.returncode}")
    return int(completed.returncode)
