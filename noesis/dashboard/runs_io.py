from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        return {}
    return {}


def read_text(path: Path, *, limit: int = 40_000) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:limit] + "\n... <truncated>" if len(text) > limit else text
    except Exception:
        return ""


def artifact_links(run_dir: Path, run_id: str) -> list[dict[str, str]]:
    candidates = [
        "merge-readiness.json",
        "validation-report.json",
        "validation-report.md",
        "full-repo-report.json",
        "audit-report.json",
        "test-report.json",
        "build-report.json",
        "forbidden-files-report.json",
        "checksums.json",
        "proof-of-work.log",
        "changed-files.json",
        "manifest.json",
    ]
    artifacts: list[dict[str, str]] = []
    for name in candidates:
        path = run_dir / name
        if path.exists():
            artifacts.append({"name": name, "path": str(path), "url": f"/api/runs/{run_id}/artifacts/{name}"})
    return artifacts
