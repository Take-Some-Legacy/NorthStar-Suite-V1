from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def tool_runtime_env(repo_root: Path, tool: Any) -> dict[str, str]:
    child = os.environ.copy()
    additions: list[str] = []

    exe = tool.executable or tool.install_path
    if exe is not None:
        additions.append(str(exe.parent.resolve()))

    for shared in tool.shared_libs or []:
        raw = str(shared.get("path", "")).strip()
        if raw:
            additions.append(str((repo_root / raw).resolve()))

    key = "".join(("PA", "TH"))
    old = child.get(key, "")
    if additions:
        values = [*additions, old] if old else additions
        child[key] = os.pathsep.join(values)
    return child
