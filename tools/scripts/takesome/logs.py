from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import Iterator
from pathlib import Path
from typing import Sequence

from .console import colorize_script_line, colorize_stream_line, strip_ansi
from .progress import progress_observe_line, progress_tick

class TeeLog:
    def __init__(self, current_log: Path | None = None, *copy_targets: Path):
        self.current_log = current_log
        self.copy_targets = [p for p in copy_targets if p is not None]
        self._fh = None
        self._extra_fhs = []
        if current_log is not None:
            current_log.parent.mkdir(parents=True, exist_ok=True)
            self._fh = current_log.open("w", encoding="utf-8", newline="")

    def add_copy_target(self, path: Path) -> None:
        """Mirror the full primary log to an additional path on close."""
        if path is None:
            return
        resolved = path.resolve()
        for existing in self.copy_targets:
            try:
                if existing.resolve() == resolved:
                    return
            except OSError:
                pass
        self.copy_targets.append(path)

    def emit(self, message: str = "") -> None:
        progress_observe_line(message)
        print(colorize_script_line(message), flush=True)
        if self._fh:
            self._fh.write(message + "\n")
            self._fh.flush()
        for fh in list(self._extra_fhs):
            fh.write(message + "\n")
            fh.flush()

    def write_raw(self, text: str) -> None:
        progress_observe_line(text)
        sys.stdout.write(colorize_stream_line(text))
        sys.stdout.flush()
        if self._fh:
            clean = strip_ansi(text)
            self._fh.write(clean)
            self._fh.flush()
        else:
            clean = strip_ansi(text)
        for fh in list(self._extra_fhs):
            fh.write(clean)
            fh.flush()

    @contextmanager
    def scoped_file(self, path: Path) -> Iterator[None]:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = path.open("w", encoding="utf-8", newline="")
        self._extra_fhs.append(fh)
        try:
            yield
        finally:
            try:
                self._extra_fhs.remove(fh)
            except ValueError:
                pass
            fh.close()

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None
        if self.current_log and self.current_log.exists():
            for target in self.copy_targets:
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(self.current_log, target)
                except OSError as exc:
                    print(colorize_script_line(f"[WARN] Failed to update log copy {target}: {exc}"))

    def __enter__(self) -> "TeeLog":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
def pause_on_error(code: int, *, context: str = "script") -> None:
    if code == 0:
        return
    if (
        os.environ.get("NEWENGINE_NO_PAUSE")
        or os.environ.get("CI")
        or os.environ.get("NEWENGINE_PARENT_SCRIPT")
        or os.environ.get("NEWENGINE_CONSOLE_OWNS_PAUSE")
    ):
        return
    try:
        print()
        print(colorize_script_line(f"[ERROR] {context} failed with exit code {code}."))
        print(colorize_script_line("[ERROR] Console is kept open for diagnostics. Press Enter to close..."))
        input()
    except EOFError:
        pass
def run_process(args: Sequence[str], *, cwd: Path, log: TeeLog, env: dict[str, str] | None = None) -> int:
    display = " ".join(quote_for_log(a) for a in args)
    log.emit(f"[CMD] {display}")
    try:
        process = subprocess.Popen(
            list(args),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,
        )
    except FileNotFoundError:
        log.emit(f"[ERROR] Command not found: {args[0]}")
        return 127
    assert process.stdout is not None
    last_tick = time.monotonic()
    for line in process.stdout:
        log.write_raw(line)
        now = time.monotonic()
        if now - last_tick >= 1.0:
            progress_tick()
            last_tick = now
    rc = process.wait()
    progress_tick(phase=f"process finished rc={rc}")
    return rc
def quote_for_log(arg: str) -> str:
    if not arg:
        return '""'
    if any(ch.isspace() for ch in arg) or any(ch in arg for ch in ['"', "'"]):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg
