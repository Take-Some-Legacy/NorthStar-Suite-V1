from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


# NOESIS Proof-of-Work Trace Layer
# Contract: INTENT -> ACTION -> WRITE -> VERIFY -> TRACE
# Console output is emitted only after the file exists and was verified.


def utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _quote(value: Any) -> str:
    text = str(value if value is not None else "")
    if text == "":
        return '""'
    if any(ch.isspace() for ch in text) or any(ch in text for ch in ['"', "'", "="]):
        return json.dumps(text, ensure_ascii=False)
    return text


def emit(event: str, **fields: Any) -> None:
    parts = [event]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={_quote(value)}")
    print(" ".join(parts), flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_facts(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"bytes": int(stat.st_size), "sha256": sha256_file(path)}


def verify(kind: str, path: Path, *, cycle: int | str | None = None, task: str | None = None, action: str | None = None) -> dict[str, Any]:
    exists = path.exists()
    fields: dict[str, Any] = {
        "kind": kind,
        "path": str(path),
        "utc": utc_iso(),
        "cycle": cycle,
        "task": task,
        "action": action,
        "exists": str(exists).lower(),
    }
    if exists and path.is_file():
        fields.update(file_facts(path))
    emit("VERIFY", **fields)
    return fields


def record_write(kind: str, path: Path, *, cycle: int | str | None = None, task: str | None = None, action: str | None = None, verify_after: bool = True) -> None:
    fields: dict[str, Any] = {
        "kind": kind,
        "path": str(path),
        "utc": utc_iso(),
        "cycle": cycle,
        "task": task,
        "action": action,
    }
    if path.exists() and path.is_file():
        fields.update(file_facts(path))
    emit("WRITE", **fields)
    if verify_after:
        verify(kind, path, cycle=cycle, task=task, action=action)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    kind: str,
    cycle: int | str | None = None,
    task: str | None = None,
    action: str | None = None,
    encoding: str = "utf-8",
    retries: int = 8,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}-{time.time_ns()}"
    tmp = path.with_name(f"{path.name}.{token}.tmp")
    tmp.write_text(text, encoding=encoding, newline="\n")
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            tmp.replace(path)
            record_write(kind, path, cycle=cycle, task=task, action=action)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    try:
        if tmp.exists():
            tmp.unlink()
    finally:
        if last_error is not None:
            emit("WRITE_FAILED", kind=kind, path=str(path), utc=utc_iso(), cycle=cycle, task=task, action=action, error=repr(last_error))
            raise last_error


def atomic_write_json(path: Path, payload: dict[str, Any], *, kind: str, cycle: int | str | None = None, task: str | None = None, action: str | None = None) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", kind=kind, cycle=cycle, task=task, action=action)


def append_jsonl(path: Path, payload: dict[str, Any], *, kind: str, cycle: int | str | None = None, task: str | None = None, action: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        stream.flush()
        try:
            os.fsync(stream.fileno())
        except OSError:
            pass
    record_write(kind, path, cycle=cycle, task=task, action=action)


def cycle_start(*, cycle: int | str | None = None, task: str | None = None) -> None:
    emit("CYCLE", phase="start", utc=utc_iso(), cycle=cycle, task=task)


def cycle_done(*, cycle: int | str | None = None, task: str | None = None, status: str | None = None) -> None:
    emit("CYCLE", phase="done", utc=utc_iso(), cycle=cycle, task=task, status=status)


def task_start(*, cycle: int | str | None = None, task: str | None = None) -> None:
    emit("TASK", phase="start", utc=utc_iso(), cycle=cycle, task=task)


def task_done(*, cycle: int | str | None = None, task: str | None = None, status: str | None = None) -> None:
    emit("TASK", phase="done", utc=utc_iso(), cycle=cycle, task=task, status=status)


def lock_acquire(path: Path, *, pid: int | None = None, owner: str | None = None, cycle: int | str | None = None, task: str | None = None) -> None:
    emit("LOCK_ACQUIRE", path=str(path), utc=utc_iso(), pid=pid if pid is not None else os.getpid(), owner=owner, cycle=cycle, task=task)


def lock_release(path: Path, *, pid: int | None = None, owner: str | None = None, cycle: int | str | None = None, task: str | None = None) -> None:
    emit("LOCK_RELEASE", path=str(path), utc=utc_iso(), pid=pid if pid is not None else os.getpid(), owner=owner, cycle=cycle, task=task)
