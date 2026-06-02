from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .runner import EndlessRunner


def _read_message_file(path_text: str, root: Path) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    if not path.is_absolute():
        path = root / path
    return path.read_text(encoding="utf-8", errors="replace")


def _collect_operator_messages(root: Path, ns: Any) -> list[str]:
    messages: list[str] = []
    for message in getattr(ns, "message", []) or []:
        clean = str(message).strip()
        if clean:
            messages.append(clean)
    message_file = str(getattr(ns, "message_file", "") or "").strip()
    if message_file:
        clean = _read_message_file(message_file, root).strip()
        if clean:
            messages.append(clean)
    if bool(getattr(ns, "stdin", False)):
        clean = sys.stdin.read().strip()
        if clean:
            messages.append(clean)
    return messages


def endless_stream_command(root: Path, ns: Any) -> int:
    messages = _collect_operator_messages(root, ns)
    if not messages:
        print("[ERROR] Endless Stream needs an operator message.")
        print("[INFO] Use --message, --message-file or --stdin.")
        return 2

    mode = str(getattr(ns, "mode", "foundation") or "foundation")
    runner = EndlessRunner(root, mode)
    result = runner.run_cycle(messages, source="cli.operator")

    print(f"[OK] Endless Stream cycle {result.cycle} prepared.")
    print(f"[INFO] status={result.status} mode={mode}")
    print(f"[INFO] selected={result.selected_task.id}: {result.selected_task.title}")
    print(f"[INFO] dataset_hits={len(result.dataset_hits)} findings={len(result.findings)}")
    print(f"[INFO] request={result.request_path}")
    print(f"[INFO] report={result.report_path}")
    print("[INFO] ledger=.takesome/endless/instruction_ledger.json")
    print("[INFO] journal=.takesome/endless/stream_journal.ndjson")
    return 0
