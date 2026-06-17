from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPORT_DIR = Path(".takesome/filesystem/reports")


def _report(root: Path, name: str, payload: dict[str, Any]) -> None:
    REPORT_DIR_ABS = root / REPORT_DIR
    REPORT_DIR_ABS.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR_ABS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def fs_mkdir(root: Path) -> int:
    target = root / ".takesome" / "filesystem" / "workspace"
    target.mkdir(parents=True, exist_ok=True)
    _report(root, "mkdir", {"schema": "northstar.filesystem.mkdir.v1", "ok": True, "path": ".takesome/filesystem/workspace"})
    return 0
