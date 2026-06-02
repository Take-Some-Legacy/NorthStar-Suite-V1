from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .git_health import GitHealthSnapshot, collect_git_health
from .incident_health import IncidentHealthSnapshot, collect_incident_health
from .plugin_health import PluginHealthSnapshot, collect_plugin_health
from .tool_health import ToolHealthSnapshot, collect_tool_health
from ..context import SuiteContext, load_suite_context


@dataclass(frozen=True)
class CockpitSnapshot:
    context: SuiteContext
    plugin_health: PluginHealthSnapshot
    tool_health: ToolHealthSnapshot
    git_health: GitHealthSnapshot
    incident_health: IncidentHealthSnapshot

    @property
    def workspace_health(self) -> str:
        severities = {
            self.plugin_health.health,
            self.tool_health.health,
            self.git_health.health,
        }
        if "error" in severities:
            return "error"
        if "warn" in severities:
            return "warn"
        return "ok"

    @property
    def workspace_line(self) -> str:
        health = self.workspace_health
        details: list[str] = []
        if self.plugin_health.stale:
            details.append(f"{self.plugin_health.stale} stale plugins/codecs")
        if self.plugin_health.invalid:
            details.append(f"{self.plugin_health.invalid} invalid plugin metadata")
        if self.tool_health.invalid:
            details.append(f"{self.tool_health.invalid} invalid tools")
        if self.git_health.available and self.git_health.dirty:
            details.append(f"{self.git_health.changed_files} changed files")
        if not details:
            details.append("ready")
        return f"{health} · {', '.join(details)}"

    @property
    def recommended_next(self) -> str:
        if self.tool_health.invalid:
            return "Validate tool registry"
        if self.plugin_health.invalid:
            return "Explain plugin state"
        if self.plugin_health.stale:
            return "Plugin Maintenance"
        if self.incident_health.exists:
            return "Review last incident"
        if self.git_health.available and self.git_health.dirty:
            return "Review Git batch"
        return "Dev Smoke"


def collect_cockpit_snapshot(root: Path) -> CockpitSnapshot:
    context = load_suite_context(root)
    return CockpitSnapshot(
        context=context,
        plugin_health=collect_plugin_health(root, profile=context.profile, platform_id=context.platform.id),
        tool_health=collect_tool_health(root),
        git_health=collect_git_health(root),
        incident_health=collect_incident_health(root),
    )
