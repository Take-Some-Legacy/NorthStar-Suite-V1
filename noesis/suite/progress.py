from __future__ import annotations

import re
from typing import Any

_CURRENT_REPORTER: Any | None = None

_FRACTION_RE = re.compile(r"(?P<current>\d+)\s*/\s*(?P<total>\d+)(?:\s+(?P<unit>[A-Za-zА-Яа-я_-]+))?(?:\s*\((?P<percent>\d+(?:\.\d+)?)%\))?")
_CARGO_COMPILING_RE = re.compile(r"^\s*Compiling\s+(?P<name>[^\s]+)")
_CARGO_FINISHED_RE = re.compile(r"^\s*Finished\s+")
_CMD_RE = re.compile(r"^\s*\[CMD\]\s+(?P<cmd>.+)")
_TAG_PHASE_RE = re.compile(r"^\s*\[(?:BUILD|CHECK|INSTALL|SYNC|CLEAN|CLEAR|TOOL|PLUGIN|STATE|INFO)\]\s+(?P<text>.+)")


def set_progress_reporter(reporter: Any | None) -> Any | None:
    global _CURRENT_REPORTER
    previous = _CURRENT_REPORTER
    _CURRENT_REPORTER = reporter
    return previous


def current_progress_reporter() -> Any | None:
    return _CURRENT_REPORTER


def progress_configure(*, total: int | None = None, current: int | None = None, unit: str = "", phase: str = "") -> None:
    reporter = _CURRENT_REPORTER
    if reporter is not None and hasattr(reporter, "configure"):
        reporter.configure(total=total, current=current, unit=unit, phase=phase)


def progress_update(*, current: int | None = None, total: int | None = None, unit: str = "", phase: str = "") -> None:
    reporter = _CURRENT_REPORTER
    if reporter is not None and hasattr(reporter, "update"):
        reporter.update(current=current, total=total, unit=unit, phase=phase)


def progress_advance(*, step: int = 1, phase: str = "") -> None:
    reporter = _CURRENT_REPORTER
    if reporter is not None and hasattr(reporter, "advance"):
        reporter.advance(step=step, phase=phase)


def progress_observe_line(line: str) -> None:
    """Feed real command output into the active suite progress reporter.

    This does not invent progress. It only converts already-known counters or
    concrete command phases into the bottom status frame. Unknown long-running
    subprocesses keep their last known phase until they report another one.
    """

    reporter = _CURRENT_REPORTER
    if reporter is None:
        return
    text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", line).strip()
    if not text:
        return

    fraction = _FRACTION_RE.search(text)
    if fraction is not None:
        current = int(fraction.group("current"))
        total = int(fraction.group("total"))
        unit = fraction.group("unit") or ""
        reporter.update(current=current, total=total, unit=unit, phase=text)
        return

    compiling = _CARGO_COMPILING_RE.match(text)
    if compiling is not None:
        reporter.update(phase=f"cargo: compiling {compiling.group('name')}")
        return

    if _CARGO_FINISHED_RE.match(text):
        reporter.update(phase="cargo: finished")
        return

    cmd = _CMD_RE.match(text)
    if cmd is not None:
        reporter.update(phase=f"cmd: {cmd.group('cmd')}")
        return

    tagged = _TAG_PHASE_RE.match(text)
    if tagged is not None:
        reporter.update(phase=tagged.group("text"))

def progress_tick(*, phase: str = "") -> None:
    reporter = _CURRENT_REPORTER
    if reporter is not None and hasattr(reporter, "tick"):
        reporter.tick(phase=phase)

