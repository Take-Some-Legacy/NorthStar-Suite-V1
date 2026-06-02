from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


_DESCRIPTOR_NAME = "northstar.tool.json"
_ALLOWED_SOURCE_TYPES = {"first_party", "third_party", "reference", "quarantine"}
_ALLOWED_LIFECYCLES = {"active", "provisional", "reference", "quarantined", "deprecated", "remove"}
_ALLOWED_SAFETY = {"safe", "manual", "unsafe"}


@dataclass(frozen=True)
class ToolValidationResult:
    tool_id: str
    path: str
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "path": self.path,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    display_name: str
    owner: str
    category: str
    kind: str
    location: str
    source_type: str
    lifecycle: str
    safety: str
    auto_build: bool = False
    safe_for_build_validation: bool = False
    safe_to_auto_run: bool = False
    entrypoint: str | None = None
    build: dict[str, Any] = field(default_factory=dict)
    commands: tuple[dict[str, Any], ...] = ()
    validation: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)
    descriptor_path: str = ""

    @classmethod
    def from_file(cls, descriptor_path: Path, repo_root: Path) -> "ToolDescriptor":
        data = json.loads(descriptor_path.read_text(encoding="utf-8"))
        commands = tuple(dict(command) for command in data.get("commands", []))
        artifacts = tuple(str(artifact) for artifact in data.get("artifacts", []))
        return cls(
            tool_id=str(data["tool_id"]),
            display_name=str(data.get("display_name") or data["tool_id"]),
            owner=str(data.get("owner") or "unknown"),
            category=str(data.get("category") or "uncategorized"),
            kind=str(data.get("kind") or "unknown"),
            location=_normalize_repo_path(data.get("location") or descriptor_path.parent, repo_root),
            source_type=str(data.get("source_type") or "reference"),
            lifecycle=str(data.get("lifecycle") or "provisional"),
            safety=str(data.get("safety") or "manual"),
            auto_build=bool(data.get("auto_build", False)),
            safe_for_build_validation=bool(data.get("safe_for_build_validation", False)),
            safe_to_auto_run=bool(data.get("safe_to_auto_run", False)),
            entrypoint=data.get("entrypoint"),
            build=dict(data.get("build") or {}),
            commands=commands,
            validation=dict(data.get("validation") or {}),
            artifacts=artifacts,
            diagnostics=dict(data.get("diagnostics") or {}),
            descriptor_path=_normalize_repo_path(descriptor_path, repo_root),
        )

    def validate(self, repo_root: Path) -> ToolValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        _require_identifier(self.tool_id, "tool_id", errors)
        if self.source_type not in _ALLOWED_SOURCE_TYPES:
            errors.append(f"source_type must be one of {sorted(_ALLOWED_SOURCE_TYPES)}, got {self.source_type!r}")
        if self.lifecycle not in _ALLOWED_LIFECYCLES:
            errors.append(f"lifecycle must be one of {sorted(_ALLOWED_LIFECYCLES)}, got {self.lifecycle!r}")
        if self.safety not in _ALLOWED_SAFETY:
            errors.append(f"safety must be one of {sorted(_ALLOWED_SAFETY)}, got {self.safety!r}")

        location = _resolve_repo_path(repo_root, self.location, errors, "location")
        if location and not location.exists():
            errors.append(f"location does not exist: {self.location}")

        if self.safe_to_auto_run and self.safety != "safe":
            errors.append("safe_to_auto_run=true requires safety='safe'")
        if self.source_type in {"reference", "quarantine"} and self.safe_to_auto_run:
            errors.append("reference/quarantine tools must not be safe_to_auto_run")
        if self.lifecycle in {"quarantined", "remove"} and self.auto_build:
            errors.append("quarantined/remove tools must not auto_build")

        if self.build:
            build_system = self.build.get("system")
            if build_system not in {"cargo", "python", "none", None}:
                warnings.append(f"unknown build.system: {build_system!r}")
            manifest = self.build.get("manifest")
            if manifest and location:
                manifest_path = location / str(manifest)
                if not manifest_path.exists():
                    errors.append(f"build manifest does not exist: {_repo_relative(manifest_path, repo_root)}")

        if self.validation:
            args = self.validation.get("args")
            if args is not None and not isinstance(args, list):
                errors.append("validation.args must be a list when present")

        command_ids: set[str] = set()
        for command in self.commands:
            command_id = command.get("command_id")
            if not command_id:
                errors.append(f"tool {self.tool_id} has command without command_id")
                continue
            _require_identifier(str(command_id), "command_id", errors)
            if command_id in command_ids:
                errors.append(f"duplicate command_id {command_id!r}")
            command_ids.add(str(command_id))

        return ToolValidationResult(
            tool_id=self.tool_id,
            path=self.descriptor_path,
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "display_name": self.display_name,
            "owner": self.owner,
            "category": self.category,
            "kind": self.kind,
            "location": self.location,
            "source_type": self.source_type,
            "lifecycle": self.lifecycle,
            "safety": self.safety,
            "auto_build": self.auto_build,
            "safe_for_build_validation": self.safe_for_build_validation,
            "safe_to_auto_run": self.safe_to_auto_run,
            "entrypoint": self.entrypoint,
            "build": self.build,
            "commands": list(self.commands),
            "validation": self.validation,
            "artifacts": list(self.artifacts),
            "diagnostics": self.diagnostics,
            "descriptor_path": self.descriptor_path,
        }


def descriptor_name() -> str:
    return _DESCRIPTOR_NAME


def _require_identifier(value: str, field_name: str, errors: list[str]) -> None:
    if not value:
        errors.append(f"{field_name} is required")
        return
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(ch not in allowed for ch in value):
        errors.append(f"{field_name} contains unsupported characters: {value!r}")


def _normalize_repo_path(value: str | Path, repo_root: Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    return _repo_relative(path, repo_root)


def _resolve_repo_path(repo_root: Path, value: str, errors: list[str], field_name: str) -> Path | None:
    if not value:
        errors.append(f"{field_name} is required")
        return None
    path = Path(value)
    if path.is_absolute():
        candidate = path.resolve()
    else:
        candidate = (repo_root / path).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        errors.append(f"{field_name} escapes repository root: {value}")
        return None
    return candidate


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
