from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runs_io import artifact_links


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: str
    scope: str
    readiness_kind: str
    reason: str
    failed_phase: str
    changed_files: int
    tests_passed: int
    tests_failed: int
    audit_issues: int
    previous_rejections: int
    whole_repository_ready: bool
    created_utc: str
    completed_utc: str
    duration_ms: int | None
    artifact_checksum_count: int
    run_dir: str

    def to_json(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "status": self.status,
            "scope": self.scope,
            "readinessKind": self.readiness_kind,
            "reason": self.reason,
            "failedPhase": self.failed_phase,
            "changedFiles": self.changed_files,
            "testsPassed": self.tests_passed,
            "testsFailed": self.tests_failed,
            "auditIssues": self.audit_issues,
            "previousRejections": self.previous_rejections,
            "wholeRepositoryReady": self.whole_repository_ready,
            "createdUtc": self.created_utc,
            "completedUtc": self.completed_utc,
            "durationMs": self.duration_ms,
            "artifactChecksumCount": self.artifact_checksum_count,
            "runDir": self.run_dir,
            "artifacts": artifact_links(Path(self.run_dir), self.run_id),
        }
