from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import runpy
from pathlib import Path
from typing import Any, Dict, Iterable, List

RULES_PATH = Path("tools/scripts/takesome/rules/noesis-source-apply-gate.md")

try:
    from .noesis_roots import load_config, resolve_files, root_context
except Exception:
    _module = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_roots.py")))
    load_config = _module["load_config"]
    resolve_files = _module["resolve_files"]
    root_context = _module["root_context"]

try:
    from .noesis_config_overrides import activate as activate_overlay
    from .noesis_config_overrides import propose as propose_overlay
except Exception:
    _overlay_module = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_config_overrides.py")))
    activate_overlay = _overlay_module["activate"]
    propose_overlay = _overlay_module["propose"]


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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def load_rules(root: Path) -> Dict[str, Any]:
    path = root / RULES_PATH
    text = read_text(path)
    match = re.search(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        raise RuntimeError(f"Noesis source apply rules JSON block is missing: {path}")
    try:
        value = json.loads(match.group(1))
    except Exception as exc:
        raise RuntimeError(f"Invalid Noesis source apply rules JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Noesis source apply rules must be an object: {path}")
    return value


def configured_paths(root: Path) -> Dict[str, Path]:
    files = resolve_files(root)
    required = {
        "review_packet": "task_artifact_current_review_packet",
        "request_current": "source_apply_request_current",
        "state": "source_apply_state",
        "events": "source_apply_events",
        "requests_dir": "source_apply_requests_dir",
    }
    missing = [value for value in required.values() if value not in files]
    if missing:
        raise RuntimeError("Noesis source apply file keys are missing from config: " + ", ".join(sorted(missing)))
    return {key: files[value] for key, value in required.items()}


def rules_config(root: Path) -> Dict[str, Any]:
    rules = load_rules(root)
    config = rules.get("config")
    if not isinstance(config, dict):
        raise RuntimeError("Noesis source apply rules must contain config object")
    return config


def source_apply_config(root: Path) -> Dict[str, Any]:
    config = load_config(root)
    capability = config.get("source_apply")
    if not isinstance(capability, dict):
        raise RuntimeError("Noesis effective config must contain source_apply capability object")
    return capability


def source_apply_status_fields(root: Path) -> Dict[str, Any]:
    capability = source_apply_config(root)
    return {
        "enabled": bool(capability.get("enabled")),
        "enablement_mode": capability.get("enablement_mode"),
        "approval_required": bool(capability.get("approval_required")),
        "direct_source_write_without_approval": bool(capability.get("direct_source_write_without_approval")),
        "auto_apply": bool(capability.get("auto_apply")),
        "auto_commit": bool(capability.get("auto_commit")),
        "auto_push": bool(capability.get("auto_push")),
        "validation_required": bool(capability.get("validation_required")),
        "commit_requires_separate_request": bool(capability.get("commit_requires_separate_request")),
        "push_requires_separate_request": bool(capability.get("push_requires_separate_request")),
        "enabled_by": capability.get("enabled_by"),
        "enabled_utc": capability.get("enabled_utc"),
        "enable_reason": capability.get("enable_reason"),
        "last_enable_task_id": capability.get("last_enable_task_id"),
    }


def request_id(review_packet: Dict[str, Any], reason: str, capability: Dict[str, Any]) -> str:
    payload = json.dumps({"review_packet": review_packet, "reason": reason, "capability": capability, "time": now_utc()}, ensure_ascii=False, sort_keys=True)
    return "srcapply-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def render_request(envelope: Dict[str, Any]) -> str:
    lines = [
        "# Noesis Source Apply Request",
        "",
        f"schema: {envelope.get('schema')}",
        f"id: {envelope.get('id')}",
        f"created_utc: {envelope.get('created_utc')}",
        f"status: {envelope.get('status')}",
        f"source_apply_enabled: {envelope.get('source_apply_enabled')}",
        f"approval_required: {envelope.get('approval_required')}",
        f"auto_apply: {envelope.get('auto_apply')}",
        f"auto_commit: {envelope.get('auto_commit')}",
        f"auto_push: {envelope.get('auto_push')}",
        "",
        "## Reason",
        "",
        str(envelope.get("reason", "")),
        "",
        "## Gate",
        "",
        "No source files were changed by this command. The capability state is read from effective config and may be enabled through runtime overlays.",
        "",
        "## Capability",
        "",
        "```json",
        json.dumps(envelope.get("capability", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Review Packet",
        "",
        "```json",
        json.dumps(envelope.get("review_packet", {}), ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(lines) + "\n"



def prepare(root: Path, *, reason: str = "") -> Dict[str, Any]:
    paths = configured_paths(root)
    review_packet = read_json(paths["review_packet"])
    capability = source_apply_status_fields(root)
    created = now_utc()
    enabled = bool(capability.get("enabled"))
    rid = request_id(review_packet, reason, capability)
    status_value = "approval_required" if enabled else "capability_disabled_enable_available"
    envelope = {
        "schema": "noesis.suite.source_apply_request.v1",
        "id": rid,
        "created_utc": created,
        "updated_utc": created,
        "status": status_value,
        "source_apply_enabled": enabled,
        "approval_required": bool(capability.get("approval_required")),
        "auto_apply": bool(capability.get("auto_apply")),
        "auto_commit": bool(capability.get("auto_commit")),
        "auto_push": bool(capability.get("auto_push")),
        "reason": reason,
        "capability": capability,
        "review_packet": review_packet,
        "root_context": root_context(root),
    }
    write_text(paths["request_current"], render_request(envelope))
    write_json(paths["requests_dir"] / f"{rid}.json", envelope)
    state = {
        "schema": "noesis.suite.source_apply_state.v1",
        "updated_utc": created,
        "status": status_value,
        "current_request_id": rid,
        "source_apply_enabled": enabled,
        "capability": capability,
        "current_request": str(paths["request_current"]),
    }
    write_json(paths["state"], state)
    append_jsonl(paths["events"], {"schema": "noesis.suite.source_apply_event.v1", "created_utc": created, "kind": "request_prepared", "id": rid, "source_apply_enabled": enabled})
    return {"ok": True, "request": envelope, "request_md": str(paths["request_current"])}


def sync_capability_state(root: Path, *, status_value: str, event_kind: str, overlay_id: str = "", task_id: str = "") -> Dict[str, Any]:
    paths = configured_paths(root)
    created = now_utc()
    capability = source_apply_status_fields(root)
    enabled = bool(capability.get("enabled"))
    existing = read_json(paths["state"])
    state = {
        "schema": "noesis.suite.source_apply_state.v1",
        "updated_utc": created,
        "status": status_value,
        "source_apply_enabled": enabled,
        "capability": capability,
        "current_request_id": existing.get("current_request_id", ""),
        "current_request": existing.get("current_request", str(paths["request_current"])),
        "last_capability_overlay_id": overlay_id,
        "last_capability_task_id": task_id,
    }
    write_json(paths["state"], state)
    append_jsonl(paths["events"], {
        "schema": "noesis.suite.source_apply_event.v1",
        "created_utc": created,
        "kind": event_kind,
        "overlay_id": overlay_id,
        "task_id": task_id,
        "source_apply_enabled": enabled,
    })
    return state


def _overlay_paths(root: Path) -> Dict[str, str]:
    config = rules_config(root)
    paths = config.get("overlay_paths")
    if not isinstance(paths, dict):
        raise RuntimeError("Noesis source apply rules must define config.overlay_paths")
    return {str(key): str(value) for key, value in paths.items()}


def _config_key(root: Path) -> str:
    config = rules_config(root)
    key = str(config.get("config_key") or "").strip()
    if not key:
        raise RuntimeError("Noesis source apply rules must define config.config_key")
    return key


def _operation(paths: Dict[str, str], name: str, value: Any) -> Dict[str, Any]:
    if name not in paths:
        raise RuntimeError(f"Noesis source apply overlay path is missing from rules: {name}")
    return {"op": "set", "path": paths[name], "value": value}


def enable(root: Path, *, task_id: str = "", reason: str = "", enabled_by: str = "noesis", auto_apply: bool | None = None, auto_commit: bool | None = None, auto_push: bool | None = None) -> Dict[str, Any]:
    paths = _overlay_paths(root)
    current = source_apply_status_fields(root)
    created = now_utc()
    operations: List[Dict[str, Any]] = [
        _operation(paths, "enabled", True),
        _operation(paths, "enablement_mode", "runtime_config_overlay"),
        _operation(paths, "enabled_by", enabled_by),
        _operation(paths, "enabled_utc", created),
        _operation(paths, "enable_reason", reason),
        _operation(paths, "last_enable_task_id", task_id),
    ]
    for name, requested in [("auto_apply", auto_apply), ("auto_commit", auto_commit), ("auto_push", auto_push)]:
        if requested is not None:
            operations.append(_operation(paths, name, bool(requested)))
        elif name in current:
            operations.append(_operation(paths, name, bool(current.get(name))))
    proposed = propose_overlay(root, config_key=_config_key(root), operations=operations, task_id=task_id, reason=reason)
    activated = activate_overlay(root, proposed["id"])
    state = sync_capability_state(root, status_value="capability_enabled", event_kind="capability_enabled", overlay_id=proposed["id"], task_id=task_id)
    return {"ok": True, "enabled": True, "overlay_id": proposed["id"], "proposed": proposed, "activated": activated, "capability": source_apply_status_fields(root), "state": state}


def disable(root: Path, *, task_id: str = "", reason: str = "", enabled_by: str = "noesis") -> Dict[str, Any]:
    paths = _overlay_paths(root)
    created = now_utc()
    operations = [
        _operation(paths, "enabled", False),
        _operation(paths, "auto_apply", False),
        _operation(paths, "auto_commit", False),
        _operation(paths, "auto_push", False),
        _operation(paths, "enabled_by", enabled_by),
        _operation(paths, "enabled_utc", created),
        _operation(paths, "enable_reason", reason),
        _operation(paths, "last_enable_task_id", task_id),
    ]
    proposed = propose_overlay(root, config_key=_config_key(root), operations=operations, task_id=task_id, reason=reason)
    activated = activate_overlay(root, proposed["id"])
    state = sync_capability_state(root, status_value="capability_disabled", event_kind="capability_disabled", overlay_id=proposed["id"], task_id=task_id)
    return {"ok": True, "enabled": False, "overlay_id": proposed["id"], "proposed": proposed, "activated": activated, "capability": source_apply_status_fields(root), "state": state}


def status(root: Path) -> Dict[str, Any]:
    paths = configured_paths(root)
    capability = source_apply_status_fields(root)
    enabled = bool(capability.get("enabled"))
    state = read_json(paths["state"])

    state_enabled = bool(state.get("source_apply_enabled")) if state else False
    state_status = str(state.get("status", "")) if state else ""
    expected_status = "capability_enabled" if enabled else "capability_disabled"

    if state_enabled != enabled or state_status not in {expected_status, "approval_required", "request_prepared"}:
        state = sync_capability_state(
            root,
            status_value=expected_status,
            event_kind="capability_status_sync",
            task_id=str(capability.get("last_enable_task_id", "")),
        )

    return {
        "schema": "noesis.suite.source_apply_status.v1",
        "ok": True,
        "generated_utc": now_utc(),
        "source_apply_enabled": enabled,
        "capability": capability,
        "state": state,
        "paths": {key: str(value) for key, value in paths.items()},
        "root_context_effective": root_context(root).get("effective", {}),
    }




# --- Noesis admin default permission profile override v1 ---
def _truthy_runtime_env(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _windows_process_is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def runtime_permission_facts(root: Path) -> Dict[str, Any]:
    config = load_config(root)
    policy = config.get("runtime_permissions", {}).get("admin_defaults", {})
    activation = policy.get("activation_when", {}) if isinstance(policy, dict) else {}
    env_names = activation.get("bridge_write_enabled_env_any", []) if isinstance(activation, dict) else []
    try:
        import os
        env_hits = {str(name): os.environ.get(str(name), "") for name in env_names if str(name)}
    except Exception:
        env_hits = {}
    env_write_enabled = any(_truthy_runtime_env(value) for value in env_hits.values())
    windows_admin = _windows_process_is_admin()
    admin_default_active = bool(policy.get("enabled", False)) and bool(windows_admin or env_write_enabled)
    return {
        "schema": "noesis.suite.runtime_permission_facts.v1",
        "generated_utc": now_utc(),
        "windows_process_is_admin": windows_admin,
        "env_write_enabled": env_write_enabled,
        "env_hits": {key: ("set" if value else "") for key, value in env_hits.items()},
        "admin_default_active": admin_default_active,
        "admin_default_profile": policy.get("default_profile", ""),
    }


def _apply_admin_default_capability(root: Path, capability: Dict[str, Any]) -> Dict[str, Any]:
    config = load_config(root)
    source_config = config.get("source_apply", {}) if isinstance(config.get("source_apply", {}), dict) else {}
    facts = runtime_permission_facts(root)
    if bool(source_config.get("admin_default_overridden", False)):
        merged = dict(capability)
        merged["admin_default_active"] = False
        merged["admin_default_overridden"] = True
        merged["runtime_facts"] = facts
        return merged
    if not facts.get("admin_default_active"):
        merged = dict(capability)
        merged["admin_default_active"] = False
        merged["admin_default_overridden"] = False
        merged["runtime_facts"] = facts
        return merged
    admin_defaults = config.get("runtime_permissions", {}).get("admin_defaults", {})
    default_cap = admin_defaults.get("capabilities", {}).get("source_apply", {}) if isinstance(admin_defaults, dict) else {}
    merged = dict(capability)
    for key, value in default_cap.items():
        merged[key] = value
    merged["admin_default_active"] = True
    merged["admin_default_overridden"] = False
    merged["runtime_facts"] = facts
    if not merged.get("enabled_utc"):
        merged["enabled_utc"] = facts.get("generated_utc", now_utc())
    if not merged.get("last_enable_task_id"):
        merged["last_enable_task_id"] = "admin.runtime.default"
    return merged


_original_source_apply_status_fields = source_apply_status_fields

def source_apply_status_fields(root: Path) -> Dict[str, Any]:
    return _apply_admin_default_capability(root, _original_source_apply_status_fields(root))


_original_enable = enable

def enable(root: Path, *, task_id: str = "", reason: str = "", enabled_by: str = "noesis", auto_apply: bool | None = None, auto_commit: bool | None = None, auto_push: bool | None = None) -> Dict[str, Any]:
    result = _original_enable(root, task_id=task_id, reason=reason, enabled_by=enabled_by, auto_apply=auto_apply, auto_commit=auto_commit, auto_push=auto_push)
    # Explicit enable clears a previous admin-default override so privileged launches can again use config defaults.
    ops = [{"op": "set", "path": "/source_apply/admin_default_overridden", "value": False}]
    proposed = propose_overlay(root, config_key=_config_key(root), operations=ops, task_id=task_id, reason="Clear admin default override after explicit enable")
    activate_overlay(root, proposed["id"])
    result["admin_default_override_cleared_overlay_id"] = proposed["id"]
    result["capability"] = source_apply_status_fields(root)
    sync_capability_state(root, status_value="capability_enabled", event_kind="source_apply_enabled", overlay_id=result.get("overlay_id", ""), task_id=task_id)
    return result


def disable(root: Path, *, task_id: str = "", reason: str = "", enabled_by: str = "noesis") -> Dict[str, Any]:
    paths = _overlay_paths(root)
    ops = [
        _operation(paths, "enabled", False),
        _operation(paths, "auto_apply", False),
        _operation(paths, "auto_commit", False),
        _operation(paths, "auto_push", False),
        {"op": "set", "path": "/source_apply/admin_default_overridden", "value": True},
        _operation(paths, "enabled_by", enabled_by),
        _operation(paths, "enabled_utc", now_utc()),
        _operation(paths, "enable_reason", reason or "Capability disabled; admin default overridden."),
        _operation(paths, "last_enable_task_id", task_id),
    ]
    proposed = propose_overlay(root, config_key=_config_key(root), operations=ops, task_id=task_id, reason=reason or "Disable source apply capability")
    activated = activate_overlay(root, proposed["id"])
    capability = source_apply_status_fields(root)
    sync_capability_state(root, status_value="capability_disabled", event_kind="source_apply_disabled", overlay_id=proposed["id"], task_id=task_id)
    return {"ok": True, "enabled": False, "overlay_id": proposed["id"], "proposed": proposed, "activated": activated, "capability": capability}

# --- /Noesis admin default permission profile override v1 ---


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Noesis source apply capability gate")
    parser.add_argument("command", choices=["status", "prepare", "enable", "disable"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--reason", default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--enabled-by", default="noesis")
    parser.add_argument("--auto-apply", action="store_true")
    parser.add_argument("--auto-commit", action="store_true")
    parser.add_argument("--auto-push", action="store_true")
    ns = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(ns.root).resolve()
    if ns.command == "status":
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "prepare":
        print(json.dumps(prepare(root, reason=ns.reason), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "enable":
        print(json.dumps(enable(root, task_id=ns.task_id, reason=ns.reason, enabled_by=ns.enabled_by, auto_apply=ns.auto_apply, auto_commit=ns.auto_commit, auto_push=ns.auto_push), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "disable":
        print(json.dumps(disable(root, task_id=ns.task_id, reason=ns.reason, enabled_by=ns.enabled_by), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
