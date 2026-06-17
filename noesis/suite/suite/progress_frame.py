from __future__ import annotations

import os
import time
import sys

from ..console import (
    ANSI_BOLD,
    color_enabled,
    paint,
    strip_ansi,
)
from ..console.theme import theme
from ..progress import set_progress_reporter
from ..console.frame import terminal_height, terminal_width
from .actions import SuiteAction


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"

def render_progress_bar(
    label: str,
    state: str,
    *,
    current: int = 0,
    total: int = 1,
    unit: str = "step",
    phase: str = "",
    done: bool = False,
    failed: bool = False,
) -> str:
    cells = 26
    safe_total = max(1, int(total or 1))
    safe_current = max(0, min(safe_total, int(current or 0)))
    if done:
        safe_current = safe_total
    percent = int(round((safe_current / safe_total) * 100.0))
    fill = int(round(cells * (safe_current / safe_total)))
    if failed and safe_current <= 0:
        fill = max(1, cells // 3)
    filled = "█" * min(cells, fill)
    empty = "░" * max(0, cells - fill)
    tag = "ERROR" if failed else ("DONE" if done else "RUN")
    current = theme()
    color = current.status_error if failed else (current.status_ok if done else current.status_warn)
    counter = f"{safe_current}/{safe_total} {unit}".strip()
    phase_text = f" :: {phase}" if phase else ""
    body = f"[{filled}{empty}] {percent:3d}% {counter} — {state}: {label}{phase_text}"
    if color_enabled():
        return paint(f"[{tag}] ", color + ANSI_BOLD) + paint(body, color)
    return f"[{tag}] {body}"


class SuiteStatusFrame:
    """Bottom status frame for one suite action.

    The frame only moves when a task reports concrete progress. It is a status
    surface, not fake animation, so build/run diagnostics remain truthful.
    """

    def __init__(self, action: SuiteAction, *, scroll_top: int = 1) -> None:
        self.action = action
        self.scroll_top = max(1, int(scroll_top or 1))
        self.state = "running"
        self.done = False
        self.failed = False
        self.current = 0
        self.total = max(1, int(action.progress_total or 1))
        self.unit = action.progress_unit or "step"
        self.phase = ""
        self.started_at = time.monotonic()
        self._height = 0
        self._scroll_bottom = 0
        self._previous_reporter: object | None = None
        self._line_final_printed = False
        # The pinned bottom frame uses ANSI scroll regions and cursor restore.
        # That is clean only when this process is the only console writer.
        # Suite actions often run subprocesses/cloudflared/bridge logs in the
        # same terminal, so the safe default is append-only line logging.
        status_frame_requested = os.environ.get("NEWENGINE_SUITE_STATUS_FRAME", "").strip().lower() in {"1", "true", "yes", "on"}
        self.enabled = (
            status_frame_requested
            and sys.stdout.isatty()
            and color_enabled()
            and not os.environ.get("NEWENGINE_SUITE_NO_STATUS_FRAME")
            and not os.environ.get("CI")
        )

    def __enter__(self) -> "SuiteStatusFrame":
        self._previous_reporter = set_progress_reporter(self)
        if not self.enabled:
            print(render_progress_bar(self.action.label, self.state, current=self.current, total=self.total, unit=self.unit, phase=self.phase), flush=True)
            return self
        self._height = terminal_height()
        self._scroll_bottom = self._height - 1
        if self.scroll_top >= self._scroll_bottom:
            self.enabled = False
            print(render_progress_bar(self.action.label, self.state, current=self.current, total=self.total, unit=self.unit, phase=self.phase), flush=True)
            return self
        self._write(f"\033[{self.scroll_top};{self._scroll_bottom}r\033[{self.scroll_top};1H")
        self._draw()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        set_progress_reporter(self._previous_reporter)
        final_line = render_progress_bar(
            self.action.label,
            self.state,
            current=self.current,
            total=self.total,
            unit=self.unit,
            phase=self.phase,
            done=self.done,
            failed=self.failed,
        )
        if self.enabled:
            self._draw()
            self._write(f"\033[r\033[{self._height};1H\033[2K")
        if not self._line_final_printed:
            print(final_line, flush=True)
            self._line_final_printed = True

    def configure(self, *, total: int | None = None, current: int | None = None, unit: str = "", phase: str = "") -> None:
        if total is not None:
            self.total = max(1, int(total))
            self.current = min(self.current, self.total)
        if current is not None:
            self.current = max(0, min(self.total, int(current)))
        if unit:
            self.unit = unit
        if phase:
            self.phase = phase
        self._draw()

    def update(self, *, current: int | None = None, total: int | None = None, unit: str = "", phase: str = "") -> None:
        self.configure(total=total, current=current, unit=unit, phase=phase)

    def advance(self, *, step: int = 1, phase: str = "") -> None:
        self.current = max(0, min(self.total, self.current + int(step)))
        if phase:
            self.phase = phase
        self._draw()

    def tick(self, *, phase: str = "") -> None:
        if phase:
            self.phase = phase
        self._draw()

    def finish(self, state: str, *, failed: bool = False) -> None:
        self.state = state
        self.failed = failed
        self.done = not failed
        self.current = self.total if not failed else min(self.current, self.total)
        if self.enabled:
            self._draw()
            return
        if not self._line_final_printed:
            print(
                render_progress_bar(
                    self.action.label,
                    self.state,
                    current=self.current,
                    total=self.total,
                    unit=self.unit,
                    phase=self.phase,
                    done=self.done,
                    failed=self.failed,
                ),
                flush=True,
            )
            self._line_final_printed = True

    def _write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    def _draw(self) -> None:
        if not self.enabled:
            return
        text = render_progress_bar(
            self.action.label,
            self.state,
            current=self.current,
            total=self.total,
            unit=self.unit,
            phase=(self.phase + (" | " if self.phase else "") + f"elapsed {_format_elapsed(time.monotonic() - self.started_at)}"),
            done=self.done,
            failed=self.failed,
        )
        current_height = terminal_height()
        current_bottom = current_height - 1
        if current_height != self._height or current_bottom != self._scroll_bottom:
            self._height = current_height
            self._scroll_bottom = current_bottom
            if self.scroll_top >= self._scroll_bottom:
                self.enabled = False
                print(text, flush=True)
                return
            self._write(f"\033[{self.scroll_top};{self._scroll_bottom}r")
        width = terminal_width()
        plain = strip_ansi(text)
        if len(plain) > width - 1:
            visible = plain[: max(0, width - 2)] + "…"
            current = theme()
            text = paint(visible, current.status_error if self.failed else (current.status_ok if self.done else current.status_warn))
        self._write(f"\033[s\033[{self._height};1H\033[2K{text}\033[u")
