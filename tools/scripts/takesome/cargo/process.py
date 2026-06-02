from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..logs import TeeLog, run_process


def cargo_exe() -> str | None:
    exe = shutil.which("cargo")
    if exe:
        return exe
    # Rustup installs Cargo here by default on Windows; bridge/service PATH can miss it.
    home = Path.home()
    candidates = [
        home / ".cargo" / "bin" / "cargo.exe",
        home / ".rustup" / "toolchains" / "stable-x86_64-pc-windows-msvc" / "bin" / "cargo.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def cargo_version() -> tuple[int, str]:
    exe = cargo_exe()
    if not exe:
        return 1, ""
    proc = subprocess.run([exe, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout.strip()


def rust_target_available(target: str | None = None) -> tuple[bool, str]:
    exe = cargo_exe()
    if not exe:
        return False, "cargo not found"
    proc = subprocess.run([exe, "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return False, proc.stdout.strip() or "cargo --version failed"
    if not target:
        return True, proc.stdout.strip()
    proc = subprocess.run([exe, "rustc", "--target", target, "--", "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    return proc.returncode == 0, proc.stdout.strip()


def run_cargo_build(args: list[str], *, cwd: Path, log: TeeLog, env: dict[str, str] | None = None) -> int:
    exe = cargo_exe() or "cargo"
    return run_process([exe, "build", *args], cwd=cwd, log=log, env=env)
