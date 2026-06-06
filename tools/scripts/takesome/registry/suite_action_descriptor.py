from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


_ALLOWED_DANGER_LEVELS = {"normal", "destructive", "manual", "unsafe"}
_ALLOWED_RISK_TIERS = {"read_only", "write", "destructive", "manual", "unsafe"}

_READ_ONLY_COMMANDS = {
    "diff-files",
    "fgrep-files",
    "inspect-ui",
    "inspect-ytd",
    "inspect-ytyp",
    "ns-count-lines",
    "ns-file-stat",
    "ns-list-dir",
    "ns-read-file",
    "ns-search-text",
    "ns-tree",
    "registry-preflight",
    "sdiff-files",
    "suite-actions-list",
    "suite-actions-validate",
    "tail-file",
    "tar-list",
    "tools-doctor",
    "tools-list",
    "tools-validate",
    "validate-ui",
    "validate-ytd",
    "validate-ytyp",
}

_WRITE_COMMAND_PREFIXES = (
    "build-",
    "extract-",
    "import-",
    "pack-",
    "run-",
    "sed-",
    "tar-create",
    "tar-extract",
    "third-party-test",
    "first-party-test",
    "touch-",
)


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

    def _metadata_bool(self, key: str) -> bool | None:
        if key not in self.metadata:
            return None
        value = self.metadata.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "y", "on"}:
                return True
            if lowered in {"0", "false", "no", "n", "off"}:
                return False
        return bool(value)

    def destructive_hint(self) -> bool:
        explicit = self._metadata_bool("destructiveHint")
        if explicit is not None:
            return explicit
        return self.danger_level in {"destructive", "unsafe"}

    def read_only_hint(self) -> bool:
        explicit = self._metadata_bool("readOnlyHint")
        if explicit is not None:
            return explicit
        if self.destructive_hint():
            return False
        if self.outputs:
            return False
        if self.command in _READ_ONLY_COMMANDS:
            return True
        if self.command.startswith(("inspect-", "validate-", "list-")):
            return True
        return False

    def idempotent_hint(self) -> bool:
        explicit = self._metadata_bool("idempotentHint")
        if explicit is not None:
            return explicit
        return self.read_only_hint()

    def risk_tier(self) -> str:
        explicit = str(self.metadata.get("riskTier") or "").strip()
        if explicit:
            return explicit
        if self.danger_level == "unsafe":
            return "unsafe"
        if self.danger_level == "manual":
            return "manual"
        if self.destructive_hint():
            return "destructive"
        if self.read_only_hint():
            return "read_only"
        if self.outputs or self.command.startswith(_WRITE_COMMAND_PREFIXES):
            return "write"
        return "write"

    def policy_dict(self) -> dict[str, Any]:
        return {
            "riskTier": self.risk_tier(),
            "readOnlyHint": self.read_only_hint(),
            "destructiveHint": self.destructive_hint(),
            "idempotentHint": self.idempotent_hint(),
        }

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
        explicit_risk = str(self.metadata.get("riskTier") or "").strip()
        if explicit_risk and explicit_risk not in _ALLOWED_RISK_TIERS:
            errors.append(f"riskTier must be one of {sorted(_ALLOWED_RISK_TIERS)}, got {explicit_risk!r}")
        if self.read_only_hint() and self.destructive_hint():
            errors.append("readOnlyHint and destructiveHint cannot both be true")
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
        data = {
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
        }
        data.update(self.policy_dict())
        data["metadata"] = self.metadata
        return data


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
