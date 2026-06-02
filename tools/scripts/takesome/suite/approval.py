from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_SUDO_ENV = "NORTHSTAR_SUITE_SUDO"
_SUDO_VALUES = {"1", "true", "yes", "y", "on", "force", "sudo"}
_TRUSTED_OWNER_PATH = Path(".takesome/authority/trusted_owner.json")
_TRUSTED_OWNER_SCHEMAS = {
    "northstar.suite.owner_authority.v1",
    "northstar.suite.trusted_owner_authority.v1",
}


def _env_sudo_enabled() -> bool:
    return os.environ.get(_SUDO_ENV, "").strip().lower() in _SUDO_VALUES


def trusted_owner_authority_path(root: Path | None = None) -> Path:
    base = root or Path.cwd()
    return base / _TRUSTED_OWNER_PATH


def trusted_owner_authority_status(root: Path | None = None) -> dict[str, Any]:
    path = trusted_owner_authority_path(root)
    if not path.exists():
        return {
            "ok": False,
            "enabled": False,
            "source": "missing",
            "path": _TRUSTED_OWNER_PATH.as_posix(),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "enabled": False,
            "source": "trusted_owner_file",
            "path": _TRUSTED_OWNER_PATH.as_posix(),
            "error": str(exc),
        }
    schema = str(data.get("schema", ""))
    enabled = bool(data.get("enabled", False))
    scope = str(data.get("scope", ""))
    mode = str(data.get("mode", data.get("authority", "")))
    ok = enabled and schema in _TRUSTED_OWNER_SCHEMAS and scope == "local_workspace" and mode in {"trusted_owner", "trusted_owner_authority"}
    return {
        "ok": ok,
        "enabled": ok,
        "source": "trusted_owner_file",
        "path": _TRUSTED_OWNER_PATH.as_posix(),
        "schema": schema,
        "owner": str(data.get("owner", "")),
        "workspace": str(data.get("workspace", "")),
        "scope": scope,
        "mode": mode,
    }


def trusted_owner_authority_enabled(root: Path | None = None) -> bool:
    return bool(trusted_owner_authority_status(root).get("enabled", False))


def suite_sudo_enabled(root: Path | None = None) -> bool:
    return _env_sudo_enabled() or trusted_owner_authority_enabled(root)


def enable_suite_sudo(reason: str = "") -> None:
    os.environ[_SUDO_ENV] = "1"
    if reason:
        os.environ["NORTHSTAR_SUITE_SUDO_REASON"] = reason


def apply_sudo_from_args(args: Any, root: Path | None = None) -> bool:
    if bool(getattr(args, "sudo", False)):
        enable_suite_sudo("cli")
        return True
    return suite_sudo_enabled(root)


