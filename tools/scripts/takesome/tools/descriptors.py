from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..paths import engine_core_root, rel
from .constants import LEGACY_TOOL_PATHS, TOOL_SCHEMA

TOOL_SCHEMA_V2 = "takesome.tool.v2"


@dataclass(frozen=True)
class ToolDescriptor:
    id: str
    name: str
    kind: str
    descriptor_path: Path
    root: Path
    cargo_manifest: Path | None
    description: str
    default_args: list[str]
    validation_args: list[str]
    capabilities: list[str]
    build_validation: bool
    legacy_replaces: list[str]
    maturity: str
    safe_for_build: bool
    install_path: Path | None
    schema: str = TOOL_SCHEMA
    package_root: Path | None = None
    source_root: Path | None = None
    executable: Path | None = None
    expected_sha256: str = ""
    expected_size_bytes: int = 0
    commands: list[dict[str, Any]] | None = None
    source_type: str = "first_party"
    owner: str = "Take Some"
    safe_to_auto_run: bool = False

    def as_record(self, repo_root: Path) -> dict[str, Any]:
        executable = self.executable or self.install_path
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "schema": self.schema,
            "description": self.description,
            "source_type": self.source_type,
            "owner": self.owner,
            "maturity": self.maturity,
            "safe_for_build": self.safe_for_build,
            "safe_to_auto_run": self.safe_to_auto_run,
            "build_validation": self.build_validation,
            "root": rel(repo_root, self.root),
            "package_root": rel(repo_root, self.package_root) if self.package_root else "",
            "source_root": rel(repo_root, self.source_root) if self.source_root else "",
            "descriptor": rel(repo_root, self.descriptor_path),
            "descriptor_hash": descriptor_hash(self.descriptor_path),
            "cargo_manifest": rel(repo_root, self.cargo_manifest) if self.cargo_manifest else "",
            "cargo_package": cargo_bin_name(self) if self.kind == "rust-cli" else "",
            "target_debug": rel(repo_root, target_exe(self, False)) if self.kind == "rust-cli" else "",
            "target_release": rel(repo_root, target_exe(self, True)) if self.kind == "rust-cli" else "",
            "install_path": rel(repo_root, self.install_path) if self.install_path else "",
            "executable": rel(repo_root, executable) if executable else "",
            "expected_sha256": self.expected_sha256,
            "expected_size_bytes": self.expected_size_bytes,
            "default_args": self.default_args,
            "validation_args": self.validation_args,
            "capabilities": self.capabilities,
            "legacy_replaces": self.legacy_replaces,
            "commands": list(self.commands or []),
        }


def descriptor_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def string_list(value: Any) -> list[str]:
    return [str(x) for x in value] if isinstance(value, list) else []


def _descriptor_under_legacy_path(repo_root: Path, descriptor: Path) -> bool:
    try:
        rel_path = descriptor.resolve().relative_to(repo_root.resolve()).as_posix().lower()
    except ValueError:
        return False
    for raw in LEGACY_TOOL_PATHS:
        raw = raw.replace("\\", "/").strip("/").lower()
        if rel_path == raw or rel_path.startswith(raw + "/"):
            return True
    return False


def _repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _descriptor_relative_path(path: Path, value: str | Path) -> Path:
    raw = Path(value)
    return raw.resolve() if raw.is_absolute() else (path.parent / raw).resolve()


def read_descriptor(repo_root: Path, path: Path) -> ToolDescriptor:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {rel(repo_root, path)}: {exc}") from exc
    schema = str(data.get("schema", "")).strip()
    if schema not in {TOOL_SCHEMA, TOOL_SCHEMA_V2}:
        raise ValueError(f"unsupported tool schema in {rel(repo_root, path)}: {data.get('schema')!r}")
    if schema == TOOL_SCHEMA_V2:
        return read_descriptor_v2(repo_root, path, data)
    return read_descriptor_v1(repo_root, path, data)


