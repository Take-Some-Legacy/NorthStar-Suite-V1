from __future__ import annotations

import os
from dataclasses import dataclass

from .ansi import (
    ANSI_BOLD,
    ANSI_BLUE,
    ANSI_BRIGHT_BLUE,
    ANSI_BRIGHT_CYAN,
    ANSI_BRIGHT_GREEN,
    ANSI_BRIGHT_MAGENTA,
    ANSI_BRIGHT_RED,
    ANSI_BRIGHT_WHITE,
    ANSI_BRIGHT_YELLOW,
    ANSI_CYAN,
    ANSI_DARK_GRAY,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_MAGENTA,
    ANSI_RED,
    ANSI_YELLOW,
)


@dataclass(frozen=True)
class DensityTokens:
    name: str
    label: str
    detail: str
    banner_max_width: int
    action_reserved_lines: int
    dual_reserved_lines: int
    multiselect_reserved_lines: int
    path_mode: str


@dataclass(frozen=True)
class ConsoleTheme:
    name: str
    label: str
    detail: str
    border_primary: str
    border_muted: str
    text_primary: str
    text_muted: str
    text_heading: str
    status_ok: str
    status_warn: str
    status_error: str
    status_info: str
    status_menu: str
    selected_bg: str
    selected_fg: str
    action_bg: str
    action_fg: str
    tag_palette: dict[str, str]
    tag_fallback_palette: tuple[str, ...]
    risk_palette: dict[str, str]


_BASE_TAGS = {
    "ERROR": "status_error_bold",
    "WARN": "status_warn_bold",
    "OK": "status_ok_bold",
    "INFO": "status_info",
    "CHECK": "blue",
    "STATE": "magenta",
    "BUILD": "blue_bold",
    "CMD": "cyan_bold",
    "LOG": "muted",
    "MIGRATE": "magenta_bold",
    "DELETE": "status_error",
    "CLEAN": "yellow",
    "SKIP": "muted",
    "INSTALL": "status_ok",
    "DONE": "status_ok_bold",
    "PATH": "status_info",
    "RESULT": "status_ok",
    "EXIT": "status_warn_bold",
    "SYNC": "blue_bold",
    "PLUGIN": "magenta_bold",
    "STALE": "status_warn_bold",
    "UP-TO-DATE": "status_ok_bold",
    "PATCH": "magenta",
    "MOVE": "yellow",
    "TOOL": "status_info",
    "TOOLS": "status_info_bold",
    "MENU": "blue_bold",
    "GIT": "green_bold",
    "DOC": "magenta_bold",
    "DIAG": "status_info_bold",
    "PACK": "magenta_bold",
    "MISSION": "status_warn_bold",
    "FIX": "status_error_bold",
    "RUN": "status_warn_bold",
    "STATUS": "status_info_bold",
    "CACHE": "yellow_bold",
    "TARGET": "cyan_bold",
    "FULL": "status_error_bold",
    "PUSH": "green_bold",
    "REG": "blue_bold",
    "DEV": "blue_bold",
    "DEBUG": "status_info_bold",
    "REL": "magenta_bold",
    "RELEASE": "magenta_bold",
    "PROFILE": "status_info_bold",
    "PLATFORM": "magenta_bold",
    "SELECT": "green_bold",
    "FORCE": "status_error_bold",
    "CODEC": "magenta_bold",
    "IMP": "cyan_bold",
    "IMPORT": "cyan_bold",
    "SCAN": "blue_bold",
    "VALID": "green_bold",
    "INDEX": "blue_bold",
    "DEEP": "magenta_bold",
    "BUNDLE": "status_info_bold",
    "SAFE": "green_bold",
    "QA": "status_warn_bold",
    "PIPE": "cyan_bold",
    "ZIP": "magenta_bold",
    "RUNGAME": "status_info",
    "PACK-SOURCE": "magenta",
    "PACK_SOURCE": "magenta",
}


