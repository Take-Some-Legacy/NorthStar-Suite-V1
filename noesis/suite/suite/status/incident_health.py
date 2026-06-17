from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...paths import rel, utc_iso
from ...status_cache import write_status_snapshot


@dataclass(frozen=True)
class IncidentHealthSnapshot:
    exists: bool
    kind: str = ""
    target: str = ""
    generated_utc: str = ""
    summary: str = ""
    exit_code: int = 0

    @property
    def health(self) -> str:
        return "warn" if self.exists else "ok"

    def line(self, root: Path) -> str:
        if not self.exists:
            return "none"
        parts = [self.kind or "incident", self.target or "unknown", self.generated_utc or "unknown time"]
        return " · ".join(parts)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _cache_incident_health(root: Path, snapshot: IncidentHealthSnapshot) -> IncidentHealthSnapshot:
    write_status_snapshot(
        root,
        "incident-health",
        {
            "schema": "takesome.incidentHealth.v1",
            "generated_utc": utc_iso(),
            "exists": snapshot.exists,
            "kind": snapshot.kind,
            "target": snapshot.target,
            "incident_generated_utc": snapshot.generated_utc,
            "summary": snapshot.summary,
            "exit_code": snapshot.exit_code,
        },
        source="suite.status.incident_health.collect_incident_health",
    )
    return snapshot


def collect_incident_health(root: Path) -> IncidentHealthSnapshot:
    path = root / "last-incident.json"
    data = _read_json(path)
    if not data:
        return _cache_incident_health(root, IncidentHealthSnapshot(False))
    return _cache_incident_health(root, IncidentHealthSnapshot(
        True,
        kind=str(data.get("kind", "")),
        target=str(data.get("target", "")),
        generated_utc=str(data.get("generated_utc", data.get("started_utc", ""))),
        summary=str(data.get("summary", data.get("summary_md", ""))),
        exit_code=int(data.get("exit_code", 0) or 0),
    ))
