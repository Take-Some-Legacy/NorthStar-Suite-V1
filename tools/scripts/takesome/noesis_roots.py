from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable

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


def load_config(suite_root: Path) -> Dict[str, Any]:
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


def resolve_roots(suite_root: Path) -> Dict[str, Path]:
    config = load_config(suite_root)
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


def resolve_files(suite_root: Path, roots: Dict[str, Path] | None = None) -> Dict[str, Path]:
    config = load_config(suite_root)
    files_config = config.get("files")
    if not isinstance(files_config, dict):
        return {}
    resolved_roots = roots or resolve_roots(suite_root)
    return {str(key): resolve_file_spec(value, suite_root=suite_root, roots=resolved_roots) for key, value in files_config.items()}


def root_context(suite_root: Path) -> Dict[str, Any]:
    config = load_config(suite_root)
    roots = resolve_roots(suite_root)
    files = resolve_files(suite_root, roots)
    root_meta = config.get("root_metadata") if isinstance(config.get("root_metadata"), dict) else {}
    return {
        "schema": "noesis.suite.root_context.v1",
        "generated_utc": utc_now(),
        "source": str((suite_root.resolve() / CONFIG_REL)),
        "roots": {
            key: {
                "path": str(path),
                "metadata": root_meta.get(key, {}) if isinstance(root_meta.get(key, {}), dict) else {},
            }
            for key, path in roots.items()
        },
        "files": {key: str(path) for key, path in files.items()},
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


def ensure_dirs(suite_root: Path) -> Dict[str, Any]:
    roots = resolve_roots(suite_root)
    created: list[str] = []
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
        created.append(str(path))
    return {"ok": True, "created_or_existing": created}
