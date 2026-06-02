from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from .suite_action_registry import SuiteActionRegistry, discover_suite_actions
from .tool_registry import ToolRegistry, discover_tools


@dataclass(frozen=True)
class RegistryReport:
    tool_registry: ToolRegistry
    suite_registry: SuiteActionRegistry

    @property
    def ok(self) -> bool:
        return self.tool_registry.ok and self.suite_registry.ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "northstar.suite_tooling_registry_report.v1",
            "ok": self.ok,
            "tool_registry": self.tool_registry.as_dict(),
            "suite_action_registry": self.suite_registry.as_dict(),
        }

    def write_all(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "SUITE_TOOLING_REGISTRY.json").write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.tool_registry.write_json(output_dir / "TOOL_REGISTRY.json")
        self.tool_registry.write_markdown(output_dir / "TOOL_REGISTRY.md")
        self.suite_registry.write_json(output_dir / "SUITE_ACTIONS.json")
        self.suite_registry.write_markdown(output_dir / "SUITE_ACTIONS.md")
        (output_dir / "TOOL_AUDIT_FINDINGS.md").write_text(render_audit_findings(self), encoding="utf-8")


def build_registry_report(repo_root: Path) -> RegistryReport:
    return RegistryReport(
        tool_registry=discover_tools(repo_root),
        suite_registry=discover_suite_actions(repo_root),
    )


def render_audit_findings(report: RegistryReport) -> str:
    lines: list[str] = [
        "# North Star Tooling Audit Findings",
        "",
        "> [!INFO] INFO BLOCK — назначение",
        "> **У нас сейчас:** этот отчёт собирает blocking findings по ToolRegistry и SuiteActionRegistry.",
        ">",
        "> **Technical details (EN):** generated from descriptors; CI/build preflight can fail on ERROR entries.",
        "",
        f"- Overall OK: `{str(report.ok).lower()}`",
        "",
    ]

    _append_validation_block(
        lines,
        "Tool Registry",
        [item.as_dict() for item in report.tool_registry.validation],
        id_key="tool_id",
    )
    _append_validation_block(
        lines,
        "Suite Action Registry",
        [item.as_dict() for item in report.suite_registry.validation],
        id_key="action_id",
    )

    lines.extend(
        [
            "## Required next behavior",
            "",
            "```text",
            "tools.validate fails on ERROR.",
            "suite.doctor fails on ERROR.",
            "Warnings are visible but do not block build unless promoted by policy.",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _append_validation_block(lines: list[str], title: str, items: list[dict[str, Any]], id_key: str) -> None:
    errors = [item for item in items if item.get("errors")]
    warnings = [item for item in items if item.get("warnings")]
    lines.extend([f"## {title}", ""])
    if not errors and not warnings:
        lines.extend(["No findings.", ""])
        return
    for item in errors:
        lines.append(f"### `{item.get(id_key, '<unknown>')}`")
        lines.append(f"- Descriptor: `{item.get('path', '')}`")
        for error in item.get("errors", []):
            lines.append(f"- ERROR: {error}")
        lines.append("")
    for item in warnings:
        lines.append(f"### `{item.get(id_key, '<unknown>')}`")
        lines.append(f"- Descriptor: `{item.get('path', '')}`")
        for warning in item.get("warnings", []):
            lines.append(f"- WARN: {warning}")
        lines.append("")
