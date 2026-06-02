from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


_ALLOWED_DANGER_LEVELS = {"normal", "destructive", "manual", "unsafe"}


@dataclass(frozen=True)
class SuiteActionValidationResult:
    action_id: str
    path: str
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "path": self.path,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SuiteActionDescriptor:
    action_id: str
    group: str
    title: str
    description: str
    command: str
    args: tuple[str, ...] = ()
    requires_tools: tuple[str, ...] = ()
    requires_workspace: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    safe_for_menu: bool = True
    danger_level: str = "normal"
    descriptor_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, descriptor_path: Path, repo_root: Path) -> "SuiteActionDescriptor":
        data = json.loads(descriptor_path.read_text(encoding="utf-8"))
        known = {
            "action_id",
            "group",
            "title",
            "description",
            "command",
            "args",
            "requires_tools",
            "requires_workspace",
            "outputs",
            "safe_for_menu",
            "danger_level",
        }
        metadata = {key: value for key, value in data.items() if key not in known}
        return cls(
            action_id=str(data["action_id"]),
            group=str(data.get("group") or "General"),
            title=str(data.get("title") or data["action_id"]),
            description=str(data.get("description") or ""),
            command=str(data["command"]),
            args=tuple(str(arg) for arg in data.get("args", [])),
            requires_tools=tuple(str(item) for item in data.get("requires_tools", [])),
            requires_workspace=tuple(str(item) for item in data.get("requires_workspace", [])),
            outputs=tuple(str(item) for item in data.get("outputs", [])),
            safe_for_menu=bool(data.get("safe_for_menu", True)),
            danger_level=str(data.get("danger_level") or "normal"),
            descriptor_path=_repo_relative(descriptor_path, repo_root),
            metadata=metadata,
        )

    def validate(self) -> SuiteActionValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        _require_identifier(self.action_id, "action_id", errors)
        if not self.command:
            errors.append("command is required")
        _require_identifier(self.command, "command", errors, allow_slash=False)
        if self.danger_level not in _ALLOWED_DANGER_LEVELS:
            errors.append(f"danger_level must be one of {sorted(_ALLOWED_DANGER_LEVELS)}, got {self.danger_level!r}")
        if self.danger_level == "unsafe" and self.safe_for_menu:
            warnings.append("unsafe action is marked safe_for_menu=true")
        if self.command == self.action_id:
            warnings.append("command and action_id are identical; action ids should be domain-specific aliases")
        return SuiteActionValidationResult(
            action_id=self.action_id,
            path=self.descriptor_path,
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "group": self.group,
            "title": self.title,
            "description": self.description,
            "command": self.command,
            "args": list(self.args),
            "requires_tools": list(self.requires_tools),
            "requires_workspace": list(self.requires_workspace),
            "outputs": list(self.outputs),
            "safe_for_menu": self.safe_for_menu,
            "danger_level": self.danger_level,
            "descriptor_path": self.descriptor_path,
            "metadata": self.metadata,
        }


def _require_identifier(value: str, field_name: str, errors: list[str], allow_slash: bool = False) -> None:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if allow_slash:
        allowed.add("/")
    if not value:
        errors.append(f"{field_name} is required")
        return
    if any(ch not in allowed for ch in value):
        errors.append(f"{field_name} contains unsupported characters: {value!r}")


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
