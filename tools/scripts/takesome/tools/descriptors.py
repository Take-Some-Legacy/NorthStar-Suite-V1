from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..paths import engine_core_root, rel
from .constants import LEGACY_TOOL_PATHS, TOOL_SCHEMA


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

    def as_record(self, repo_root: Path) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "maturity": self.maturity,
            "safe_for_build": self.safe_for_build,
            "build_validation": self.build_validation,
            "root": rel(repo_root, self.root),
            "descriptor": rel(repo_root, self.descriptor_path),
            "descriptor_hash": descriptor_hash(self.descriptor_path),
            "cargo_manifest": rel(repo_root, self.cargo_manifest) if self.cargo_manifest else "",
            "cargo_package": cargo_bin_name(self) if self.kind == "rust-cli" else "",
            "target_debug": rel(repo_root, target_exe(self, False)) if self.kind == "rust-cli" else "",
            "target_release": rel(repo_root, target_exe(self, True)) if self.kind == "rust-cli" else "",
            "install_path": rel(repo_root, self.install_path) if self.install_path else "",
            "default_args": self.default_args,
            "validation_args": self.validation_args,
            "capabilities": self.capabilities,
            "legacy_replaces": self.legacy_replaces,
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


def read_descriptor(repo_root: Path, path: Path) -> ToolDescriptor:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {rel(repo_root, path)}: {exc}") from exc
    if data.get("schema") != TOOL_SCHEMA:
        raise ValueError(f"unsupported tool schema in {rel(repo_root, path)}: {data.get('schema')!r}")
    tool_id = str(data.get("id", "")).strip()
    if not tool_id:
        raise ValueError(f"tool descriptor has empty id: {rel(repo_root, path)}")
    kind = str(data.get("kind", "")).strip() or "unknown"
    root_raw = str(data.get("root", ".")).strip() or "."
    tool_root = (path.parent / root_raw).resolve()
    cargo_manifest_raw = str(data.get("cargo_manifest", "")).strip()
    cargo_manifest = (tool_root / cargo_manifest_raw).resolve() if cargo_manifest_raw else None
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
        install_path=(repo_root / str(data.get("install_path", "")).strip()).resolve() if str(data.get("install_path", "")).strip() else None,
    )


def discover_tools(repo_root: Path) -> tuple[list[ToolDescriptor], list[str]]:
    tools_root = repo_root / "tools"
    warnings: list[str] = []
    found: list[ToolDescriptor] = []
    if not tools_root.exists():
        return [], ["tools directory is missing"]
    for descriptor in sorted(tools_root.rglob("tool.json"), key=lambda p: p.as_posix().lower()):
        parts = set(descriptor.relative_to(tools_root).parts)
        if parts & {"target", "node_modules", ".git"}:
            continue
        if _descriptor_under_legacy_path(repo_root, descriptor):
            continue
        try:
            tool = read_descriptor(repo_root, descriptor)
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        try:
            tool.root.relative_to(repo_root.resolve())
        except ValueError:
            warnings.append(f"tool root escapes repository: {rel(repo_root, descriptor)} -> {tool.root}")
            continue
        if tool.cargo_manifest is not None:
            try:
                tool.cargo_manifest.relative_to(repo_root.resolve())
            except ValueError:
                warnings.append(f"tool cargo manifest escapes repository: {rel(repo_root, descriptor)} -> {tool.cargo_manifest}")
                continue
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
    profile = "release" if release else "debug"
    suffix = ".exe" if os.name == "nt" else ""
    return tool.root / "target" / profile / f"{cargo_bin_name(tool)}{suffix}"


def expand_tool_args(repo_root: Path, tool: ToolDescriptor, args: list[str]) -> list[str]:
    replacements = {
        "$repo_root": str(repo_root),
        "$tool_root": str(tool.root),
        "$engine_root": str(engine_core_root(repo_root)),
    }
    expanded: list[str] = []
    for arg in args:
        value = arg
        for key, replacement in replacements.items():
            value = value.replace(key, replacement)
        expanded.append(value)
    return expanded