def _style_map(*, muted: str = ANSI_DIM) -> dict[str, str]:
    return {
        "status_error": ANSI_BRIGHT_RED,
        "status_error_bold": ANSI_BRIGHT_RED + ANSI_BOLD,
        "status_warn": ANSI_BRIGHT_YELLOW,
        "status_warn_bold": ANSI_BRIGHT_YELLOW + ANSI_BOLD,
        "status_ok": ANSI_BRIGHT_GREEN,
        "status_ok_bold": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "status_info": ANSI_BRIGHT_CYAN,
        "status_info_bold": ANSI_BRIGHT_CYAN + ANSI_BOLD,
        "blue": ANSI_BRIGHT_BLUE,
        "blue_bold": ANSI_BRIGHT_BLUE + ANSI_BOLD,
        "green": ANSI_BRIGHT_GREEN,
        "green_bold": ANSI_BRIGHT_GREEN + ANSI_BOLD,
        "yellow": ANSI_YELLOW,
        "yellow_bold": ANSI_YELLOW + ANSI_BOLD,
        "magenta": ANSI_BRIGHT_MAGENTA,
        "magenta_bold": ANSI_BRIGHT_MAGENTA + ANSI_BOLD,
        "cyan": ANSI_CYAN,
        "cyan_bold": ANSI_CYAN + ANSI_BOLD,
        "muted": muted,
    }


def _tag_palette(style_map: dict[str, str]) -> dict[str, str]:
    return {tag: style_map.get(style, style_map["status_info"]) for tag, style in _BASE_TAGS.items()}


_NORTHSTAR_STYLE_MAP = _style_map()
_AMBER_STYLE_MAP = _style_map(muted=ANSI_DARK_GRAY)

THEMES: dict[str, ConsoleTheme] = {
    "northstar-dark": ConsoleTheme(
        name="northstar-dark",
        label="North Star Dark",
        detail="cyan borders, bright status colors, default operator theme",
        border_primary=ANSI_BRIGHT_CYAN + ANSI_BOLD,
        border_muted=ANSI_CYAN,
        text_primary=ANSI_BRIGHT_WHITE,
        text_muted=ANSI_DIM,
        text_heading=ANSI_BRIGHT_WHITE + ANSI_BOLD,
        status_ok=ANSI_BRIGHT_GREEN,
        status_warn=ANSI_BRIGHT_YELLOW,
        status_error=ANSI_BRIGHT_RED,
        status_info=ANSI_BRIGHT_CYAN,
        status_menu=ANSI_BRIGHT_BLUE + ANSI_BOLD,
        selected_bg="\033[44m",
        selected_fg=ANSI_BRIGHT_WHITE,
        action_bg="\033[42m",
        action_fg="\033[30m",
        tag_palette=_tag_palette(_NORTHSTAR_STYLE_MAP),
        tag_fallback_palette=(
            ANSI_BRIGHT_BLUE,
            ANSI_BRIGHT_GREEN,
            ANSI_BRIGHT_YELLOW,
            ANSI_BRIGHT_MAGENTA,
            ANSI_BRIGHT_CYAN,
            ANSI_BLUE,
            ANSI_GREEN,
            ANSI_YELLOW,
            ANSI_MAGENTA,
            ANSI_CYAN,
        ),
        risk_palette={
            "readonly": ANSI_DIM,
            "diagnostics": ANSI_BRIGHT_CYAN,
            "writes_cache": ANSI_YELLOW,
            "writes_reports": ANSI_BRIGHT_CYAN,
            "writes_zip": ANSI_BRIGHT_MAGENTA,
            "writes_runtime_plugins": ANSI_BRIGHT_YELLOW,
            "writes_runtime_codecs": ANSI_BRIGHT_YELLOW,
            "writes_tools": ANSI_BRIGHT_MAGENTA,
            "destructive_cleanup": ANSI_BRIGHT_RED + ANSI_BOLD,
            "force_rebuild": ANSI_BRIGHT_RED + ANSI_BOLD,
            "runs_process": ANSI_BRIGHT_YELLOW + ANSI_BOLD,
            "mutates_git": ANSI_BRIGHT_GREEN + ANSI_BOLD,
            "migration": ANSI_BRIGHT_MAGENTA + ANSI_BOLD,
        },
    ),
    "northstar-amber": ConsoleTheme(
        name="northstar-amber",
        label="North Star Amber",
        detail="warmer warning-forward palette for long maintenance sessions",
        border_primary=ANSI_BRIGHT_YELLOW + ANSI_BOLD,
        border_muted=ANSI_YELLOW,
        text_primary=ANSI_BRIGHT_WHITE,
        text_muted=ANSI_DARK_GRAY,
        text_heading=ANSI_BRIGHT_WHITE + ANSI_BOLD,
        status_ok=ANSI_BRIGHT_GREEN,
        status_warn=ANSI_BRIGHT_YELLOW,
        status_error=ANSI_BRIGHT_RED,
        status_info=ANSI_BRIGHT_YELLOW,
        status_menu=ANSI_BRIGHT_YELLOW + ANSI_BOLD,
        selected_bg="\033[43m",
        selected_fg="\033[30m",
        action_bg="\033[42m",
        action_fg="\033[30m",
        tag_palette=_tag_palette(_AMBER_STYLE_MAP),
        tag_fallback_palette=(
            ANSI_BRIGHT_YELLOW,
            ANSI_YELLOW,
            ANSI_BRIGHT_GREEN,
            ANSI_BRIGHT_MAGENTA,
            ANSI_BRIGHT_CYAN,
            ANSI_GREEN,
            ANSI_MAGENTA,
            ANSI_CYAN,
        ),
        risk_palette={
            "readonly": ANSI_DARK_GRAY,
            "diagnostics": ANSI_BRIGHT_YELLOW,
            "writes_cache": ANSI_YELLOW,
            "writes_reports": ANSI_BRIGHT_CYAN,
            "writes_zip": ANSI_BRIGHT_MAGENTA,
            "writes_runtime_plugins": ANSI_BRIGHT_YELLOW + ANSI_BOLD,
            "writes_runtime_codecs": ANSI_BRIGHT_YELLOW + ANSI_BOLD,
            "writes_tools": ANSI_BRIGHT_MAGENTA,
            "destructive_cleanup": ANSI_BRIGHT_RED + ANSI_BOLD,
            "force_rebuild": ANSI_BRIGHT_RED + ANSI_BOLD,
            "runs_process": ANSI_BRIGHT_YELLOW + ANSI_BOLD,
            "mutates_git": ANSI_BRIGHT_GREEN + ANSI_BOLD,
            "migration": ANSI_BRIGHT_MAGENTA + ANSI_BOLD,
        },
    ),
}

