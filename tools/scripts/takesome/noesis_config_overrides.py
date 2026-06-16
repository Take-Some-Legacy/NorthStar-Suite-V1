from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import runpy
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List

RULES_PATH = Path("tools/scripts/takesome/rules/noesis-config-overrides.md")

try:
    from .noesis_roots import (
        apply_overlay_operations,
        config_path,
        resolve_files,
        resolve_config_paths,
        root_context,
    )
except Exception:
    _module = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_roots.py")))
    apply_overlay_operations = _module["apply_overlay_operations"]
    config_path = _module["config_path"]
    resolve_files = _module["resolve_files"]
    resolve_config_paths = _module["resolve_config_paths"]
    root_context = _module["root_context"]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        return ""


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def configured_paths(root: Path) -> Dict[str, Path]:
    files = resolve_files(root)
    required = {
        "proposals_dir": "config_override_proposals_dir",
        "active_dir": "config_override_active_dir",
        "archive_dir": "config_override_archive_dir",
        "state": "config_override_state",
        "events": "config_override_events",
        "effective_cache_dir": "config_override_effective_cache_dir",
    }
    missing = [key for key in required.values() if key not in files]
    if missing:
        raise RuntimeError("Noesis config override file keys are missing from config: " + ", ".join(sorted(missing)))
    return {name: files[key] for name, key in required.items()}


