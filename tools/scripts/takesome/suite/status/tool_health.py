from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...status_cache import write_status_snapshot
from ...tools.descriptors import discover_tools
from ...paths import utc_iso


@dataclass(frozen=True)
class ToolHealthSnapshot:
    total: int
    invalid: int
    warnings: tuple[str, ...]

    @property
    def health(self) -> str:
        return "error" if self.invalid else "ok"

    def line(self) -> str:
        return f"{self.total} registered · {self.invalid} invalid"


def collect_tool_health(root: Path) -> ToolHealthSnapshot:
    tools, warnings = discover_tools(root)
    snapshot = ToolHealthSnapshot(total=len(tools), invalid=len(warnings), warnings=tuple(warnings))
    write_status_snapshot(
        root,
        "tool-health",
        {
            "schema": "takesome.toolHealth.v1",
            "generated_utc": utc_iso(),
            "total": snapshot.total,
            "invalid": snapshot.invalid,
            "warnings": list(snapshot.warnings),
        },
        source="suite.status.tool_health.collect_tool_health",
    )
    return snapshot
