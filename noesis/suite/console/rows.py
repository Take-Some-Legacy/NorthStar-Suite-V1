from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from .ansi import strip_ansi
from .tags import render_tag

T = TypeVar("T")


@dataclass(frozen=True)
class ConsoleChoice(Generic[T]):
    """One selectable row in a pseudo-console menu."""

    value: T
    number: int | None
    label: str
    detail: str = ""
    checked: bool = False
    marker: str = ""


@dataclass(frozen=True)
class ConsoleMenuOption:
    """One non-selectable command option shown above selectable entries."""

    action: str
    key: str
    label: str
    detail: str = ""


@dataclass(frozen=True)
class ConsoleMultiSelectResult(Generic[T]):
    selected_values: list[T]
    special: str = ""


@dataclass(frozen=True)
class ConsoleActionMenuResult(Generic[T]):
    selected_value: T | None
    cancelled: bool = False


@dataclass(frozen=True)
class ConsoleConfirmResult:
    confirmed: bool
    cancelled: bool = False


def choice_marker_width(choices: list[ConsoleChoice[T]]) -> int:
    return max((len(strip_ansi(choice.marker.strip())) for choice in choices if choice.marker.strip()), default=0)


def choice_marker(choice: ConsoleChoice[T], *, width: int = 0) -> str:
    marker = render_tag(choice.marker, width=width)
    return f"{marker} " if marker else ""
