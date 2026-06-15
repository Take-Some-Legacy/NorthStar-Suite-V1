from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

CONFIG_ROOT_REL = Path(".takesome") / "config"
LEGACY_CONFIG_ROOT_REL = Path("config") / "suite"


@dataclass(frozen=True)
class ConfigLoadResult:
    """Result of a bounded Suite config lookup.

    The canonical config root is .takesome/config.  config/suite is kept only as
    a legacy fallback so old launchers keep working during migration.
    """

    data: dict[str, Any]
    path: Path | None = None
    source: str = "defaults"
    error: str = ""

    @property
    def found(self) -> bool:
        return bool(self.data) and self.path is not None and not self.error

    def with_metadata(self) -> dict[str, Any]:
        data = dict(self.data)
        if self.path is not None:
            data.setdefault("_config_path", str(self.path))
        data.setdefault("_config_source", self.source)
        if self.error:
            data.setdefault("_config_error", self.error)
        return data


def read_json_object(path: Path) -> dict[str, Any]:
    """Read one JSON object from disk. Non-object or unreadable files return {}."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_user_path(base: Path, raw: str | Path | None) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = os.path.expandvars(text)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return path.resolve()


def _unique_paths(paths: Iterable[Path | None]) -> tuple[Path, ...]:
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        if path is None:
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return tuple(out)


def config_candidates(
    root: Path,
    filename: str | Path,
    *,
    operator_root: Path | None = None,
    include_legacy: bool = True,
) -> tuple[Path, ...]:
    """Return config candidates in canonical precedence order.

    Order is intentionally Suite-first: operator_root/.takesome/config, then
    workspace/root .takesome/config, then legacy config/suite fallbacks.
    """
    rel = Path(filename)
    primary = [
        (operator_root / CONFIG_ROOT_REL / rel) if operator_root is not None else None,
        root / CONFIG_ROOT_REL / rel,
    ]
    legacy = [
        (operator_root / LEGACY_CONFIG_ROOT_REL / rel) if operator_root is not None else None,
        root / LEGACY_CONFIG_ROOT_REL / rel,
    ] if include_legacy else []
    return _unique_paths([*primary, *legacy])


def first_existing_config_path(
    root: Path,
    filename: str | Path,
    *,
    operator_root: Path | None = None,
    include_legacy: bool = True,
) -> Path | None:
    for path in config_candidates(root, filename, operator_root=operator_root, include_legacy=include_legacy):
        if path.exists():
            return path
    return None


def load_config_json(
    root: Path,
    filename: str | Path,
    *,
    operator_root: Path | None = None,
    explicit_path: str | Path | None = None,
    env_var: str | None = None,
    include_legacy: bool = True,
) -> ConfigLoadResult:
    """Load one Suite config object using explicit/env/canonical/legacy order."""
    explicit = str(explicit_path or "").strip()
    env_raw = os.environ.get(env_var, "").strip() if env_var else ""
    if explicit or env_raw:
        path = resolve_user_path(root, explicit or env_raw)
        if path is None:
            return ConfigLoadResult({}, source="defaults")
        try:
            data = read_json_object(path)
            return ConfigLoadResult(data, path if data else None, "explicit" if explicit else f"env:{env_var}")
        except Exception as exc:
            return ConfigLoadResult({}, path, "explicit" if explicit else f"env:{env_var}", str(exc))

    for path in config_candidates(root, filename, operator_root=operator_root, include_legacy=include_legacy):
        data = read_json_object(path)
        if data:
            rel = path.as_posix().lower()
            source = "legacy" if "/config/suite/" in rel or "\\config\\suite\\" in str(path).lower() else "canonical"
            return ConfigLoadResult(data, path, source)
    return ConfigLoadResult({}, source="defaults")


def write_json_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


__all__ = [
    "CONFIG_ROOT_REL",
    "LEGACY_CONFIG_ROOT_REL",
    "ConfigLoadResult",
    "config_candidates",
    "first_existing_config_path",
    "load_config_json",
    "read_json_object",
    "resolve_user_path",
    "write_json_object",
]
