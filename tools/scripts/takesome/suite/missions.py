from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping

from ..console import console_emit
from ..progress import progress_configure, progress_update
from .actions import SuiteAction


def make_mission_runner(name: str, steps: tuple[SuiteAction, ...]) -> Callable[[Path], int]:
    """Create a linear production workflow from existing action descriptors."""

    def run(root: Path) -> int:
        total = max(1, len(steps))
        progress_configure(total=total, current=0, unit="step", phase=name)
        console_emit(f"[MISSION] {name}: {len(steps)} step(s)")
        for index, action in enumerate(steps, start=1):
            progress_update(current=index - 1, total=total, unit="step", phase=action.label)
            console_emit(f"[MISSION] Step {index}/{total}: [{action.primary_tag}] {action.label}")
            rc = int(action.run(root))
            if rc != 0:
                console_emit(f"[ERROR] Mission stopped at step {index}/{total}: {action.key} rc={rc}")
                progress_update(current=index, total=total, unit="step", phase="failed")
                return rc
        progress_update(current=total, total=total, unit="step", phase="completed")
        console_emit(f"[OK] Mission completed: {name}")
        return 0

    return run


def build_mission_actions(actions: Mapping[str, SuiteAction]) -> tuple[SuiteAction, ...]:
    """Build first-party workflow chains from already registered command intents.

    Mission composition lives here so `registry.py` remains focused on discovery
    and binding, while `missions.py` owns command chains.
    """

    return (
        SuiteAction(
            "mission.dev_smoke",
            "Dev Smoke",
            "sync workspace, inspect plugins, build active plugins, run demo",
            make_mission_runner(
                "Dev Smoke",
                (
                    actions["workspace.sync"],
                    actions["build.status"],
                    actions["build.plugins"],
                    actions["runtime.run"],
                ),
            ),
            "MISSION",
            "missions",
            "runtime",
            "runs_process",
            "active",
            progress_total=4,
            progress_unit="step",
        ),
        SuiteAction(
            "mission.plugin_maintenance",
            "Plugin Maintenance",
            "inspect stale plugins, rebuild active plugins, verify status",
            make_mission_runner(
                "Plugin Maintenance",
                (
                    actions["build.status"],
                    actions["build.plugins"],
                    actions["build.status"],
                ),
            ),
            "MISSION",
            "missions",
            "plugins",
            "writes_runtime_plugins",
            "active",
            progress_total=3,
            progress_unit="step",
        ),
    )
