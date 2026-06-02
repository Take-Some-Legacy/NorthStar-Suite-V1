from __future__ import annotations

import json
from pathlib import Path

from ..console import console_emit
from ..paths import suite_path
from .actions import SuiteAction

RECENT_ACTION_LIMIT = 8


def recent_actions_file(root: Path) -> Path:
    return suite_path(root, "suite", "recent-actions.json")


def load_recent_action_keys(root: Path, known: dict[str, SuiteAction]) -> list[str]:
    path = recent_actions_file(root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw = payload.get("recent_actions") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        if item not in known or item in seen:
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= RECENT_ACTION_LIMIT:
            break
    return result


def save_recent_action_keys(root: Path, keys: list[str], *, suite_version: str) -> None:
    path = recent_actions_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"suite_version": suite_version, "recent_actions": keys[:RECENT_ACTION_LIMIT]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record_recent_action(root: Path, action: SuiteAction, known: dict[str, SuiteAction], *, suite_version: str) -> None:
    keys = [action.key]
    keys.extend(key for key in load_recent_action_keys(root, known) if key != action.key)
    try:
        save_recent_action_keys(root, keys, suite_version=suite_version)
    except OSError as exc:
        console_emit(f"[WARN] Could not update recent actions: {exc}")


def recent_actions(root: Path, known: dict[str, SuiteAction]) -> list[SuiteAction]:
    return [known[key] for key in load_recent_action_keys(root, known) if key in known]