DENSITIES: dict[str, DensityTokens] = {
    "compact": DensityTokens(
        name="compact",
        label="Compact",
        detail="more rows, shorter cockpit, fewer path details",
        banner_max_width=104,
        action_reserved_lines=6,
        dual_reserved_lines=7,
        multiselect_reserved_lines=8,
        path_mode="compact",
    ),
    "normal": DensityTokens(
        name="normal",
        label="Normal",
        detail="balanced cockpit and command rows",
        banner_max_width=132,
        action_reserved_lines=7,
        dual_reserved_lines=8,
        multiselect_reserved_lines=9,
        path_mode="normal",
    ),
    "wide": DensityTokens(
        name="wide",
        label="Wide",
        detail="more readable cockpit and wider rows on large terminals",
        banner_max_width=156,
        action_reserved_lines=8,
        dual_reserved_lines=9,
        multiselect_reserved_lines=10,
        path_mode="wide",
    ),
}

_ACTIVE_THEME = "northstar-dark"
_ACTIVE_DENSITY = "normal"


def normalize_theme_name(value: str | None) -> str:
    name = str(value or "").strip().lower()
    return name if name in THEMES else "northstar-dark"


def normalize_density_name(value: str | None) -> str:
    name = str(value or "").strip().lower()
    return name if name in DENSITIES else "normal"


def set_console_theme(name: str | None) -> None:
    global _ACTIVE_THEME
    _ACTIVE_THEME = normalize_theme_name(name)
    os.environ["NEWENGINE_SUITE_THEME"] = _ACTIVE_THEME


def set_console_density(name: str | None) -> None:
    global _ACTIVE_DENSITY
    _ACTIVE_DENSITY = normalize_density_name(name)
    os.environ["NEWENGINE_SUITE_DENSITY"] = _ACTIVE_DENSITY


def active_theme_name() -> str:
    return normalize_theme_name(os.environ.get("NEWENGINE_SUITE_THEME") or _ACTIVE_THEME)


def active_density_name() -> str:
    return normalize_density_name(os.environ.get("NEWENGINE_SUITE_DENSITY") or _ACTIVE_DENSITY)


def theme() -> ConsoleTheme:
    return THEMES[active_theme_name()]


def density() -> DensityTokens:
    return DENSITIES[active_density_name()]


def available_theme_names() -> tuple[str, ...]:
    return tuple(THEMES.keys())


def available_density_names() -> tuple[str, ...]:
    return tuple(DENSITIES.keys())
