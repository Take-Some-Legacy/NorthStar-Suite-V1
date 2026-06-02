from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..paths import suite_path


def manifest(root: Path) -> dict:
    path = plugins_root(root) / "build_manifest.json"
    if not path.exists():
        return {"plugins": [], "codecWorkers": []}
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_dirs(root: Path) -> None:
    (engine_core_root(root) / "plugins").mkdir(parents=True, exist_ok=True)
    (engine_core_root(root) / "plugins" / "codecs").mkdir(parents=True, exist_ok=True)
    suite_path(root, "build-state", "stamps").mkdir(parents=True, exist_ok=True)
    # Build logs are centralized under .takesome/buildLog. Remove the old
    # split path on build startup so stale runs do not look authoritative.
    old_build_logs = suite_path(root, "logs", "build")
    if old_build_logs.exists():
        shutil.rmtree(old_build_logs, ignore_errors=True)


def discover_plugin_names(root: Path) -> list[str]:
    """Discover buildable top-level plugins without hardcoded script lists."""
    m = manifest(root)
    ordered: list[str] = [str(name) for name in m.get("plugins", [])]
    plugin_root = plugins_root(root)
    discovered: list[str] = []
    if plugin_root.exists():
        for child in sorted(plugin_root.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and (child / "Cargo.toml").exists():
                discovered.append(child.name)
    seen: set[str] = set()
    merged: list[str] = []
    for name in [*ordered, *discovered]:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(name)
    return merged


def root_last_build_log_name(selected: str | None) -> str:
    if selected is None:
        return "lastbuild-all.log"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in selected.strip())
    safe = safe.strip("-._") or "selected"
    return f"lastbuild-{safe}.log"
