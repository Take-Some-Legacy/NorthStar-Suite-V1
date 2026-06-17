from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .tags import compact_chips, risk_label

SuiteRunner = Callable[[Path], int]


@dataclass(frozen=True)
class SuiteCategory:
    """A visible suite block in the command center."""

    key: str
    label: str
    detail: str
    marker: str


@dataclass(frozen=True)
class SuiteAction:
    """Descriptor for one operator-facing suite command.

    The leading tag is command taxonomy: what this command does. Chips explain
    where it operates, which profile it targets, and how risky it is. The actual
    implementation stays behind `run`, so command discovery and command intent
    are no longer hardcoded into the shell renderer.
    """

    key: str
    label: str
    detail: str
    run: SuiteRunner
    primary_tag: str
    category: str
    target_domain: str
    risk_level: str = "readonly"
    profile: str = ""
    progress_total: int = 1
    progress_unit: str = "step"
    output_schema: str | None = None
    output_mode: str = "process_exit"

    @property
    def marker(self) -> str:
        return self.primary_tag

    @property
    def risk_label(self) -> str:
        return risk_label(self.risk_level)

    def chips(self) -> tuple[str, ...]:
        return compact_chips(self.target_domain, self.profile, self.risk_label)

    def operator_detail(self) -> str:
        chips = " · ".join(self.chips())
        return chips or self.detail
