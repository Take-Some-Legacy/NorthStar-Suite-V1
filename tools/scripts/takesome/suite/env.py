from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from ..console import console_emit
from ..paths import rel, suite_path, suite_root

SCRIPT_ENV_VERSION = "4"


def discover_python_cmd() -> str:
    value = os.environ.get("NEWENGINE_SUITE_PYTHON_CMD", "").strip()
    if value:
        return value
    exe = Path(sys.executable)
    if exe.exists():
        return str(exe)
    return "python"


def split_cmd(command: str) -> list[str]:
    command = command.strip()
    if not command:
        return ["python"]
    try:
        if Path(command).exists():
            return [command]
    except OSError:
        pass
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return [command]


def _cmd_set_value(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped.lower().startswith("set "):
        return None
    payload = stripped[4:].strip()
    if payload.startswith('"') and payload.endswith('"'):
        payload = payload[1:-1]
    if "=" not in payload:
        return None
    key, value = payload.split("=", 1)
    key = key.strip()
    if not key:
        return None
    return key, value


def load_env_cmd(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = _cmd_set_value(raw)
        if parsed is None:
            continue
        key, value = parsed
        loaded[key] = value
        os.environ[key] = value
    return loaded


def env_is_valid(root: Path, env_file: Path, *, suite_version: str) -> bool:
    if not env_file.exists():
        return False
    loaded = load_env_cmd(env_file)
    project = Path(loaded.get("NEWENGINE_PROJECT_ROOT") or loaded.get("NEWENGINE_REPO_ROOT") or "")
    engine = Path(loaded.get("NEWENGINE_ROOT") or "")
    script_root = Path(loaded.get("NEWENGINE_SCRIPT_ROOT") or "")
    try:
        if project.resolve() != root.resolve():
            return False
    except OSError:
        return False
    if loaded.get("NEWENGINE_SCRIPT_ENV_VERSION") != SCRIPT_ENV_VERSION:
        return False
    if loaded.get("NEWENGINE_SUITE_VERSION") != suite_version:
        return False
    if not (engine / "Cargo.toml").exists():
        return False
    if not (script_root / "takesome.py").exists():
        return False
    return True


def ensure_script_env(root: Path, *, suite_version: str) -> int:
    suite = suite_root(root)
    env_file = suite_path(root, "script-env.cmd")
    if env_is_valid(root, env_file, suite_version=suite_version):
        console_emit(f"[OK] Script Env ready: {rel(root, env_file)}")
        return 0

    console_emit("[WARN] Script Env is missing or stale. Running suite init now.")
    suite.mkdir(parents=True, exist_ok=True)
    init_script = root / "tools" / "scripts" / "init_script_env.py"
    if not init_script.exists():
        console_emit(f"[ERROR] Missing initializer: {rel(root, init_script)}")
        return 11

    python_cmd = discover_python_cmd()
    cmd = [
        *split_cmd(python_cmd),
        str(init_script),
        "--repo-root",
        str(root),
        "--emit-cmd",
        str(env_file),
        "--python-cmd",
        python_cmd,
        "--suite-version",
        suite_version,
    ]
    try:
        rc = subprocess.call(cmd, cwd=str(root))
    except OSError as exc:
        console_emit(f"[ERROR] Failed to run suite init: {exc}")
        return 12
    if rc != 0:
        console_emit(f"[ERROR] Suite init failed with code {rc}.")
        return rc
    if not env_is_valid(root, env_file, suite_version=suite_version):
        loaded = load_env_cmd(env_file)
        console_emit(f"[ERROR] Suite init completed but env cache is invalid: {rel(root, env_file)}")
        console_emit(f"[ERROR] Expected suite version: {suite_version}; env has: {loaded.get('NEWENGINE_SUITE_VERSION', '<missing>')}")
        console_emit(f"[ERROR] Expected script env version: {SCRIPT_ENV_VERSION}; env has: {loaded.get('NEWENGINE_SCRIPT_ENV_VERSION', '<missing>')}")
        return 13
    console_emit(f"[OK] Script Env ready: {rel(root, env_file)}")
    return 0