def read_descriptor_v1(repo_root: Path, path: Path, data: dict[str, Any]) -> ToolDescriptor:
    tool_id = str(data.get("id", "")).strip()
    if not tool_id:
        raise ValueError(f"tool descriptor has empty id: {rel(repo_root, path)}")
    kind = str(data.get("kind", "")).strip() or "unknown"
    root_raw = str(data.get("root", ".")).strip() or "."
    tool_root = _descriptor_relative_path(path, root_raw)
    cargo_manifest_raw = str(data.get("cargo_manifest", "")).strip()
    cargo_manifest = (tool_root / cargo_manifest_raw).resolve() if cargo_manifest_raw else None
    install_raw = str(data.get("install_path", "")).strip()
    install_path = _repo_path(repo_root, install_raw) if install_raw else None
    return ToolDescriptor(
        id=tool_id,
        name=str(data.get("name", tool_id)).strip() or tool_id,
        kind=kind,
        description=str(data.get("description", "")).strip(),
        descriptor_path=path.resolve(),
        root=tool_root,
        cargo_manifest=cargo_manifest,
        default_args=string_list(data.get("default_args", [])),
        validation_args=string_list(data.get("validation_args", [])),
        capabilities=string_list(data.get("capabilities", [])),
        build_validation=bool(data.get("build_validation", False)),
        legacy_replaces=string_list(data.get("legacy_replaces", [])),
        maturity=str(data.get("maturity", "dev")).strip() or "dev",
        safe_for_build=bool(data.get("safe_for_build", False)),
        install_path=install_path,
    )


def read_descriptor_v2(repo_root: Path, path: Path, data: dict[str, Any]) -> ToolDescriptor:
    tool_id = str(data.get("id", "")).strip()
    if not tool_id:
        raise ValueError(f"tool descriptor has empty id: {rel(repo_root, path)}")
    kind = str(data.get("kind", "")).strip() or "external-cli"
    package_raw = str(data.get("package_root", "")).strip()
    package_root = _repo_path(repo_root, package_raw) if package_raw else path.parent.resolve()
    root_raw = str(data.get("root", ".")).strip() or "."
    tool_root = _repo_path(repo_root, root_raw)
    source_raw = str(data.get("source_root", "")).strip()
    source_root = _repo_path(repo_root, source_raw) if source_raw else None
    cargo_raw = str(data.get("cargo_manifest", "")).strip()
    cargo_manifest = _repo_path(repo_root, cargo_raw) if cargo_raw else None
    executable_raw = str(data.get("executable", "")).strip()
    executable = (package_root / executable_raw).resolve() if executable_raw else None
    install_raw = str(data.get("install_path", "")).strip()
    install_path = _repo_path(repo_root, install_raw) if install_raw else executable
    commands = data.get("commands", [])
    if not isinstance(commands, list):
        commands = []
    validation = data.get("validation", {})
    validation_args = string_list(validation.get("args", [])) if isinstance(validation, dict) else []
    default_args = string_list(data.get("default_args", []))
    if not default_args and commands:
        first = commands[0]
        if isinstance(first, dict):
            default_args = string_list(first.get("args", []))
    return ToolDescriptor(
        id=tool_id,
        name=str(data.get("name", tool_id)).strip() or tool_id,
        kind=kind,
        schema=TOOL_SCHEMA_V2,
        description=str(data.get("description", "")).strip(),
        descriptor_path=path.resolve(),
        root=tool_root,
        package_root=package_root,
        source_root=source_root,
        cargo_manifest=cargo_manifest,
        executable=executable,
        default_args=default_args,
        validation_args=validation_args,
        capabilities=string_list(data.get("capabilities", [])),
        build_validation=bool(data.get("build_validation", False)),
        legacy_replaces=string_list(data.get("legacy_replaces", [])),
        maturity=str(data.get("maturity", "vendor-provisional")).strip() or "vendor-provisional",
        safe_for_build=bool(data.get("safe_for_build", False)),
        install_path=install_path,
        expected_sha256=str(data.get("expected_sha256", "")).strip(),
        expected_size_bytes=int(data.get("expected_size_bytes", 0) or 0),
        commands=[dict(x) for x in commands if isinstance(x, dict)],
        source_type=str(data.get("source_type", "third_party")).strip() or "third_party",
        owner=str(data.get("owner", "third-party")).strip() or "third-party",
        safe_to_auto_run=bool(data.get("safe_to_auto_run", False)),
    )


