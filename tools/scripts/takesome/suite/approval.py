from __future__ import annotations

import os
from typing import Any

_SUDO_ENV = "NORTHSTAR_SUITE_SUDO"
_SUDO_VALUES = {"1", "true", "yes", "y", "on", "force", "sudo"}


def suite_sudo_enabled() -> bool:
    return os.environ.get(_SUDO_ENV, "").strip().lower() in _SUDO_VALUES


def enable_suite_sudo(reason: str = "") -> None:
    os.environ[_SUDO_ENV] = "1"
    if reason:
        os.environ["NORTHSTAR_SUITE_SUDO_REASON"] = reason


def apply_sudo_from_args(args: Any) -> bool:
    if bool(getattr(args, "sudo", False)):
        enable_suite_sudo("cli")
        return True
    return suite_sudo_enabled()


def suite_sudo_label() -> str:
    return "enabled" if suite_sudo_enabled() else "disabled"
