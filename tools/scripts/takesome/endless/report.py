from __future__ import annotations

from .model import CycleResult, DatasetHit, Instruction, ScannerFinding, SelectedTask

STABLE_LAWS = [
    "Engine as Host.",
    "Service as Plugin.",
    "Capability as Option.",
    "Runtime as DTO pipeline.",
    "Diagnostics as Truth.",
    "No patch without dataset context.",
    "No hidden fallback; use explicit profile policy or real NullProvider route.",
]


def render_request_markdown(
    *,
    cycle: int,
    mode: str,
    instructions: list[Instruction],
    selected_task: SelectedTask,
    findings: list[ScannerFinding],
    dataset_hits: list[DatasetHit],
) -> str:
    ranked = sorted([i for i in instructions if i.status == "active"], key=lambda i: i.weight(), reverse=True)
    lines: list[str] = []
    lines.append(f"# Endless Stream Request - cycle {cycle}")
    lines.append("")
    lines.append(f"mode: {mode}")
    lines.append("source: chat.operator")
    lines.append("execution: dataset-backed foundation loop")
    lines.append("")
    lines.append("## Active Operator Instructions")
    if ranked:
        for instruction in ranked[:20]:
            lines.append(f"- [{instruction.priority}/{instruction.kind}] {instruction.id}: {instruction.text}")
    else:
        lines.append("- No active operator instructions.")
    lines.append("")
    lines.append("## Selected Task")
    lines.append(f"- id: {selected_task.id}")
    lines.append(f"- priority: {selected_task.priority}")
    lines.append(f"- title: {selected_task.title}")
    lines.append(f"- reason: {selected_task.reason}")
    if selected_task.affected_paths:
        lines.append("- affected paths:")
        lines.extend(f"  - {path}" for path in selected_task.affected_paths[:20])
    lines.append("")
    lines.append("## Dataset Context")
    lines.append("### Stable laws")
    for law in STABLE_LAWS:
        lines.append(f"- {law}")
    lines.append("")
    lines.append("### Relevant dataset hits")
    if dataset_hits:
        for hit in dataset_hits[:12]:
            lines.append(f"- {hit.path} - {hit.reason}")
            for excerpt in hit.excerpts[:4]:
                lines.append(f"  - {excerpt}")
    else:
        lines.append("- No dataset hits resolved; architecture mutation is blocked until dataset is available.")
    lines.append("")
    lines.append("## Scanner Findings")
    if findings:
        for finding in findings[:25]:
            location = f"{finding.path}:{finding.line}" if finding.line else finding.path
            lines.append(f"- [{finding.severity}] {finding.scanner} {location} - {finding.message}")
            if finding.sample:
                lines.append(f"  - sample: {finding.sample}")
    else:
        lines.append("- No findings in bounded foundation scan.")
    lines.append("")
    lines.append("## Required response fields")
    lines.append("- Selected task")
    lines.append("- Dataset rules applied")
    lines.append("- Files to change")
    lines.append("- Patch summary")
    lines.append("- Checks to run")
    lines.append("- Acceptance result")
    lines.append("- Next task")
    lines.append("")
    return "\n".join(lines)


def render_cycle_report(result: CycleResult, *, mode: str, instructions: list[Instruction]) -> str:
    active_count = len([instruction for instruction in instructions if instruction.status == "active"])
    errors = len([finding for finding in result.findings if finding.severity == "error"])
    warnings = len([finding for finding in result.findings if finding.severity == "warn"])
    lines: list[str] = []
    lines.append(f"# Endless Stream Cycle Report - cycle {result.cycle}")
    lines.append("")
    lines.append(f"status: {result.status}")
    lines.append(f"mode: {mode}")
    lines.append(f"started_at: {result.started_at}")
    lines.append("")
    lines.append("## What happened")
    lines.append("- Chat/operator instructions were ingested into the persistent Intent Ledger.")
    lines.append("- Fresh instructions were ranked above stale instructions unless they conflict with constant architecture law.")
    lines.append("- Dataset context was resolved before task execution.")
    lines.append("- Foundation scanners produced a bounded diagnostics set.")
    lines.append("- A transparent request packet and this report were written to .takesome/endless/cycles/.")
    lines.append("")
    lines.append("## Selected task")
    lines.append(f"- {result.selected_task.id}: {result.selected_task.title}")
    lines.append(f"- priority: {result.selected_task.priority}")
    lines.append(f"- reason: {result.selected_task.reason}")
    lines.append("")
    lines.append("## Diagnostics summary")
    lines.append(f"- active instructions: {active_count}")
    lines.append(f"- dataset hits: {len(result.dataset_hits)}")
    lines.append(f"- scanner findings: {len(result.findings)}")
    lines.append(f"- errors: {errors}")
    lines.append(f"- warnings: {warnings}")
    lines.append("")
    lines.append("## Artifacts")
    lines.append(f"- request: {result.request_path}")
    lines.append(f"- report: {result.report_path}")
    lines.append("- ledger: .takesome/endless/instruction_ledger.json")
    lines.append("- journal: .takesome/endless/stream_journal.ndjson")
    lines.append("")
    lines.append("## Operator visibility")
    lines.append("This cycle is chat-driven: the operator message becomes an instruction entry, receives a weight, appears in the request packet, and is preserved in the journal.")
    lines.append("")
    return "\n".join(lines)
