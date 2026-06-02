from __future__ import annotations

from pathlib import Path

from .checks import run_foundation_scans
from .dataset import resolve_dataset_context
from .model import CycleResult, Instruction, SelectedTask, utc_now_iso
from .report import render_cycle_report, render_request_markdown
from .selector import select_task
from .state import EndlessState


class EndlessRunner:
    def __init__(self, root: Path, mode: str = "foundation") -> None:
        self.root = root
        self.state = EndlessState(root)
        self.mode = mode

    def run_cycle(self, operator_notes: list[str], *, source: str = "chat.operator") -> CycleResult:
        cycle_number = self.state.next_cycle(mode=self.mode)
        appended = self.state.append_operator_notes(operator_notes)
        instructions = self.state.load_ledger()
        findings = run_foundation_scans(self.root)
        selected_task = self._select_task(instructions, findings, appended)
        dataset_hits = resolve_dataset_context(self.root, selected_task.title)

        request_path = self.state.cycle_file(cycle_number, "request.md")
        report_path = self.state.cycle_file(cycle_number, "report.md")
        started_at = appended[-1].created_at if appended else utc_now_iso()
        result = CycleResult(
            cycle=cycle_number,
            started_at=started_at,
            selected_task=selected_task,
            request_path=request_path,
            report_path=report_path,
            findings=findings,
            dataset_hits=dataset_hits,
            status="request_ready",
        )

        request_text = render_request_markdown(
            cycle=cycle_number,
            mode=self.mode,
            instructions=instructions,
            selected_task=selected_task,
            findings=findings,
            dataset_hits=dataset_hits,
        )
        request_path.write_text(request_text, encoding="utf-8")

        report_text = render_cycle_report(result, mode=self.mode, instructions=instructions)
        report_path.write_text(report_text, encoding="utf-8")

        state = self.state.load_state()
        state["last_status"] = result.status
        state["last_cycle"] = result.to_json()
        self.state.save_state(state)
        self.state.append_journal(
            {
                "event": "cycle_reported",
                "cycle": cycle_number,
                "source": source,
                "status": result.status,
                "selected_task": result.selected_task.to_json(),
                "request_path": str(request_path),
                "report_path": str(report_path),
                "finding_count": len(findings),
                "dataset_hit_count": len(dataset_hits),
            }
        )
        return result

    def _select_task(
        self,
        instructions: list[Instruction],
        findings: list,
        appended: list[Instruction],
    ) -> SelectedTask:
        return select_task(instructions, findings)

def run_endless_stream(root: Path | str, operator_notes: list[str] | None = None, mode: str = "foundation") -> CycleResult:
    if isinstance(root, str):
        root = Path(root)
    operator_notes = operator_notes or []
    runner = EndlessRunner(root, mode)
    return runner.run_cycle(operator_notes, source="programmatic")


def run_chat_operator_cycle(root: Path | str, message: str, mode: str = "foundation") -> CycleResult:
    if isinstance(root, str):
        root = Path(root)
    runner = EndlessRunner(root, mode)
    return runner.run_cycle([message], source="chat.operator")
