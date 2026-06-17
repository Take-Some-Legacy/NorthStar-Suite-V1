from __future__ import annotations

import json
from pathlib import Path

from ..logs import TeeLog
from ..paths import now_stamp, rel, suite_path, utc_iso
from ..status_cache import write_status_snapshot
from .constants import CACHE_SCHEMA, LEGACY_TOOL_IDENTITIES, LEGACY_TOOL_PATHS
from .descriptors import ToolDescriptor, discover_tools


def tool_cache_dir(repo_root: Path) -> Path:
    return suite_path(repo_root, "tools")


def write_tool_cache(repo_root: Path, tools: list[ToolDescriptor], warnings: list[str]) -> tuple[Path, Path]:
    out_dir = tool_cache_dir(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    capability_index: dict[str, list[str]] = {}
    for tool in tools:
        for capability in tool.capabilities:
            capability_index.setdefault(capability, []).append(tool.id)
    payload = {
        "schema": CACHE_SCHEMA,
        "generated_utc": utc_iso(),
        "root": str(repo_root),
        "summary": {
            "total": len(tools),
            "rust_cli": sum(1 for t in tools if t.kind == "rust-cli"),
            "safe_for_build": sum(1 for t in tools if t.safe_for_build),
            "build_validation": sum(1 for t in tools if t.build_validation),
            "warnings": len(warnings),
        },
        "selection_policy": {
            "discovery": "recursive tools/**/tool.json scan, legacy roots excluded",
            "cache": ".takesome/tools/tool-registry.json",
            "build_surface": "explicit tools build command only; plugin build never compiles tools",
            "validation_surface": "build_validation descriptors declare validation_args",
        },
        "legacy_policy": {
            "deleted_identities": LEGACY_TOOL_IDENTITIES,
            "deleted_paths": LEGACY_TOOL_PATHS,
        },
        "capability_index": capability_index,
        "tools": [t.as_record(repo_root) for t in tools],
        "warnings": warnings,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    json_path = out_dir / "tool-registry.json"
    dated_json_path = out_dir / f"tool-registry-{stamp}.json"
    json_path.write_text(text, encoding="utf-8")
    dated_json_path.write_text(text, encoding="utf-8")

    lines = [
        "# North Star / Take Some tool registry cache",
        "",
        f"- generated_utc: `{payload['generated_utc']}`",
        f"- total: `{len(tools)}`",
        f"- rust_cli: `{payload['summary']['rust_cli']}`",
        f"- safe_for_build: `{payload['summary']['safe_for_build']}`",
        f"- build_validation: `{payload['summary']['build_validation']}`",
        "",
        "| id | kind | maturity | safe_for_build | validation | root | default / validation args | capabilities |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    for tool in tools:
        arg_text = " ".join(tool.default_args) or "-"
        validation_text = " ".join(tool.validation_args) or "-"
        caps = ", ".join(f"`{c}`" for c in tool.capabilities) or "-"
        lines.append(
            f"| `{tool.id}` | `{tool.kind}` | `{tool.maturity}` | `{str(tool.safe_for_build).lower()}` | `{str(tool.build_validation).lower()}` | `{rel(repo_root, tool.root)}` | `{arg_text}` / `{validation_text}` | {caps} |"
        )
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {w}" for w in warnings)
    md_path = out_dir / "tool-registry.md"
    md_text = "\n".join(lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    write_status_snapshot(
        repo_root,
        "tool-registry",
        payload,
        summary_markdown=md_text,
        source="tools.cache.write_tool_cache",
    )
    return json_path, md_path


def scan_and_cache_tools(repo_root: Path, *, log: TeeLog | None = None) -> int:
    tools, warnings = discover_tools(repo_root)
    json_path, md_path = write_tool_cache(repo_root, tools, warnings)
    if log:
        log.emit(f"[INFO] Tool registry cache: {rel(repo_root, json_path)}")
        log.emit(f"[INFO] Tool registry report: {rel(repo_root, md_path)}")
        for warning in warnings:
            log.emit(f"[WARN] {warning}")
        log.emit(f"[OK] Discovered {len(tools)} native tool descriptor(s).")
    return 0 if not warnings else 1
