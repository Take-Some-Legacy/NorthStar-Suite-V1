from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..console import console_emit
from ..console_menu import ConsoleChoice, interactive_menu_enabled, run_action_menu
from ..paths import rel, suite_path
from ..platforms import BuildPlatform, available_build_platforms, normalize_build_platform

VALID_SUITE_PROFILES = ("dev", "debug", "release")
CONTEXT_VERSION = 1


@dataclass(frozen=True)
class SuiteContext:
    """Global suite execution context selected by the operator."""

    root: Path
    profile: str
    platform: BuildPlatform
    source: str = "default"

    @property
    def platform_id(self) -> str:
        return self.platform.id

    def build_args(self) -> list[str]:
        return [self.profile, "--platform", self.platform.id]

    def with_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["NEWENGINE_BUILD_PROFILE"] = self.profile
        env["NEWENGINE_BUILD_TYPE"] = self.profile
        env["NEWENGINE_PLUGIN_BUILD_TYPE"] = self.profile
        env["NEWENGINE_RUN_PROFILE"] = self.profile
        env["NEWENGINE_BUILD_PLATFORM"] = self.platform.id
        env["NEWENGINE_PLUGIN_BUILD_PLATFORM"] = self.platform.id
        return env


def _context_path(root: Path) -> Path:
    return suite_path(root, "suite", "context.json")


def _read_context_payload(root: Path) -> dict[str, Any]:
    path = _context_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_profile(raw: object) -> str:
    value = str(raw or "").strip().lower()
    return value if value in VALID_SUITE_PROFILES else "dev"


def load_suite_context(root: Path) -> SuiteContext:
    payload = _read_context_payload(root)
    stored_profile = _normalize_profile(payload.get("active_profile", ""))
    stored_platform = normalize_build_platform(str(payload.get("active_platform", "") or ""))
    source = "stored" if payload else "default"

    env_profile = ""
    for key in ("NEWENGINE_SUITE_PROFILE", "NEWENGINE_BUILD_PROFILE", "NEWENGINE_PLUGIN_BUILD_TYPE", "NEWENGINE_BUILD_TYPE"):
        value = os.environ.get(key, "").strip().lower()
        if value in VALID_SUITE_PROFILES:
            env_profile = value
            source = key
            break
    profile = env_profile or stored_profile

    env_platform = ""
    for key in ("NEWENGINE_SUITE_PLATFORM", "NEWENGINE_BUILD_PLATFORM", "NEWENGINE_PLUGIN_BUILD_PLATFORM"):
        value = os.environ.get(key, "").strip()
        if value:
            env_platform = value
            source = key
            break
    platform = normalize_build_platform(env_platform or stored_platform.id)
    return SuiteContext(root=root, profile=profile, platform=platform, source=source)


def save_suite_context(context: SuiteContext) -> None:
    path = _context_path(context.root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CONTEXT_VERSION,
        "active_profile": context.profile,
        "active_platform": context.platform.id,
        "platform_label": context.platform.label,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def context_build_args(root: Path) -> list[str]:
    return load_suite_context(root).build_args()


def context_profile_args(root: Path) -> list[str]:
    context = load_suite_context(root)
    return [context.profile]


def context_platform_args(root: Path) -> list[str]:
    context = load_suite_context(root)
    return ["--platform", context.platform.id]


def _select_profile(root: Path, current: SuiteContext) -> str | None:
    choices = [
        ConsoleChoice(value=profile, number=index, label=profile, detail=("active" if profile == current.profile else ""), marker="PROFILE")
        for index, profile in enumerate(VALID_SUITE_PROFILES, start=1)
    ]
    if interactive_menu_enabled():
        result = run_action_menu(
            title="Take Some() Suite — Select active profile",
            choices=choices,
            footer="↑/↓ move  Enter select  Backspace/Esc keep current",
        )
        return None if result.cancelled else result.selected_value
    raw = input(f"Active profile [{current.profile}] dev/debug/release: ").strip().lower()
    if not raw:
        return None
    if raw in VALID_SUITE_PROFILES:
        return raw
    console_emit(f"[WARN] Unknown profile: {raw}")
    return None


def _select_platform(root: Path, current: SuiteContext) -> BuildPlatform | None:
    platforms = available_build_platforms()
    choices = [
        ConsoleChoice(
            value=platform,
            number=index,
            label=platform.id,
            detail=("active · " if platform.id == current.platform.id else "") + platform.detail,
            marker="PLATFORM",
        )
        for index, platform in enumerate(platforms, start=1)
    ]
    if interactive_menu_enabled():
        result = run_action_menu(
            title="Take Some() Suite — Select active platform",
            choices=choices,
            footer="↑/↓ move  Enter select  Backspace/Esc keep current",
        )
        return None if result.cancelled else result.selected_value
    raw = input(f"Active platform [{current.platform.id}] host/windows-x64-msvc/etc: ").strip()
    if not raw:
        return None
    return normalize_build_platform(raw)


def select_suite_context(root: Path) -> int:
    current = load_suite_context(root)
    console_emit(f"[STATE] Active profile : {current.profile}")
    console_emit(f"[STATE] Active platform: {current.platform.id}")
    profile = _select_profile(root, current) or current.profile
    interim = SuiteContext(root=root, profile=profile, platform=current.platform, source="operator")
    platform = _select_platform(root, interim) or current.platform
    updated = SuiteContext(root=root, profile=profile, platform=platform, source="operator")
    save_suite_context(updated)
    console_emit(f"[OK] Active profile : {updated.profile}")
    console_emit(f"[OK] Active platform: {updated.platform.id}")
    console_emit(f"[LOG] Context saved: {rel(root, _context_path(root))}")
    return 0
