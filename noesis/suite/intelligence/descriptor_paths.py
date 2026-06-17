from __future__ import annotations

from pathlib import Path

def suite_action_descriptor_path(root: Path, category: str, action_id: str) -> Path:
    safe_category = category.strip().replace(chr(92), "/").strip("/")
    safe_action_id = action_id.strip()
    return root / "tools" / "suite" / "actions" / safe_category / f"{safe_action_id}.json"

def suite_action_descriptor_relpath(category: str, action_id: str) -> str:
    safe_category = category.strip().replace(chr(92), "/").strip("/")
    safe_action_id = action_id.strip()
    return "/".join(["tools", "suite", "actions", safe_category, f"{safe_action_id}.json"])
