from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TOOLBELT: list[dict[str, Any]] = [
    {
        "group": "status_and_diagnostics",
        "risk": "read_only",
        "tools": [
            "get_status",
            "get_operator_snapshot",
            "get_dataset_status",
            "list_recent_logs",
            "bridge_origin_status",
        ],
        "when": "first step before any long or mutating pass",
    },
    {
        "group": "search_and_read",
        "risk": "read_only",
        "tools": [
            "search_project_text",
            "search_dataset",
            "read_text_file",
            "list_project_tree",
        ],
        "when": "dataset-backed analysis and targeted source inspection",
    },
    {
        "group": "git_control",
        "risk": "read_only_or_vcs",
        "tools": [
            "git status --short",
            "git diff --stat",
            "git diff -- <path>",
            "git show HEAD:<path>",
        ],
        "when": "before and after every patch pass",
    },
    {
        "group": "suite_actions",
        "risk": "registry_bounded",
        "tools": [
            "list_suite_actions",
            "execute_suite_command",
        ],
        "when": "run registered Suite actions, not arbitrary shell commands",
    },
    {
        "group": "build_and_runtime",
        "risk": "bounded_process",
        "tools": [
            "python python -m noesis suite validate-build",
            "python python -m noesis suite plugin-status dev",
            "python python -m noesis suite build-plugins dev",
            "python python -m noesis suite run-game dev --check-plugins-only",
        ],
        "when": "after scans and before accepting a patch",
    },
    {
        "group": "cargo",
        "risk": "bounded_process",
        "tools": [
            "cargo --version",
            "cargo metadata --format-version 1",
            "cargo check -p <crate>",
            "cargo test -p <crate>",
            "cargo check --workspace",
            "cargo test --workspace",
        ],
        "when": "targeted Rust validation first, workspace validation as final gate",
    },
    {
        "group": "endless_stream",
        "risk": "writes_reports",
        "tools": [
            "python python -m noesis suite endless-stream --message <text>",
            "python python -m noesis suite endless-stream --message-file <path>",
            "python python -m noesis suite endless-stream --stdin",
        ],
        "when": "record chat/operator intent and produce transparent request/report artifacts",
    },
    {
        "group": "descriptor_tools",
        "risk": "descriptor_bounded",
        "tools": [
            "tool_registry",
            "tool_northstar_devspace",
            "tool_northstar_neui_packer",
        ],
        "when": "use first-party tool descriptors instead of ad-hoc local helpers",
    },
    {
        "group": "file_mutation",
        "risk": "writes_source",
        "tools": [
            "write_text_file",
            "delete_path with dry_run first",
        ],
        "when": "only after dataset context, scanner evidence and selected task are clear",
    },
    {
        "group": "bridge_maintenance",
        "risk": "bridge_reload",
        "tools": [
            "reload_bridge_origin",
            "restart_bridge_origin",
        ],
        "when": "only after bridge/tool exposure changes and status checks",
    },
]


MINIMAL_PASS_ORDER = [
    "get_status",
    "git status --short",
    "search_dataset",
    "search_project_text",
    "read_text_file",
    "write_text_file",
    "python python -m noesis suite endless-stream --message <text>",
    "python python -m noesis suite validate-build",
    "cargo check -p <crate>",
    "git diff --stat",
    "git diff",
]


def render_toolbelt_markdown() -> str:
    lines: list[str] = []
    lines.append("# North Star Suite Operator Toolbelt")
    lines.append("")
    lines.append("This file pins the simple, useful tools for safe Suite work.")
    lines.append("The Suite should prefer bounded registry tools, dataset-backed context and explicit diagnostics over ad-hoc shell behavior.")
    lines.append("")
    lines.append("## Tool groups")
    for group in TOOLBELT:
        lines.append("")
        lines.append(f"### {group['group']}")
        lines.append(f"- risk: `{group['risk']}`")
        lines.append(f"- when: {group['when']}")
        lines.append("- tools:")
        for tool in group["tools"]:
            lines.append(f"  - `{tool}`")
    lines.append("")
    lines.append("## Minimal pass order")
    for index, item in enumerate(MINIMAL_PASS_ORDER, start=1):
        lines.append(f"{index}. `{item}`")
    lines.append("")
    lines.append("## Invariants")
    lines.append("- No arbitrary shell as the default path.")
    lines.append("- No hidden confirmation alias; operator confirmation uses `-sudo`.")
    lines.append("- No source mutation without dataset context and git diff visibility.")
    lines.append("- Cargo is a first-class validation tool, but targeted crate checks should run before workspace-wide gates.")
    lines.append("")
    return "\n".join(lines)


def write_operator_toolbelt(root: Path) -> int:
    output_dir = root / ".takesome" / "suite" / "toolbelt"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "northstar.suite.operator_toolbelt.v1",
        "toolbelt": TOOLBELT,
        "minimal_pass_order": MINIMAL_PASS_ORDER,
        "confirmation_flag": "-sudo",
        "forbidden_confirmation_aliases": ["legacy affirmative aliases"],
    }
    json_path = output_dir / "operator_toolbelt.json"
    md_path = output_dir / "operator_toolbelt.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_toolbelt_markdown(), encoding="utf-8")
    print(f"[OK] Operator toolbelt pinned: {md_path}")
    print(f"[OK] Operator toolbelt json: {json_path}")
    return 0
