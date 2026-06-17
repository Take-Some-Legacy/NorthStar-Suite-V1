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

_STEERING_PHRASES = (
    "continue endless stream",
    "continue foundation series",
    "start first endless stream",
    "pick next",
    "select the highest",
    "do not wait",
    "without waiting",
    "foundation-first",
    "foundation series",
    "stream steering",
    "не жди",
    "продолжай",
    "выбери следующий",
    "без пинка",
)

_EPHEMERAL_PHRASES = (
    "cli smoke",
    "smoke test",
    "smoke:",
    "проверить прозрачный",
    "test cycle",
    "help check",
)


def is_stream_steering_instruction(instruction: Instruction) -> bool:
    lowered = instruction.text.lower()
    if instruction.kind in {"constraint", "priority", "mode"}:
        return True
    return any(phrase in lowered for phrase in _STEERING_PHRASES)


def is_ephemeral_instruction(instruction: Instruction) -> bool:
    lowered = instruction.text.lower()
    return any(phrase in lowered for phrase in _EPHEMERAL_PHRASES)


def _select_from_findings(findings: list[ScannerFinding]) -> SelectedTask | None:
    if not findings:
        return None
    scanner_rank = {
        "no_legacy_scan": 500,
        "direct_provider_id_scan": 450,
        "hidden_fallback_scan": 400,
        "service_boundary_scan": 350,
        "large_module_scan": 300,
    }
    severity_rank = {"error": 100, "warn": 50, "info": 10}
    top_finding = max(
        findings,
        key=lambda finding: scanner_rank.get(finding.scanner, 0) + severity_rank.get(finding.severity, 0),
    )
    priority, title = _TASK_BY_SCANNER.get(top_finding.scanner, ("P1", top_finding.message))
    related = sorted({finding.path for finding in findings if finding.scanner == top_finding.scanner})[:10]
    return SelectedTask(
        id=f"scanner-{top_finding.scanner}",
        priority=priority,
        title=title,
        reason=f"highest ranked scanner finding from {top_finding.scanner}",
        affected_paths=related,
    )


def select_task(instructions: list[Instruction], findings: list[ScannerFinding]) -> SelectedTask:
    now = datetime.now(timezone.utc)
    active = [instruction for instruction in instructions if instruction.status == "active"]
    newest_operator = max(
        [instruction for instruction in active if instruction.source == "operator"],
        key=lambda instruction: instruction.created_at,
        default=None,
    )

    # If the latest operator input is stream-control, it explicitly asks the
    # loop to continue autonomously, so scanner-backed P0/P1 work wins over old
    # one-off smoke/test notes left in the ledger.
    if newest_operator and is_stream_steering_instruction(newest_operator):
        scanner_task = _select_from_findings(findings)
        if scanner_task:
            return scanner_task

    concrete_operator_tasks = [
        instruction
        for instruction in active
        if instruction.source == "operator"
        and instruction.kind in {"task", "correction"}
        and not is_stream_steering_instruction(instruction)
        and not is_ephemeral_instruction(instruction)
    ]
    if concrete_operator_tasks:
        top = max(concrete_operator_tasks, key=lambda instruction: instruction.weight(now))
        return SelectedTask(
            id=top.id,
            priority=top.priority,
            title=top.text,
            reason=f"highest weighted concrete operator task: kind={top.kind}, source={top.source}",
            affected_paths=[],
        )

    scanner_task = _select_from_findings(findings)
    if scanner_task:
        return scanner_task

    return SelectedTask(
        id="idle-foundation-review",
        priority="P1",
        title="Run dataset-backed foundation review",
        reason="no concrete operator task and no scanner findings in bounded scan",
        affected_paths=[],
    )
