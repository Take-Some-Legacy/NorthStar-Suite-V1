from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

from .cargo.process import cargo_exe
from .paths import rel

YTYP_PACKER_MANIFEST = Path("tools") / "toolsSrc" / "ytyp_packer" / "Cargo.toml"


def ytyp_packer_exe(root: Path) -> Path | None:
    name = "northstar-ytyp-packer.exe" if os.name == "nt" else "northstar-ytyp-packer"
    candidates = [
        root / "tools" / "exe" / name,
        root / "tools" / "toolbelt" / "first_party" / "northstar" / "ytyp_packer" / "bin" / name,
        root / "tools" / "toolsSrc" / "ytyp_packer" / "target" / "release" / name,
        root / "tools" / "toolsSrc" / "ytyp_packer" / "target" / "debug" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def ytyp_packer_command(root: Path, args: Sequence[str]) -> list[str]:
    exe = ytyp_packer_exe(root)
    if exe is not None:
        return [str(exe), *args]
    cargo = cargo_exe() or "cargo"
    manifest = root / YTYP_PACKER_MANIFEST
    return [cargo, "run", "--manifest-path", str(manifest), "--", *args]


def run_ytyp_packer(root: Path, args: Sequence[str]) -> int:
    cmd = ytyp_packer_command(root, args)
    print("[CMD] " + " ".join(cmd))
    try:
        completed = subprocess.run(cmd, cwd=root)
    except FileNotFoundError as exc:
        print(f"[ERROR] ytyp_packer launch failed: {exc}")
        return 127
    if completed.returncode == 0:
        print("[OK] ytyp_packer finished successfully")
    else:
        print(f"[ERROR] ytyp_packer failed exit_code={completed.returncode}")
    return int(completed.returncode)


def default_ytyp_asset(root: Path) -> Path | None:
    base = root / "EngineRepo" / "NewEngine" / "neocore2" / "assets"
    if not base.exists():
        base = root / "NewEngine" / "neocore2" / "assets"
    for path in sorted(base.rglob("*.ytyp")):
        if not path.name.endswith(".ytyp.xml"):
            return path
    return None


def repo_arg(root: Path, raw: str) -> str:
    if not raw:
        return ""
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str(root / path)


def print_ytyp_tool_hint(root: Path) -> None:
    exe = ytyp_packer_exe(root)
    if exe is None:
        print("[WARN] ytyp_packer executable is not installed; suite will fall back to cargo run")
    else:
        print(f"[INFO] ytyp_packer executable: {rel(root, exe)}")
