from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

from .cargo.process import cargo_exe
from .paths import rel

YTD_PACKER_MANIFEST = Path("tools") / "northstar" / "ytd_packer" / "Cargo.toml"


def ytd_packer_exe(root: Path) -> Path | None:
    name = "northstar-ytd-packer.exe" if os.name == "nt" else "northstar-ytd-packer"
    candidates = [
        root / "tools" / "exe" / name,
        root / "tools" / "northstar" / "ytd_packer" / "target" / "release" / name,
        root / "tools" / "northstar" / "ytd_packer" / "target" / "debug" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def ytd_packer_command(root: Path, args: Sequence[str]) -> list[str]:
    exe = ytd_packer_exe(root)
    if exe is not None:
        return [str(exe), *args]
    cargo = cargo_exe() or "cargo"
    manifest = root / YTD_PACKER_MANIFEST
    return [cargo, "run", "--manifest-path", str(manifest), "--", *args]


def run_ytd_packer(root: Path, args: Sequence[str]) -> int:
    cmd = ytd_packer_command(root, args)
    print("[CMD] " + " ".join(cmd))
    try:
        completed = subprocess.run(cmd, cwd=root)
    except FileNotFoundError as exc:
        print(f"[ERROR] ytd_packer launch failed: {exc}")
        return 127
    if completed.returncode == 0:
        print("[OK] ytd_packer finished successfully")
    else:
        print(f"[ERROR] ytd_packer failed exit_code={completed.returncode}")
    return int(completed.returncode)


def default_ytd_asset(root: Path) -> Path | None:
    base = root / "EngineRepo" / "NewEngine" / "neocore2" / "assets"
    if not base.exists():
        base = root / "NewEngine" / "neocore2" / "assets"
    for path in [
        base / "ui" / "icons" / "builtin_icons.ytd",
        base / "loading" / "loading_ui.ytd",
    ]:
        if path.exists():
            return path
    for path in sorted(base.rglob("*.ytd")):
        return path
    return None


def repo_arg(root: Path, raw: str) -> str:
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str(root / path)


def print_ytd_tool_hint(root: Path) -> None:
    exe = ytd_packer_exe(root)
    if exe is None:
        print("[WARN] ytd_packer executable is not installed; suite will fall back to cargo run")
    else:
        print(f"[INFO] ytd_packer executable: {rel(root, exe)}")
