from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

from .cargo.process import cargo_exe
from .paths import rel

NEUI_PACKER_MANIFEST = Path("tools") / "northstar" / "neui_packer" / "Cargo.toml"


def neui_packer_exe(root: Path) -> Path | None:
    name = "northstar-neui-packer.exe" if os.name == "nt" else "northstar-neui-packer"
    candidates = [
        root / "tools" / "exe" / name,
        root / "tools" / "northstar" / "neui_packer" / "target" / "debug" / name,
        root / "tools" / "northstar" / "neui_packer" / "target" / "release" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def neui_packer_command(root: Path, args: Sequence[str]) -> list[str]:
    exe = neui_packer_exe(root)
    if exe is not None:
        return [str(exe), *args]
    cargo = cargo_exe() or "cargo"
    manifest = root / NEUI_PACKER_MANIFEST
    return [cargo, "run", "--manifest-path", str(manifest), "--", *args]


def run_neui_packer(root: Path, args: Sequence[str]) -> int:
    cmd = neui_packer_command(root, args)
    print("[CMD] " + " ".join(cmd))
    try:
        completed = subprocess.run(cmd, cwd=root)
    except FileNotFoundError as exc:
        print(f"[ERROR] neui_packer launch failed: {exc}")
        return 127
    if completed.returncode == 0:
        print("[OK] neui_packer finished successfully")
    else:
        print(f"[ERROR] neui_packer failed exit_code={completed.returncode}")
    return int(completed.returncode)


def default_ui_assets_root(root: Path) -> Path:
    nested = root / "EngineRepo" / "NewEngine" / "neocore2" / "assets" / "ui"
    if nested.exists():
        return nested
    return root / "NewEngine" / "neocore2" / "assets" / "ui"


def first_neui_asset(root: Path) -> Path | None:
    base = default_ui_assets_root(root)
    if not base.exists():
        return None
    for path in sorted(base.rglob("*.neui")):
        if path.name.endswith(".neui.xml"):
            continue
        return path
    return None


def repo_arg(root: Path, raw: str) -> str:
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str(root / path)


def print_ui_tool_hint(root: Path) -> None:
    exe = neui_packer_exe(root)
    if exe is None:
        print("[WARN] neui_packer executable is not installed; suite will fall back to cargo run")
    else:
        print(f"[INFO] neui_packer executable: {rel(root, exe)}")
