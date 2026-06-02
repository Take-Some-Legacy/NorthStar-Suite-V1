from __future__ import annotations

from datetime import datetime, timezone

from .model import Instruction, ScannerFinding, SelectedTask


_TASK_BY_SCANNER = {
    "no_legacy_scan": ("P0", "Remove legacy public/runtime references"),
    "direct_provider_id_scan": ("P0", "Remove direct provider id calls from consumers"),
    "hidden_fallback_scan": ("P0", "Replace hidden fallback with explicit provider/profile route"),
    "service_boundary_scan": ("P0", "Clean provider/service DTO boundaries"),
    "large_module_scan": ("P0", "Split oversized Rust modules"),
}


def select_task(instructions: list[Instruction], findings: list[ScannerFinding]) -> SelectedTask:
    active_instructions = [instruction for instruction in instructions if instruction.status == "active"]
    now = datetime.now(timezone.utc)
    if active_instructions:
        top = max(active_instructions, key=lambda instruction: instruction.weight(now))
        return SelectedTask(
            id=top.id,
            priority=top.priority,
            title=top.text,
            reason=f"highest weighted active instruction: kind={top.kind}, source={top.source}",
            affected_paths=[],
        )

    if findings:
        severity_rank = {"error": 3, "warn": 2, "info": 1}
        top_finding = max(findings, key=lambda finding: severity_rank.get(finding.severity, 0))
        priority, title = _TASK_BY_SCANNER.get(top_finding.scanner, ("P1", top_finding.message))
        related = sorted({finding.path for finding in findings if finding.scanner == top_finding.scanner})[:10]
        return SelectedTask(
            id=f"scanner-{top_finding.scanner}",
            priority=priority,
            title=title,
            reason=f"highest scanner severity from {top_finding.scanner}",
            affected_paths=related,
        )

    return SelectedTask(
        id="idle-foundation-review",
        priority="P1",
        title="Run dataset-backed foundation review",
        reason="no active operator task and no scanner findings in bounded scan",
        affected_paths=[],
    )