def discover_tools(repo_root: Path) -> tuple[list[ToolDescriptor], list[str]]:
    tools_root = repo_root / "tools"
    warnings: list[str] = []
    found: list[ToolDescriptor] = []
    if not tools_root.exists():
        return [], ["tools directory is missing"]
    preferred_root = tools_root / "toolbelt"
    roots = [preferred_root] if preferred_root.exists() else [tools_root]
    for scan_root in roots:
        for descriptor in sorted(scan_root.rglob("tool.json"), key=lambda p: p.as_posix().lower()):
            parts = set(descriptor.relative_to(tools_root).parts)
            if parts & {"target", "node_modules", ".git", "__pycache__"}:
                continue
            if _descriptor_under_legacy_path(repo_root, descriptor):
                continue
            try:
                tool = read_descriptor(repo_root, descriptor)
            except ValueError as exc:
                warnings.append(str(exc))
                continue
            for label, candidate in [("tool root", tool.root), ("package root", tool.package_root), ("source root", tool.source_root), ("cargo manifest", tool.cargo_manifest), ("executable", tool.executable)]:
                if candidate is None:
                    continue
                try:
                    candidate.relative_to(repo_root.resolve())
                except ValueError:
                    warnings.append(f"{label} escapes repository: {rel(repo_root, descriptor)} -> {candidate}")
                    break
            else:
                found.append(tool)
    ids: dict[str, Path] = {}
    unique: list[ToolDescriptor] = []
    for tool in found:
        key = tool.id.lower()
        if key in ids:
            warnings.append(f"duplicate tool id {tool.id!r}: {rel(repo_root, ids[key])} and {rel(repo_root, tool.descriptor_path)}")
            continue
        ids[key] = tool.descriptor_path
        unique.append(tool)
    return unique, warnings


def tool_by_id(repo_root: Path, tool_id: str) -> ToolDescriptor | None:
    tools, _ = discover_tools(repo_root)
    lowered = tool_id.lower()
    for tool in tools:
        if tool.id.lower() == lowered or tool.name.lower() == lowered:
            return tool
    return None


def cargo_bin_name(tool: ToolDescriptor) -> str:
    if tool.cargo_manifest is None or not tool.cargo_manifest.exists():
        return tool.root.name
    text = tool.cargo_manifest.read_text(encoding="utf-8", errors="replace")
    in_package = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_package = line == "[package]"
            continue
        if in_package and line.startswith("name") and "=" in line:
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return tool.root.name


def target_exe(tool: ToolDescriptor, release: bool) -> Path:
    if tool.schema == TOOL_SCHEMA_V2 and tool.executable is not None:
        return tool.executable
    profile = "release" if release else "debug"
    suffix = ".exe" if os.name == "nt" else ""
    return tool.root / "target" / profile / f"{cargo_bin_name(tool)}{suffix}"


def expand_tool_args(repo_root: Path, tool: ToolDescriptor, args: list[str]) -> list[str]:
    replacements = {
        "$repo_root": str(repo_root),
        "$tool_root": str(tool.root),
        "$package_root": str(tool.package_root or tool.root),
        "$source_root": str(tool.source_root or tool.root),
        "$engine_root": str(engine_core_root(repo_root)),
    }
    expanded: list[str] = []
    for arg in args:
        value = arg
        for key, replacement in replacements.items():
            value = value.replace(key, replacement)
        expanded.append(value)
    return expanded
