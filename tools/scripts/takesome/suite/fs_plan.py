from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLAN_PATH = Path(".takesome/filesystem/operations.json")
REPORT_DIR = Path(".takesome/filesystem/reports")
ALLOWED_PLAN_ACTIONS = ("mkdir", "copy", "move", "archive_zip", "extract_zip")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _report(root: Path, name: str, payload: dict[str, Any]) -> Path:
    out_dir = root / REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}-{_stamp()}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] filesystem report: {path}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def _inside_root(root: Path, raw: str) -> tuple[bool, str]:
    text = str(raw or "").strip().strip('"')
    if not text:
        return False, "empty path"
    path = (Path(text) if Path(text).is_absolute() else root / text).resolve()
    try:
        rel = path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return False, f"path escapes workspace root: {text}"
    return True, rel


def filesystem_status(root: Path) -> int:
    payload = {
        "schema": "northstar.filesystem.status.v1",
        "ok": True,
        "workspace_root": str(root),
        "default_plan": PLAN_PATH.as_posix(),
        "reports": REPORT_DIR.as_posix(),
        "allowed_plan_actions": list(ALLOWED_PLAN_ACTIONS),
        "policy": {
            "phase": "plan_only",
            "root_bound": True,
            "executes_operations": False,
            "apply_requires_owner_authority": True,
            "risk_labels_are_not_hidden": True
        }
    }
    _report(root, "status", payload)
    return 0


def _validate_operation(root: Path, index: int, op: Any) -> dict[str, Any]:
    if not isinstance(op, dict):
        return {"ok": False, "index": index, "error": "operation must be object"}
    action = str(op.get("action", "")).strip()
    result: dict[str, Any] = {"ok": True, "index": index, "action": action, "paths": []}
    if action not in ALLOWED_PLAN_ACTIONS:
        return {"ok": False, "index": index, "action": action, "error": "unsupported action"}
    fields = {
        "mkdir": ("path",),
        "copy": ("src", "dst"),
        "move": ("src", "dst"),
        "archive_zip": ("output",),
        "extract_zip": ("archive", "dest"),
    }[action]
    for field in fields:
        ok, detail = _inside_root(root, str(op.get(field, "")))
        result["paths"].append({"field": field, "ok": ok, "path": detail})
        if not ok:
            result["ok"] = False
    if action == "archive_zip":
        sources = op.get("sources", [])
        if not isinstance(sources, list) or not sources:
            result["ok"] = False
            result["error"] = "archive_zip requires non-empty sources[]"
        else:
            for source in sources:
                ok, detail = _inside_root(root, str(source))
                result["paths"].append({"field": "sources[]", "ok": ok, "path": detail})
                if not ok:
                    result["ok"] = False
    return result


def filesystem_plan(root: Path) -> int:
    plan_file = root / PLAN_PATH
    if not plan_file.exists():
        payload = {
            "schema": "northstar.filesystem.plan.v1",
            "ok": False,
            "plan": PLAN_PATH.as_posix(),
            "error": "plan file does not exist",
            "template": {
                "schema": "northstar.filesystem.operations.v1",
                "operations": []
            }
        }
        _report(root, "plan", payload)
        return 1
    try:
        data = json.loads(plan_file.read_text(encoding="utf-8"))
        operations = data.get("operations", [])
        if not isinstance(operations, list):
            raise ValueError("operations must be a list")
        results = [_validate_operation(root, i, op) for i, op in enumerate(operations)]
        payload = {
            "schema": "northstar.filesystem.plan.v1",
            "ok": all(item.get("ok") for item in results),
            "plan": PLAN_PATH.as_posix(),
            "operation_count": len(results),
            "executes_operations": False,
            "results": results
        }
    except Exception as exc:
        payload = {"schema": "northstar.filesystem.plan.v1", "ok": False, "plan": PLAN_PATH.as_posix(), "error": str(exc)}
    _report(root, "plan", payload)
    return 0 if payload.get("ok") else 1
