from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_run_id() -> str:
    return "noesis-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def relpath(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class CommandResult:
    command: list[str]
    cwd: str
    exit_code: int
    duration_ms: int
    stdout_tail: str
    stderr_tail: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_json(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "cwd": self.cwd,
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
            "ok": self.ok,
            "stdoutTail": self.stdout_tail,
            "stderrTail": self.stderr_tail,
        }


@dataclass
class Phase:
    name: str
    status: str = "pending"
    reason: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "reason": self.reason, **self.data}


class ProofLog:
    def __init__(self, run_id: str, path: Path) -> None:
        self.run_id = run_id
        self.path = path
        ensure_parent(path)
        self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, **fields: Any) -> None:
        parts = [event, f"utc={utc_now()}", f"run={self.run_id}"]
        for key, value in fields.items():
            if value is None:
                continue
            text = str(value).replace("\n", " ").replace("\r", " ")
            if " " in text or text == "":
                text = json.dumps(text, ensure_ascii=False)
            parts.append(f"{key}={text}")
        line = " ".join(parts)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line)


def run_cmd(cmd: list[str], *, cwd: Path, timeout: int = 180) -> CommandResult:
    start = time.perf_counter()
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    elapsed = int((time.perf_counter() - start) * 1000)
    return CommandResult(
        command=cmd,
        cwd=str(cwd),
        exit_code=int(completed.returncode),
        duration_ms=elapsed,
        stdout_tail=(completed.stdout or "")[-12000:],
        stderr_tail=(completed.stderr or "")[-12000:],
    )


def write_json(path: Path, data: Any, proof: ProofLog | None = None, kind: str = "json") -> None:
    ensure_parent(path)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    if proof:
        proof.emit("WRITE", kind=kind, path=path.as_posix(), bytes=len(text.encode("utf-8")), sha256=sha256_bytes(text.encode("utf-8")))


def write_text(path: Path, text: str, proof: ProofLog | None = None, kind: str = "text") -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")
    if proof:
        proof.emit("WRITE", kind=kind, path=path.as_posix(), bytes=len(text.encode("utf-8")), sha256=sha256_bytes(text.encode("utf-8")))
