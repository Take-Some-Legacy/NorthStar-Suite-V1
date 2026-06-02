from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import subprocess
import sys

from .actions import SuiteAction, SuiteCategory
from .recent import recent_actions, record_recent_action
from ..registry.suite_action_registry import discover_suite_actions
from ..registry.suite_bridge_menu import render_bridge_menu_actions


@dataclass(frozen=True)
class SuiteRegistry:
    """Authoritative descriptor registry for suite command discovery.

    The shell reads Suite actions from `tools/suite/actions/*.json`.  It must not
    keep a parallel hardcoded action table.
    """

    categories: tuple[SuiteCategory, ...]
    actions_by_category: dict[str, tuple[SuiteAction, ...]]
    _actions_by_key: dict[str, SuiteAction] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        category_keys = [category.key for category in self.categories]
        duplicate_categories = _duplicates(category_keys)
        if duplicate_categories:
            raise ValueError(f"duplicate suite categories: {', '.join(duplicate_categories)}")

        valid_categories = set(category_keys)
        action_map: dict[str, SuiteAction] = {}
        for category_key, actions in self.actions_by_category.items():
            if category_key not in valid_categories:
                raise ValueError(f"suite action group references unknown category: {category_key}")
            for action in actions:
                if not action.key:
                    raise ValueError(f"suite action in category {category_key} has empty key")
                if not action.primary_tag:
                    raise ValueError(f"suite action {action.key} has empty primary_tag")
                if action.category != category_key:
                    raise ValueError(
                        f"suite action {action.key} is stored under {category_key} "
                        f"but declares category {action.category}"
                    )
                if action.key in action_map:
                    raise ValueError(f"duplicate suite action key: {action.key}")
                action_map[action.key] = action
        object.__setattr__(self, "_actions_by_key", action_map)

    def command_blocks(self) -> tuple[SuiteCategory, ...]:
        return self.categories

    def category_actions(self, category_key: str) -> tuple[SuiteAction, ...]:
        return self.actions_by_category.get(category_key, ())

    def actions(self) -> tuple[SuiteAction, ...]:
        result: list[SuiteAction] = []
        for category in self.categories:
            result.extend(self.category_actions(category.key))
        return tuple(result)

    def by_key(self) -> dict[str, SuiteAction]:
        return dict(self._actions_by_key)

    def action(self, key: str) -> SuiteAction | None:
        return self._actions_by_key.get(key)

    def recent(self, root: Path) -> tuple[SuiteAction, ...]:
        return tuple(recent_actions(root, self._actions_by_key))

    def record_recent(self, root: Path, action: SuiteAction, *, suite_version: str) -> None:
        record_recent_action(root, action, self._actions_by_key, suite_version=suite_version)

    def run(self, root: Path, action: SuiteAction) -> int:
        return int(action.run(root))


def build_suite_registry(root: Path) -> SuiteRegistry:
    descriptor_registry = discover_suite_actions(root)
    actions = render_bridge_menu_actions(descriptor_registry)
    categories: list[SuiteCategory] = []
    actions_by_category: dict[str, list[SuiteAction]] = {}
    seen_categories: set[str] = set()

    for action_data in actions:
        category_key = str(action_data.get("category") or "actions")
        if category_key not in seen_categories:
            seen_categories.add(category_key)
            categories.append(
                SuiteCategory(
                    key=category_key,
                    label=_category_label(category_key),
                    detail=f"Descriptor-backed {category_key} actions",
                    marker=str(action_data.get("primary_tag") or "ACTION"),
                )
            )
        actions_by_category.setdefault(category_key, []).append(_suite_action_from_bridge_data(action_data))

    return SuiteRegistry(
        categories=tuple(categories),
        actions_by_category={key: tuple(value) for key, value in actions_by_category.items()},
    )


def _suite_action_from_bridge_data(action_data: dict[str, object]) -> SuiteAction:
    key = str(action_data.get("key") or "")
    command = str(action_data.get("command") or "")
    args = tuple(str(arg) for arg in action_data.get("args", []) if str(arg))
    category = str(action_data.get("category") or "actions")

    return SuiteAction(
        key=key,
        label=str(action_data.get("label") or key),
        detail=str(action_data.get("detail") or command),
        run=_command_runner(command, args),
        primary_tag=str(action_data.get("primary_tag") or "ACTION"),
        category=category,
        target_domain=str(action_data.get("target_domain") or category),
        risk_level=str(action_data.get("risk_level") or "readonly"),
        profile=str(action_data.get("profile") or ""),
        progress_total=int(action_data.get("progress_total") or 1),
        progress_unit=str(action_data.get("progress_unit") or "step"),
        output_schema=action_data.get("output_schema") if isinstance(action_data.get("output_schema"), str) else None,
        output_mode=str(action_data.get("output_mode") or "process_exit"),
    )


def _command_runner(command: str, args: tuple[str, ...]):
    def run(root: Path) -> int:
        if not command:
            print("[ERROR] Suite action has no command.")
            return 2
        cmd = [sys.executable, str(root / "tools" / "scripts" / "takesome.py"), command, *args]
        completed = subprocess.run(cmd, cwd=root)
        return int(completed.returncode)

    return run


def _category_label(category_key: str) -> str:
    return category_key.replace("_", " ").replace("-", " ").title()


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicate: list[str] = []
    for value in values:
        if value in seen and value not in duplicate:
            duplicate.append(value)
        seen.add(value)
    return duplicate
