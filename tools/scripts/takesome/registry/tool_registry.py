from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json

from .tool_descriptor import ToolDescriptor, ToolValidationResult, descriptor_name


DEFAULT_TOOL_ROOTS = (
    "tools/northstar",
    "tools/third_party",
    "tools/reference",
    "tools/quarantine",
    "Importers",
)


@dataclass(frozen=True)
class ToolRegistry:
    tools: tuple[ToolDescriptor, ...]
    validation: tuple[ToolValidationResult, ...]

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.validation)

    def by_id(self) -> dict[str, ToolDescriptor]:
        return {tool.tool_id: tool for tool in self.tools}

    def duplicates(self) -> dict[str, list[str]]:
        seen: dict[str, list[str]] = {}
        for tool in self.tools:
            seen.setdefault(tool.tool_id, []).append(tool.descriptor_path)
        return {tool_id: paths for tool_id, paths in seen.items() if len(paths) > 1}

    def as_dict(self) -> dict[str, Any]:
        duplicates = self.duplicates()
        return {
            "schema": "northstar.tool_registry.v1",
            "ok": self.ok and not duplicates,
            "summary": {
                "tool_count": len(self.tools),
                "error_count": sum(len(item.errors) for item in self.validation),
                "warning_count": sum(len(item.warnings) for item in self.validation),
                "duplicate_tool_ids": sorted(duplicates),
            },
            "tools": [tool.as_dict() for tool in sorted(self.tools, key=lambda item: item.tool_id)],
            "validation": [item.as_dict() for item in self.validation],
        }

    def write_json(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def write_markdown(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_tool_registry_markdown(self), encoding="utf-8")


def discover_tools(repo_root: Path, roots: Iterable[str] = DEFAULT_TOOL_ROOTS) -> ToolRegistry:
    repo_root = repo_root.resolve()
    descriptors: list[ToolDescriptor] = []
    validation: list[ToolValidationResult] = []

    for root in roots:
        root_path = (repo_root / root).resolve()
        if not root_path.exists():
            continue
        for descriptor_path in sorted(root_path.rglob(descriptor_name())):
            try:
                descriptor = ToolDescriptor.from_file(descriptor_path, repo_root)
            except Exception as exc:  # noqa: BLE001 - descriptor audit must continue.
                rel = _repo_relative(descriptor_path, repo_root)
                validation.append(
                    ToolValidationResult(
                        tool_id="<invalid>",
                        path=rel,
                        ok=False,
                        errors=(f"failed to parse descriptor: {exc}",),
                    )
                )
                continue
            descriptors.append(descriptor)
            validation.append(descriptor.validate(repo_root))

    duplicate_map: dict[str, list[str]] = {}
    for descriptor in descriptors:
        duplicate_map.setdefault(descriptor.tool_id, []).append(descriptor.descriptor_path)
    for tool_id, paths in duplicate_map.items():
        if len(paths) <= 1:
            continue
        validation.append(
            ToolValidationResult(
                tool_id=tool_id,
                path=", ".join(paths),
                ok=False,
                errors=("duplicate tool_id; registry ids must be unique",),
            )
        )

    return ToolRegistry(tools=tuple(descriptors), validation=tuple(validation))


def render_tool_registry_markdown(registry: ToolRegistry) -> str:
    lines: list[str] = [
        "# North Star Tool Registry",
        "",
        "> [!INFO] INFO BLOCK — назначение",
        "> **У нас сейчас:** этот файл генерируется из `northstar.tool.json` descriptors и служит authoritative index для Suite/tooling plane.",
        ">",
        "> **Technical details (EN):** schema=`northstar.tool_registry.v1`; unknown/quarantine/reference tools must not be auto-run.",
        "",
        f"- Tools: `{len(registry.tools)}`",
        f"- Errors: `{sum(len(item.errors) for item in registry.validation)}`",
        f"- Warnings: `{sum(len(item.warnings) for item in registry.validation)}`",
        "",
        "| Tool | Category | Source | Lifecycle | Safety | Auto-run | Descriptor |",
        "|---|---|---|---|---|---:|---|",
    ]
    for tool in sorted(registry.tools, key=lambda item: item.tool_id):
        auto_run = "yes" if tool.safe_to_auto_run else "no"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{tool.tool_id}`",
                    _md(tool.category),
                    _md(tool.source_type),
                    _md(tool.lifecycle),
                    _md(tool.safety),
                    auto_run,
                    f"`{tool.descriptor_path}`",
                ]
            )
            + " |"
        )

    failed = [item for item in registry.validation if not item.ok]
    warned = [item for item in registry.validation if item.warnings]
    if failed:
        lines.extend(["", "## Blocking findings", ""])
        for item in failed:
            lines.append(f"### `{item.tool_id}`")
            lines.append("")
            lines.append(f"- Descriptor: `{item.path}`")
            for error in item.errors:
                lines.append(f"- ERROR: {error}")
            lines.append("")
    if warned:
        lines.extend(["", "## Warnings", ""])
        for item in warned:
            lines.append(f"### `{item.tool_id}`")
            lines.append("")
            lines.append(f"- Descriptor: `{item.path}`")
            for warning in item.warnings:
                lines.append(f"- WARN: {warning}")
            lines.append("")

    lines.extend(
        [
            "",
            "## Invariant",
            "",
            "```text",
            "Tool is declared, not guessed.",
            "Unknown tool is quarantined.",
            "Reference tool is never auto-run.",
            "Registry is source of truth.",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _md(value: str) -> str:
    return value.replace("|", "\\|")
