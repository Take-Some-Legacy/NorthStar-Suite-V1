from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..console import console_emit
from ..console.theme import (
    available_density_names,
    available_theme_names,
    normalize_density_name,
    normalize_theme_name,
    set_console_density,
    set_console_theme,
    DENSITIES,
    THEMES,
)
from ..console_menu import ConsoleChoice, interactive_menu_enabled, run_action_menu
from ..paths import rel, suite_path

SETTINGS_VERSION = 1


@dataclass(frozen=True)
class SuiteSettings:
    root: Path
    theme: str = "northstar-dark"
    density: str = "normal"
    show_paths: bool = True
    show_recent: bool = True
    source: str = "default"

    @property
    def path(self) -> Path:
        return settings_path(self.root)


def settings_path(root: Path) -> Path:
    return suite_path(root, "suite", "settings.json")


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "show", "visible"}:
        return True
    if text in {"0", "false", "no", "off", "hide", "hidden"}:
        return False
    return default


def _read_payload(root: Path) -> dict[str, Any]:
    path = settings_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_suite_settings(root: Path) -> SuiteSettings:
    payload = _read_payload(root)
    source = "stored" if payload else "default"
    theme_name = normalize_theme_name(payload.get("theme"))
    density_name = normalize_density_name(payload.get("density"))
    show_paths = _as_bool(payload.get("show_paths"), True)
    show_recent = _as_bool(payload.get("show_recent"), True)

    env_theme = os.environ.get("NEWENGINE_SUITE_THEME", "").strip()
    if env_theme:
        theme_name = normalize_theme_name(env_theme)
        source = "NEWENGINE_SUITE_THEME"
    env_density = os.environ.get("NEWENGINE_SUITE_DENSITY", "").strip()
    if env_density:
        density_name = normalize_density_name(env_density)
        source = "NEWENGINE_SUITE_DENSITY"
    if os.environ.get("NEWENGINE_SUITE_SHOW_PATHS"):
        show_paths = _as_bool(os.environ.get("NEWENGINE_SUITE_SHOW_PATHS"), show_paths)
        source = "NEWENGINE_SUITE_SHOW_PATHS"
    if os.environ.get("NEWENGINE_SUITE_SHOW_RECENT"):
        show_recent = _as_bool(os.environ.get("NEWENGINE_SUITE_SHOW_RECENT"), show_recent)
        source = "NEWENGINE_SUITE_SHOW_RECENT"

    return SuiteSettings(root=root, theme=theme_name, density=density_name, show_paths=show_paths, show_recent=show_recent, source=source)


