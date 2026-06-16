from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

CONFIG_REL = Path(".takesome/config/noesis-roots.v1.json")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing Noesis roots config: {path}") from exc
    except Exception as exc:
        raise RuntimeError(f"Invalid Noesis roots config: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Noesis roots config must be an object: {path}")
    return value


def machine_runtime_root() -> Path:
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local:
        return Path(local).expanduser().resolve() / "NoesisSuite"
    return Path.home().joinpath(".local", "state", "NoesisSuite").resolve()


def load_base_config(suite_root: Path) -> Dict[str, Any]:
    return read_json(suite_root.resolve() / CONFIG_REL)


def env_first(names: Iterable[Any]) -> str:
    for name in names:
        text = str(name or "").strip()
        if not text:
            continue
        value = os.environ.get(text)
        if value:
            return value
    return ""


def substitute(value: str, known: Dict[str, Path], builtins: Dict[str, Path]) -> str:
    result = os.path.expandvars(value)
    merged: Dict[str, Path] = {}
    merged.update(builtins)
    merged.update(known)
    for key, path in merged.items():
        result = result.replace("${" + key + "}", str(path))
    return result


def path_from_text(text: str, *, base: Path, known: Dict[str, Path], builtins: Dict[str, Path]) -> Path:
    resolved = substitute(text, known, builtins).strip()
    path = Path(resolved).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def resolve_root_spec(key: str, spec: Any, *, suite_input_root: Path, known: Dict[str, Path], builtins: Dict[str, Path]) -> Path:
    base = suite_input_root.resolve()
    if isinstance(spec, str):
        text = spec.strip() or "${suite_input_root}"
        return path_from_text(text, base=base, known=known, builtins=builtins)
    if not isinstance(spec, dict):
        raise RuntimeError(f"Invalid Noesis root spec for {key}: expected string or object")
    env_value = env_first(spec.get("env", [])) if isinstance(spec.get("env"), list) else ""
    if env_value:
        return path_from_text(env_value, base=base, known=known, builtins=builtins)
    raw = spec.get("path", spec.get("fallback", "${suite_input_root}"))
    return path_from_text(str(raw), base=base, known=known, builtins=builtins)


def resolve_roots_from_config(config: Dict[str, Any], suite_root: Path) -> Dict[str, Path]:
    roots_config = config.get("roots")
    if not isinstance(roots_config, dict) or not roots_config:
        raise RuntimeError("Noesis roots config must contain non-empty roots object")
    builtins = {
        "suite_input_root": suite_root.resolve(),
        "machine_runtime_root": machine_runtime_root(),
    }
    known: Dict[str, Path] = {}
    pending = dict(roots_config)
    for _ in range(max(1, len(pending) + 2)):
        progressed = False
        for key in list(pending.keys()):
            try:
                known[key] = resolve_root_spec(key, pending[key], suite_input_root=suite_root, known=known, builtins=builtins)
            except Exception:
                continue
            pending.pop(key, None)
            progressed = True
        if not pending:
            return known
        if not progressed:
            break
    unresolved = ", ".join(sorted(pending))
    raise RuntimeError(f"Unable to resolve Noesis roots from config: {unresolved}")


def resolve_file_spec(raw: Any, *, suite_root: Path, roots: Dict[str, Path]) -> Path:
    if raw is None:
        raise RuntimeError("Noesis file path is missing")
    builtins = {
        "suite_input_root": suite_root.resolve(),
        "machine_runtime_root": machine_runtime_root(),
    }
    return path_from_text(str(raw), base=suite_root.resolve(), known=roots, builtins=builtins)


def resolve_files_from_config(config: Dict[str, Any], suite_root: Path, roots: Dict[str, Path] | None = None) -> Dict[str, Path]:
    files_config = config.get("files")
    if not isinstance(files_config, dict):
        return {}
    resolved_roots = roots or resolve_roots_from_config(config, suite_root)
    return {str(key): resolve_file_spec(value, suite_root=suite_root, roots=resolved_roots) for key, value in files_config.items()}


