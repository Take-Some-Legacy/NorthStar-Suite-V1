from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, UTC)
    value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.fromtimestamp(0, UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(slots=True)
class Instruction:
    id: str
    created_at: str
    source: str
    kind: str
    scope: str
    priority: str
    text: str
    status: str = "active"
    supersedes: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)

    @classmethod
    def from_text(cls, instruction_id: str, text: str, *, priority: str = "high") -> "Instruction":
        lowered = text.lower()
        kind = "task"
        if any(word in lowered for word in ("stop", "останов", "нельзя", "запрет")):
            kind = "constraint"
        if any(word in lowered for word in ("сначала", "priority", "приоритет")):
            kind = "priority"
        if any(word in lowered for word in ("исправ", "коррект", "не так")):
            kind = "correction"
        return cls(
            id=instruction_id,
            created_at=utc_now_iso(),
            source="operator",
            kind=kind,
            scope="global",
            priority=priority,
            text=text.strip(),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "source": self.source,
            "kind": self.kind,
            "scope": self.scope,
            "priority": self.priority,
            "text": self.text,
            "status": self.status,
            "supersedes": list(self.supersedes),
            "conflicts_with": list(self.conflicts_with),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Instruction":
        return cls(
            id=str(data.get("id", "")),
            created_at=str(data.get("created_at", "")),
            source=str(data.get("source", "operator")),
            kind=str(data.get("kind", "task")),
            scope=str(data.get("scope", "global")),
            priority=str(data.get("priority", "normal")),
            text=str(data.get("text", "")),
            status=str(data.get("status", "active")),
            supersedes=list(data.get("supersedes", [])),
            conflicts_with=list(data.get("conflicts_with", [])),
        )

    def weight(self, now: datetime | None = None) -> float:
        priority_weight = {
            "critical": 10000.0,
            "high": 8000.0,
            "normal": 4000.0,
            "low": 1000.0,
        }.get(self.priority, 4000.0)
        kind_boost = {
            "constraint": 1200.0,
            "correction": 1000.0,
            "priority": 900.0,
            "task": 600.0,
            "mode": 500.0,
        }.get(self.kind, 0.0)
        now = now or datetime.now(UTC)
        age_seconds = max(0.0, (now - parse_utc(self.created_at)).total_seconds())
        freshness = max(0.0, 2400.0 - min(age_seconds / 60.0, 2400.0))
        stale_penalty = 0.0 if self.status == "active" else 5000.0
        return priority_weight + kind_boost + freshness - stale_penalty


@dataclass(slots=True)
class ScannerFinding:
    scanner: str
    severity: str
    path: str
    line: int
    message: str
    sample: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "scanner": self.scanner,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "sample": self.sample,
        }


@dataclass(slots=True)
class DatasetHit:
    path: str
    reason: str
    excerpts: list[str]

    def to_json(self) -> dict[str, Any]:
        return {"path": self.path, "reason": self.reason, "excerpts": list(self.excerpts)}


@dataclass(slots=True)
class SelectedTask:
    id: str
    priority: str
    title: str
    reason: str
    affected_paths: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "priority": self.priority,
            "title": self.title,
            "reason": self.reason,
            "affected_paths": list(self.affected_paths),
        }


@dataclass(slots=True)
class CycleResult:
    cycle: int
    started_at: str
    selected_task: SelectedTask
    request_path: Path
    report_path: Path
    findings: list[ScannerFinding]
    dataset_hits: list[DatasetHit]
    status: str

    def to_json(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "started_at": self.started_at,
            "selected_task": self.selected_task.to_json(),
            "request_path": str(self.request_path),
            "report_path": str(self.report_path),
            "findings": [finding.to_json() for finding in self.findings],
            "dataset_hits": [hit.to_json() for hit in self.dataset_hits],
            "status": self.status,
        }