def parse_jsonish(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def overlay_id(config_key: str, task_id: str, operations: List[Dict[str, Any]]) -> str:
    payload = json.dumps({"config_key": config_key, "task_id": task_id, "operations": operations, "time": now_utc()}, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return "cfgovr-" + digest


def event(root: Path, kind: str, payload: Dict[str, Any]) -> None:
    paths = configured_paths(root)
    append_jsonl(paths["events"], {"schema": "noesis.suite.config_override_event.v1", "created_utc": now_utc(), "kind": kind, **payload})


def list_overlays(root: Path, *, include_archived: bool = False) -> List[Dict[str, Any]]:
    paths = configured_paths(root)
    dirs = [paths["proposals_dir"], paths["active_dir"]]
    if include_archived:
        dirs.append(paths["archive_dir"])
    items: List[Dict[str, Any]] = []
    for directory in dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            value = read_json(path)
            if value:
                value["path"] = str(path)
                value["bucket"] = directory.name
                items.append(value)
    return items


def propose(root: Path, *, config_key: str, operations: List[Dict[str, Any]], task_id: str = "", reason: str = "") -> Dict[str, Any]:
    if config_key not in resolve_config_paths(root):
        raise RuntimeError(f"Noesis config key is not configured: {config_key}")
    if not operations:
        raise RuntimeError("At least one config overlay operation is required")
    created = now_utc()
    oid = overlay_id(config_key, task_id, operations)
    overlay = {
        "schema": "noesis.suite.config_overlay.v1",
        "id": oid,
        "status": "proposed",
        "created_utc": created,
        "updated_utc": created,
        "config_key": config_key,
        "task_id": task_id,
        "reason": reason,
        "operations": operations,
        "approval": {
            "required_for_base_config_write": True,
            "active_overlay_is_runtime_only": True,
            "base_config_mutation": "forbidden_without_explicit_approval",
        },
    }
    paths = configured_paths(root)
    target = paths["proposals_dir"] / f"{oid}.json"
    write_json(target, overlay)
    event(root, "proposed", {"id": oid, "config_key": config_key, "path": str(target)})
    return {"ok": True, "id": oid, "path": str(target), "overlay": overlay}


def find_overlay_file(root: Path, overlay_id_value: str) -> Path:
    paths = configured_paths(root)
    for directory in [paths["proposals_dir"], paths["active_dir"], paths["archive_dir"]]:
        candidate = directory / f"{overlay_id_value}.json"
        if candidate.exists():
            return candidate
    raise RuntimeError(f"Noesis config overlay not found: {overlay_id_value}")


def activate(root: Path, overlay_id_value: str) -> Dict[str, Any]:
    paths = configured_paths(root)
    source = find_overlay_file(root, overlay_id_value)
    overlay = read_json(source)
    if not overlay:
        raise RuntimeError(f"Invalid overlay JSON: {source}")
    state = read_json(paths["state"])
    try:
        activation_seq = int(state.get("last_activation_seq") or 0) + 1
    except Exception:
        activation_seq = 1
    active = state.get("active_overlay_ids") if isinstance(state.get("active_overlay_ids"), list) else []
    if overlay_id_value not in active:
        active.append(overlay_id_value)
    activated_utc = now_utc()
    overlay["status"] = "active"
    overlay["updated_utc"] = activated_utc
    overlay["activated_utc"] = activated_utc
    overlay["activation_seq"] = activation_seq
    target = paths["active_dir"] / f"{overlay_id_value}.json"
    write_json(target, overlay)
    state.update({
        "schema": "noesis.suite.config_override_state.v1",
        "updated_utc": now_utc(),
        "active_overlay_ids": active,
        "last_activation_seq": activation_seq,
    })
    write_json(paths["state"], state)
    event(root, "activated", {"id": overlay_id_value, "config_key": overlay.get("config_key"), "path": str(target)})
    return {"ok": True, "id": overlay_id_value, "path": str(target), "overlay": overlay}


def deactivate(root: Path, overlay_id_value: str) -> Dict[str, Any]:
    paths = configured_paths(root)
    active = paths["active_dir"] / f"{overlay_id_value}.json"
    if not active.exists():
        return {"ok": True, "id": overlay_id_value, "deactivated": False, "reason": "not_active"}
    overlay = read_json(active)
    overlay["status"] = "archived"
    overlay["updated_utc"] = now_utc()
    target = paths["archive_dir"] / f"{overlay_id_value}.json"
    write_json(target, overlay)
    active.unlink()
    state = read_json(paths["state"])
    ids = state.get("active_overlay_ids") if isinstance(state.get("active_overlay_ids"), list) else []
    state["active_overlay_ids"] = [x for x in ids if x != overlay_id_value]
    state["updated_utc"] = now_utc()
    state["schema"] = "noesis.suite.config_override_state.v1"
    write_json(paths["state"], state)
    event(root, "deactivated", {"id": overlay_id_value, "path": str(target)})
    return {"ok": True, "id": overlay_id_value, "deactivated": True, "archive_path": str(target)}


def effective(root: Path, *, config_key: str, write_cache: bool = False) -> Dict[str, Any]:
    configs = resolve_config_paths(root)
    if config_key not in configs:
        raise RuntimeError(f"Noesis config key is not configured: {config_key}")
    base_path = configs[config_key]
    base = read_json(base_path)
    if not base:
        raise RuntimeError(f"Invalid or missing base config for {config_key}: {base_path}")
    active = [x for x in list_overlays(root) if x.get("bucket") == "active" and x.get("config_key") == config_key]
    active.sort(key=lambda x: (int(x.get("activation_seq") or 0), str(x.get("activated_utc") or x.get("updated_utc") or x.get("created_utc") or ""), str(x.get("id") or "")))
    result = base
    applied: List[Dict[str, Any]] = []
    for overlay in active:
        operations = overlay.get("operations")
        if not isinstance(operations, list):
            continue
        result = apply_overlay_operations(result, operations)
        applied.append({"id": overlay.get("id"), "path": overlay.get("path"), "activation_seq": overlay.get("activation_seq")})
    envelope = {
        "schema": "noesis.suite.effective_config_result.v1",
        "ok": True,
        "generated_utc": now_utc(),
        "config_key": config_key,
        "base_path": str(base_path),
        "active_overlays": applied,
        "config": result,
    }
    if write_cache:
        paths = configured_paths(root)
        cache = paths["effective_cache_dir"] / f"{config_key}.json"
        write_json(cache, envelope)
        envelope["cache_path"] = str(cache)
    return envelope


def status(root: Path) -> Dict[str, Any]:
    paths = configured_paths(root)
    overlays = list_overlays(root, include_archived=True)
    configs = resolve_config_paths(root)
    return {
        "schema": "noesis.suite.config_override_status.v1",
        "ok": True,
        "generated_utc": now_utc(),
        "configured_paths": {key: str(value) for key, value in paths.items()},
        "configured_configs": {key: str(value) for key, value in configs.items()},
        "counts": {
            "proposed": sum(1 for item in overlays if item.get("bucket") == "proposals"),
            "active": sum(1 for item in overlays if item.get("bucket") == "active"),
            "archived": sum(1 for item in overlays if item.get("bucket") == "archive"),
        },
        "root_context_effective": root_context(root).get("effective", {}),
    }


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Noesis generic config overlay protocol")
    parser.add_argument("command", choices=["status", "list", "propose", "activate", "deactivate", "effective"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--config-key", default="")
    parser.add_argument("--op", default="set")
    parser.add_argument("--path", default="")
    parser.add_argument("--value", default="null")
    parser.add_argument("--operations-json", default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--id", default="")
    parser.add_argument("--write-cache", action="store_true")
    ns = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(ns.root).resolve()
    if ns.command == "status":
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "list":
        print(json.dumps(list_overlays(root, include_archived=True), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "propose":
        operations = json.loads(ns.operations_json) if ns.operations_json else [{"op": ns.op, "path": ns.path, "value": parse_jsonish(ns.value)}]
        print(json.dumps(propose(root, config_key=ns.config_key, operations=operations, task_id=ns.task_id, reason=ns.reason), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "activate":
        print(json.dumps(activate(root, ns.id), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "deactivate":
        print(json.dumps(deactivate(root, ns.id), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "effective":
        print(json.dumps(effective(root, config_key=ns.config_key, write_cache=ns.write_cache), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
