from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from ..paths import engine_core_root
from .suite_action_registry import SuiteActionRegistry, discover_suite_actions


_TAG_BY_GROUP = {
    "Build": "BUILD",
    "Run": "RUN",
    "Workspace": "CLEAN",
    "Diagnostics": "DIAG",
    "Tools": "TOOLS",
    "Source": "PACK",
    "Importers": "IMPORT",
    "Java": "JAVA",
}

_TAG_BY_DOMAIN = {
    "lang": "LANG",
    "NorthStarEngine": "NORTHSTAR ENGINE",
    "system": "SYSTEM",
    "suite": "SUITE",
    "tools": "TOOLS",
    "vendor": "VENDOR",
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
    for action in sorted(registry.actions, key=lambda item: (_target_domain(item), item.action_id)):
        if not action.safe_for_menu:
            continue
        domain = _domain_from_descriptor_path(action.descriptor_path)
        target_domain = _target_domain(action)
        tag = _TAG_BY_DOMAIN.get(domain, _TAG_BY_GROUP.get(action.group, "ACTION"))
        command_line = " ".join([action.command, *action.args]).strip()
        chips = _domain_chips(target_domain) + [action.group.lower()]
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
                "category": domain.lower() if domain else action.group.lower(),
                "target_domain": target_domain.lower() if target_domain else action.group.lower(),
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
    output_path = output_path or engine_core_root(repo_root) / "buildInfo" / "tools" / "SUITE_ACTIONS_BRIDGE_MENU.json"
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
        if arg in {"dev", "debug", "release", "gradle", "maven", "auto"}:
            return arg
    return ""


def _domain_from_descriptor_path(descriptor_path: str) -> str:
    taxonomy = _descriptor_taxonomy(descriptor_path)
    return taxonomy[0] if taxonomy else ""


def _target_domain(action: Any) -> str:
    taxonomy = _descriptor_taxonomy(action.descriptor_path)
    if not taxonomy:
        return action.group
    return "/".join(taxonomy)


def _descriptor_taxonomy(descriptor_path: str) -> tuple[str, ...]:
    parts = Path(descriptor_path).as_posix().split("/")
    try:
        index = parts.index("actions") + 1
    except ValueError:
        return ()
    taxonomy = [part for part in parts[index:-1] if part]
    return tuple(taxonomy)


def _domain_chips(target_domain: str) -> list[str]:
    return [part.lower() for part in target_domain.split("/") if part]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
