from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json

from .suite_action_descriptor import SuiteActionDescriptor, SuiteActionValidationResult


DEFAULT_SUITE_ACTION_ROOTS = ("tools/suite/actions",)


@dataclass(frozen=True)
class SuiteActionRegistry:
    actions: tuple[SuiteActionDescriptor, ...]
    validation: tuple[SuiteActionValidationResult, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.validation) and not self.duplicates()

    def by_id(self) -> dict[str, SuiteActionDescriptor]:
        return {action.action_id: action for action in self.actions}

    def duplicates(self) -> dict[str, list[str]]:
        seen: dict[str, list[str]] = {}
        for action in self.actions:
            seen.setdefault(action.action_id, []).append(action.descriptor_path)
        return {action_id: paths for action_id, paths in seen.items() if len(paths) > 1}

    def as_dict(self) -> dict[str, Any]:
        duplicates = self.duplicates()
        return {
            "schema": "northstar.suite_action_registry.v1",
            "ok": self.ok,
            "summary": {
                "action_count": len(self.actions),
                "error_count": sum(len(item.errors) for item in self.validation),
                "warning_count": sum(len(item.warnings) for item in self.validation),
                "duplicate_action_ids": sorted(duplicates),
            },
            "actions": [action.as_dict() for action in sorted(self.actions, key=lambda item: (item.group, item.action_id))],
            "validation": [item.as_dict() for item in self.validation],
        }

    def write_json(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def write_markdown(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_suite_actions_markdown(self), encoding="utf-8")


def discover_suite_actions(repo_root: Path, roots: Iterable[str] = DEFAULT_SUITE_ACTION_ROOTS) -> SuiteActionRegistry:
    repo_root = repo_root.resolve()
    actions: list[SuiteActionDescriptor] = []
    validation: list[SuiteActionValidationResult] = []

    for root in roots:
        root_path = (repo_root / root).resolve()
        if not root_path.exists():
            continue
        for descriptor_path in sorted(root_path.rglob("*.json")):
            try:
                descriptor = SuiteActionDescriptor.from_file(descriptor_path, repo_root)
            except Exception as exc:  # noqa: BLE001 - audit should continue after bad descriptors.
                validation.append(
                    SuiteActionValidationResult(
                        action_id="<invalid>",
                        path=_repo_relative(descriptor_path, repo_root),
                        ok=False,
                        errors=(f"failed to parse descriptor: {exc}",),
                    )
                )
                continue
            actions.append(descriptor)
            validation.append(descriptor.validate())

    duplicate_map: dict[str, list[str]] = {}
    for descriptor in actions:
        duplicate_map.setdefault(descriptor.action_id, []).append(descriptor.descriptor_path)
    for action_id, paths in duplicate_map.items():
        if len(paths) <= 1:
            continue
        validation.append(
            SuiteActionValidationResult(
                action_id=action_id,
                path=", ".join(paths),
                ok=False,
                errors=("duplicate action_id; suite action ids must be unique",),
            )
        )

    return SuiteActionRegistry(actions=tuple(actions), validation=tuple(validation))


def render_suite_actions_markdown(registry: SuiteActionRegistry) -> str:
    lines: list[str] = [
        "# North Star Suite Actions",
        "",
        "> [!INFO] INFO BLOCK — назначение",
        "> **У нас сейчас:** этот файл генерируется из Suite action descriptors и является source of truth для меню/bridge/headless запуска.",
        ">",
        "> **Technical details (EN):** schema=`northstar.suite_action_registry.v1`; action dispatch goes through `takesome.py <command>`.",
        "",
        f"- Actions: `{len(registry.actions)}`",
        f"- Errors: `{sum(len(item.errors) for item in registry.validation)}`",
        f"- Warnings: `{sum(len(item.warnings) for item in registry.validation)}`",
        "",
    ]

    groups: dict[str, list[SuiteActionDescriptor]] = {}
    for action in registry.actions:
        groups.setdefault(action.group, []).append(action)

    for group in sorted(groups):
        lines.extend([f"## {group}", "", "| Action | Command | Menu | Danger | Outputs |", "|---|---|---:|---|---|"])
        for action in sorted(groups[group], key=lambda item: item.action_id):
            menu = "yes" if action.safe_for_menu else "no"
            command = " ".join([action.command, *action.args]).strip()
            outputs = ", ".join(f"`{item}`" for item in action.outputs) or "—"
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{action.action_id}`",
                        f"`{command}`",
                        menu,
                        action.danger_level,
                        outputs,
                    ]
                )
                + " |"
            )
        lines.append("")

    failed = [item for item in registry.validation if not item.ok]
    warned = [item for item in registry.validation if item.warnings]
    if failed:
        lines.extend(["## Blocking findings", ""])
        for item in failed:
            lines.append(f"### `{item.action_id}`")
            lines.append(f"- Descriptor: `{item.path}`")
            for error in item.errors:
                lines.append(f"- ERROR: {error}")
            lines.append("")
    if warned:
        lines.extend(["## Warnings", ""])
        for item in warned:
            lines.append(f"### `{item.action_id}`")
            lines.append(f"- Descriptor: `{item.path}`")
            for warning in item.warnings:
                lines.append(f"- WARN: {warning}")
            lines.append("")

    lines.extend(
        [
            "## Invariant",
            "",
            "```text",
            "Suite action is descriptor, not hardcoded button.",
            "Suite shell lists registry actions and dispatches through CommandBus.",
            "Every heavy action declares outputs and diagnostics.",
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
