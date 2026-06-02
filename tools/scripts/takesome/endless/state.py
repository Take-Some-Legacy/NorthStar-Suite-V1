from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import Instruction, utc_now_iso


class EndlessState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.base_dir = root / ".takesome" / "endless"
        self.cycles_dir = self.base_dir / "cycles"
        self.state_path = self.base_dir / "stream_state.json"
        self.ledger_path = self.base_dir / "instruction_ledger.json"
        self.journal_path = self.base_dir / "stream_journal.ndjson"

    def ensure_dirs(self) -> None:
        self.cycles_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {
                "schema": "northstar.endless.stream_state.v1",
                "cycle": 0,
                "mode": "foundation",
                "last_status": "new",
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            }
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "schema": "northstar.endless.stream_state.v1",
                "cycle": 0,
                "mode": "foundation",
                "last_status": "state_recovered",
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            }

    def save_state(self, state: dict[str, Any]) -> None:
        self.ensure_dirs()
        state["updated_at"] = utc_now_iso()
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def next_cycle(self, *, mode: str) -> int:
        state = self.load_state()
        cycle = int(state.get("cycle", 0)) + 1
        state["cycle"] = cycle
        state["mode"] = mode
        state["last_status"] = "running"
        self.save_state(state)
        return cycle

    def load_ledger(self) -> list[Instruction]:
        if not self.ledger_path.exists():
            return self.default_instructions()
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.default_instructions()
        rows = data.get("instructions", data if isinstance(data, list) else [])
        instructions = [Instruction.from_json(row) for row in rows if isinstance(row, dict)]
        known = {instruction.text for instruction in instructions}
        for default_instruction in self.default_instructions():
            if default_instruction.text not in known:
                instructions.append(default_instruction)
        return instructions

    def save_ledger(self, instructions: list[Instruction]) -> None:
        self.ensure_dirs()
        payload = {
            "schema": "northstar.endless.instruction_ledger.v1",
            "updated_at": utc_now_iso(),
            "instructions": [instruction.to_json() for instruction in instructions],
        }
        self.ledger_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def append_operator_notes(self, notes: list[str]) -> list[Instruction]:
        instructions = self.load_ledger()
        existing_ids = {instruction.id for instruction in instructions}
        start = len(existing_ids) + 1
        appended: list[Instruction] = []
        for offset, note in enumerate(notes):
            clean_note = note.strip()
            if not clean_note:
                continue
            instruction_id = f"instr-{start + offset:06d}"
            while instruction_id in existing_ids:
                start += 1
                instruction_id = f"instr-{start + offset:06d}"
            instruction = Instruction.from_text(instruction_id, clean_note, priority="high")
            instructions.append(instruction)
            appended.append(instruction)
            self.append_journal({
                "event": "instruction_received",
                "instruction_id": instruction.id,
                "created_at": instruction.created_at,
                "kind": instruction.kind,
                "priority": instruction.priority,
                "text": instruction.text,
            })
        self.save_ledger(instructions)
        return appended

    def append_journal(self, event: dict[str, Any]) -> None:
        self.ensure_dirs()
        row = dict(event)
        row.setdefault("at", utc_now_iso())
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def cycle_file(self, cycle: int, suffix: str) -> Path:
        self.ensure_dirs()
        return self.cycles_dir / f"{cycle:06d}-{suffix}"

    @staticmethod
    def default_instructions() -> list[Instruction]:
        defaults = [
            ("constant-000001", "critical", "No legacy aliases or compatibility shims after migration."),
            ("constant-000002", "critical", "No hidden fallback; Null providers must be real routes visible in diagnostics."),
            ("constant-000003", "critical", "P0/P1 foundation work has priority over feature work."),
            ("constant-000004", "critical", "No reusable runtime module may call concrete provider ids directly."),
            ("constant-000005", "critical", "Providers must receive and return DTO payloads, not &mut World or native EntityId."),
            ("constant-000006", "critical", "Every architecture change must include dataset context and acceptance checks."),
        ]
        return [
            Instruction(
                id=instruction_id,
                created_at="1970-01-01T00:00:00Z",
                source="dataset-constant",
                kind="constraint",
                scope="global",
                priority=priority,
                text=text,
            )
            for instruction_id, priority, text in defaults
        ]
