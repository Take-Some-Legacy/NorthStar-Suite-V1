from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .suite_action_registry import SuiteActionRegistry, discover_suite_actions


_TAG_BY_GROUP = {
    "Build": "BUILD",
    "Run": "RUN",
    "Workspace": "CLEAN",
    "Diagnostics": "DIAG",
    "Tools": "TOOLS",
    "Source": "PACK",
    "Importers": "IMPORT",
}


_RISK_BY_DANGER = {
    "normal": "safe",
    "destructive": "writes_workspace",
    "manual": "manual_review",
    "unsafe": "unsafe",
}


def render_bridge_menu_actions(registry: SuiteActionRegistry) -> list[dict[str, Any]]:
    """Convert descriptor actions into the bounded Suite/bridge list-actions shape.

    The bridge UI should consume this instead of hardcoding action buttons.  The
    output intentionally keeps legacy field names (`key`, `label`, `detail`) so
    existing UI code can migrate without changing its rendering model.
    """

    actions: list[dict[str, Any]] = []
    for action in sorted(registry.actions, key=lambda item: (item.group, item.action_id)):
        if not action.safe_for_menu:
            continue
        tag = _TAG_BY_GROUP.get(action.group, "ACTION")
        command_line = " ".join([action.command, *action.args]).strip()
        chips = [action.group.lower()]
        if action.requires_workspace:
            chips.extend(action.requires_workspace)
        if action.requires_tools:
            chips.extend(action.requires_tools)
        actions.append(
            {
                "key": action.action_id,
                "label": action.title,
                "detail": action.description or command_line,
                "primary_tag": tag,
                "category": action.group.lower(),
                "target_domain": action.group.lower(),
                "risk_level": _RISK_BY_DANGER.get(action.danger_level, action.danger_level),
                "profile": _profile_from_args(action.args),
                "chips": _dedupe(chips),
                "progress_total": 1,
                "progress_unit": "step",
                "output_schema": action.metadata.get("output_schema"),
                "output_mode": action.metadata.get("output_mode", "process_exit"),
                "command": action.command,
                "args": list(action.args),
                "outputs": list(action.outputs),
                "descriptor_path": action.descriptor_path,
            }
        )
    return actions


def write_bridge_menu_json(repo_root: Path, output_path: Path | None = None) -> Path:
    registry = discover_suite_actions(repo_root)
    output_path = output_path or repo_root / "NewEngine" / "neocore2" / "buildInfo" / "tools" / "SUITE_ACTIONS_BRIDGE_MENU.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "northstar.suite.bridge_menu_actions.v1",
        "ok": registry.ok,
        "source": "tools/suite/actions/*.json",
        "action_count": len(registry.actions),
        "menu_action_count": len([action for action in registry.actions if action.safe_for_menu]),
        "actions": render_bridge_menu_actions(registry),
        "validation": [item.as_dict() for item in registry.validation],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def _profile_from_args(args: tuple[str, ...]) -> str:
    for arg in args:
        if arg in {"dev", "debug", "release"}:
            return arg
    return ""


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