def save_suite_settings(settings: SuiteSettings) -> None:
    path = settings_path(settings.root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SETTINGS_VERSION,
        "theme": normalize_theme_name(settings.theme),
        "density": normalize_density_name(settings.density),
        "show_paths": bool(settings.show_paths),
        "show_recent": bool(settings.show_recent),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_suite_settings(root: Path) -> SuiteSettings:
    settings = load_suite_settings(root)
    if not settings_path(root).exists():
        save_suite_settings(settings)
        settings = load_suite_settings(root)
    apply_suite_settings(settings)
    return settings


def apply_suite_settings(settings: SuiteSettings) -> None:
    set_console_theme(settings.theme)
    set_console_density(settings.density)
    os.environ["NEWENGINE_SUITE_SHOW_PATHS"] = "1" if settings.show_paths else "0"
    os.environ["NEWENGINE_SUITE_SHOW_RECENT"] = "1" if settings.show_recent else "0"


def _choice_detail_theme(name: str, current: SuiteSettings) -> str:
    token = THEMES[name]
    return ("active · " if name == current.theme else "") + token.detail


def _choice_detail_density(name: str, current: SuiteSettings) -> str:
    token = DENSITIES[name]
    return ("active · " if name == current.density else "") + token.detail


def _select_theme(root: Path, current: SuiteSettings) -> str | None:
    choices = [
        ConsoleChoice(value=name, number=index, label=THEMES[name].label, detail=_choice_detail_theme(name, current), marker="THEME")
        for index, name in enumerate(available_theme_names(), start=1)
    ]
    if interactive_menu_enabled():
        result = run_action_menu(
            title="Take Some() Suite — Select visual theme",
            choices=choices,
            footer="↑/↓ move  Enter select  Backspace/Esc keep current",
        )
        return None if result.cancelled else result.selected_value
    raw = input(f"Theme [{current.theme}] ({'/'.join(available_theme_names())}): ").strip().lower()
    return normalize_theme_name(raw) if raw else None


def _select_density(root: Path, current: SuiteSettings) -> str | None:
    choices = [
        ConsoleChoice(value=name, number=index, label=DENSITIES[name].label, detail=_choice_detail_density(name, current), marker="DENSITY")
        for index, name in enumerate(available_density_names(), start=1)
    ]
    if interactive_menu_enabled():
        result = run_action_menu(
            title="Take Some() Suite — Select density",
            choices=choices,
            footer="↑/↓ move  Enter select  Backspace/Esc keep current",
        )
        return None if result.cancelled else result.selected_value
    raw = input(f"Density [{current.density}] ({'/'.join(available_density_names())}): ").strip().lower()
    return normalize_density_name(raw) if raw else None


def _select_bool(title: str, current_value: bool, *, marker: str) -> bool | None:
    choices = [
        ConsoleChoice(value=True, number=1, label="Show", detail="active" if current_value else "", marker=marker),
        ConsoleChoice(value=False, number=2, label="Hide", detail="active" if not current_value else "", marker=marker),
    ]
    if interactive_menu_enabled():
        result = run_action_menu(
            title=title,
            choices=choices,
            footer="↑/↓ move  Enter select  Backspace/Esc keep current",
        )
        return None if result.cancelled else result.selected_value
    raw = input(f"{title} [{'show' if current_value else 'hide'}] show/hide: ").strip().lower()
    if not raw:
        return None
    return _as_bool(raw, current_value)


def select_suite_visual_settings(root: Path) -> int:
    current = load_suite_settings(root)
    apply_suite_settings(current)
    console_emit(f"[STATE] Theme      : {current.theme}")
    console_emit(f"[STATE] Density    : {current.density}")
    console_emit(f"[STATE] Show paths : {'yes' if current.show_paths else 'no'}")
    console_emit(f"[STATE] Show recent: {'yes' if current.show_recent else 'no'}")

    selected_theme = _select_theme(root, current) or current.theme
    interim = SuiteSettings(root=root, theme=selected_theme, density=current.density, show_paths=current.show_paths, show_recent=current.show_recent, source="operator")
    apply_suite_settings(interim)
    selected_density = _select_density(root, interim) or current.density
    interim = SuiteSettings(root=root, theme=selected_theme, density=selected_density, show_paths=current.show_paths, show_recent=current.show_recent, source="operator")
    apply_suite_settings(interim)
    show_paths = _select_bool("Take Some() Suite — Show cockpit paths", current.show_paths, marker="PATH")
    if show_paths is None:
        show_paths = current.show_paths
    show_recent = _select_bool("Take Some() Suite — Show recent actions", current.show_recent, marker="RECENT")
    if show_recent is None:
        show_recent = current.show_recent

    updated = SuiteSettings(
        root=root,
        theme=selected_theme,
        density=selected_density,
        show_paths=show_paths,
        show_recent=show_recent,
        source="operator",
    )
    save_suite_settings(updated)
    apply_suite_settings(updated)
    console_emit(f"[OK] Theme      : {updated.theme}")
    console_emit(f"[OK] Density    : {updated.density}")
    console_emit(f"[OK] Show paths : {'yes' if updated.show_paths else 'no'}")
    console_emit(f"[OK] Show recent: {'yes' if updated.show_recent else 'no'}")
    console_emit(f"[LOG] Settings saved: {rel(root, settings_path(root))}")
    return 0
