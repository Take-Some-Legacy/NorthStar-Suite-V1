from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class OperationRecord:
    operation_id: str
    kind: str
    title: str
    status: str = "queued"
    command: list[str] = field(default_factory=list)
    started_utc: str = ""
    finished_utc: str = ""
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    report: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.operation_id,
            "operationId": self.operation_id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "command": self.command,
            "startedUtc": self.started_utc,
            "finishedUtc": self.finished_utc,
            "exitCode": self.exit_code,
            "stdout": self.stdout[-64000:],
            "stderr": self.stderr[-32000:],
            "report": self.report,
            "error": self.error,
            "running": self.status in {"queued", "running"},
        }


class OperationStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.Lock()
        self._items: dict[str, OperationRecord] = {}

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [item.as_dict() for item in reversed(list(self._items.values()))]

    def get(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get(operation_id)
            return item.as_dict() if item else None

    def start_suite_action(self, action_id: str, *, timeout_sec: int = 240) -> dict[str, Any]:
        action_id = str(action_id or "").strip()
        if not ACTION_ID_RE.match(action_id):
            return {"ok": False, "error": "invalid_action_id", "actionId": action_id}
        operation_id = "op-" + uuid.uuid4().hex[:12]
        command = [sys.executable, "-m", "noesis", "suite", "--run", action_id, "--json"]
        record = OperationRecord(
            operation_id=operation_id,
            kind="suite-action",
            title=action_id,
            command=command,
        )
        with self._lock:
            self._items[operation_id] = record
        thread = threading.Thread(target=self._run_subprocess, args=(record, timeout_sec), daemon=True)
        thread.start()
        return {"ok": True, "operation": record.as_dict()}

    def _run_subprocess(self, record: OperationRecord, timeout_sec: int) -> None:
        with self._lock:
            record.status = "running"
            record.started_utc = utc_now()
        try:
            completed = subprocess.run(
                record.command,
                cwd=str(self.root),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=max(1, int(timeout_sec)),
                shell=False,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            report: dict[str, Any] = {}
            stripped = stdout.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    report = parsed if isinstance(parsed, dict) else {"result": parsed}
                except Exception:
                    report = {"parseWarning": "stdout_is_not_json"}
            status = "ok" if completed.returncode == 0 else "failed"
            with self._lock:
                record.status = status
                record.exit_code = completed.returncode
                record.stdout = stdout
                record.stderr = stderr
                record.report = report
                record.finished_utc = utc_now()
        except subprocess.TimeoutExpired as exc:
            with self._lock:
                record.status = "failed"
                record.error = f"timeout_after_{timeout_sec}s"
                record.stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                record.stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
                record.finished_utc = utc_now()
        except Exception as exc:
            with self._lock:
                record.status = "failed"
                record.error = str(exc)
                record.finished_utc = utc_now()
