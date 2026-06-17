from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import Phase, ProofLog

FORBIDDEN_RUNTIME_ROOTS = (
    "tools/scripts",
    "config/suite",
)


def scan_forbidden_runtime_roots(repo: Path, proof: ProofLog) -> Phase:
    findings: list[dict[str, Any]] = []
    for rel in FORBIDDEN_RUNTIME_ROOTS:
        path = repo / rel
        if path.exists():
            findings.append({
                "path": rel,
                "reason": "forbidden_runtime_root_present",
            })
    status = "ok" if not findings else "failed"
    proof.emit("AUDIT", kind="runtime-boundaries", status=status, findings=len(findings))
    return Phase(
        name="runtime-boundaries",
        status=status,
        reason="forbidden_runtime_roots_present" if findings else "",
        data={"findings": findings, "passed": not findings},
    )