def _json_pointer_tokens(pointer: str) -> List[str]:
    if pointer in ("", "/"):
        return []
    if not pointer.startswith("/"):
        raise RuntimeError(f"Overlay operation path must be a JSON pointer: {pointer}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]


def _deep_merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        result = dict(base)
        for key, value in patch.items():
            result[key] = _deep_merge(result[key], value) if key in result else copy.deepcopy(value)
        return result
    return copy.deepcopy(patch)


def _parent_for_pointer(doc: Any, pointer: str, *, create: bool = True) -> tuple[Any, str]:
    tokens = _json_pointer_tokens(pointer)
    if not tokens:
        return None, ""
    node = doc
    for token in tokens[:-1]:
        if isinstance(node, dict):
            if token not in node:
                if not create:
                    raise RuntimeError(f"Overlay path does not exist: {pointer}")
                node[token] = {}
            node = node[token]
        elif isinstance(node, list):
            index = int(token)
            node = node[index]
        else:
            raise RuntimeError(f"Overlay path cannot traverse scalar: {pointer}")
    return node, tokens[-1]


def apply_overlay_operations(config: Dict[str, Any], operations: Iterable[Any]) -> Dict[str, Any]:
    result: Any = copy.deepcopy(config)
    for raw in operations:
        if not isinstance(raw, dict):
            raise RuntimeError("Config overlay operation must be an object")
        op = str(raw.get("op") or "").strip().lower()
        pointer = str(raw.get("path") or "")
        if op in {"set", "replace", "merge"} and pointer in ("", "/"):
            value = copy.deepcopy(raw.get("value"))
            if op == "merge":
                if not isinstance(result, dict) or not isinstance(value, dict):
                    raise RuntimeError("Root merge requires object config and object value")
                result = _deep_merge(result, value)
            else:
                if not isinstance(value, dict):
                    raise RuntimeError("Root set/replace requires object value")
                result = value
            continue
        parent, leaf = _parent_for_pointer(result, pointer, create=op != "remove")
        if parent is None:
            raise RuntimeError(f"Unsupported root operation for {op}: {pointer}")
        if isinstance(parent, dict):
            if op in {"set", "replace"}:
                parent[leaf] = copy.deepcopy(raw.get("value"))
            elif op == "merge":
                parent[leaf] = _deep_merge(parent.get(leaf), raw.get("value"))
            elif op == "remove":
                parent.pop(leaf, None)
            else:
                raise RuntimeError(f"Unsupported config overlay op: {op}")
        elif isinstance(parent, list):
            index = int(leaf)
            if op in {"set", "replace"}:
                parent[index] = copy.deepcopy(raw.get("value"))
            elif op == "remove":
                parent.pop(index)
            else:
                raise RuntimeError(f"Unsupported list overlay op: {op}")
        else:
            raise RuntimeError(f"Overlay path parent is scalar: {pointer}")
    if not isinstance(result, dict):
        raise RuntimeError("Effective Noesis config must remain an object")
    return result


def _active_overlay_files_for(config: Dict[str, Any], suite_root: Path, config_key: str) -> List[Path]:
    try:
        roots = resolve_roots_from_config(config, suite_root)
        files = resolve_files_from_config(config, suite_root, roots)
    except Exception:
        return []
    active_dir = files.get("config_override_active_dir")
    if not active_dir or not active_dir.exists():
        return []
    candidates: List[tuple[str, Path]] = []
    for path in sorted(active_dir.glob("*.json")):
        try:
            overlay = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if str(overlay.get("config_key") or "") != config_key:
            continue
        order = str(overlay.get("created_utc") or "") + " " + str(overlay.get("id") or path.stem)
        candidates.append((order, path))
    return [path for _, path in sorted(candidates)]


def apply_active_overlays(config: Dict[str, Any], suite_root: Path, config_key: str) -> Dict[str, Any]:
    effective = copy.deepcopy(config)
    applied: List[Dict[str, Any]] = []
    for path in _active_overlay_files_for(config, suite_root, config_key):
        overlay = json.loads(path.read_text(encoding="utf-8-sig"))
        operations = overlay.get("operations")
        if not isinstance(operations, list):
            continue
        effective = apply_overlay_operations(effective, operations)
        applied.append({"id": overlay.get("id"), "path": str(path)})
    if applied:
        effective.setdefault("_effective", {})
        if isinstance(effective["_effective"], dict):
            effective["_effective"].update({
                "schema": "noesis.suite.effective_config.v1",
                "generated_utc": utc_now(),
                "base_source": str((suite_root.resolve() / CONFIG_REL)),
                "config_key": config_key,
                "active_overlays": applied,
            })
    return effective


def load_config(suite_root: Path) -> Dict[str, Any]:
    base = load_base_config(suite_root)
    self_config = base.get("self") if isinstance(base.get("self"), dict) else {}
    config_key = str(self_config.get("config_key") or "").strip()
    if not config_key:
        return base
    return apply_active_overlays(base, suite_root, config_key)


def resolve_roots(suite_root: Path) -> Dict[str, Path]:
    return resolve_roots_from_config(load_config(suite_root), suite_root)


def resolve_files(suite_root: Path, roots: Dict[str, Path] | None = None) -> Dict[str, Path]:
    config = load_config(suite_root)
    return resolve_files_from_config(config, suite_root, roots)


def resolve_config_paths(suite_root: Path) -> Dict[str, Path]:
    config = load_config(suite_root)
    configs = config.get("configs")
    if not isinstance(configs, dict):
        return {}
    roots = resolve_roots_from_config(config, suite_root)
    return {str(key): resolve_file_spec(value, suite_root=suite_root, roots=roots) for key, value in configs.items()}


def root_context(suite_root: Path) -> Dict[str, Any]:
    config = load_config(suite_root)
    roots = resolve_roots_from_config(config, suite_root)
    files = resolve_files_from_config(config, suite_root, roots)
    root_meta = config.get("root_metadata") if isinstance(config.get("root_metadata"), dict) else {}
    return {
        "schema": "noesis.suite.root_context.v1",
        "generated_utc": utc_now(),
        "source": str((suite_root.resolve() / CONFIG_REL)),
        "effective": config.get("_effective", {}) if isinstance(config.get("_effective"), dict) else {},
        "roots": {
            key: {
                "path": str(path),
                "metadata": root_meta.get(key, {}) if isinstance(root_meta.get(key, {}), dict) else {},
            }
            for key, path in roots.items()
        },
        "files": {key: str(path) for key, path in files.items()},
        "configs": {key: str(path) for key, path in resolve_config_paths(suite_root).items()},
    }


def root_path(suite_root: Path, key: str) -> Path:
    roots = resolve_roots(suite_root)
    if key not in roots:
        raise RuntimeError(f"Noesis root key is not configured: {key}")
    return roots[key]


def file_path(suite_root: Path, key: str) -> Path:
    files = resolve_files(suite_root)
    if key not in files:
        raise RuntimeError(f"Noesis file key is not configured: {key}")
    return files[key]


def config_path(suite_root: Path, key: str) -> Path:
    configs = resolve_config_paths(suite_root)
    if key not in configs:
        raise RuntimeError(f"Noesis config key is not configured: {key}")
    return configs[key]


def ensure_dirs(suite_root: Path) -> Dict[str, Any]:
    roots = resolve_roots(suite_root)
    created: list[str] = []
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path))
    return {"ok": True, "created_or_existing": created}
