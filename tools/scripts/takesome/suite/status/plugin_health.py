from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...console import (
    ANSI_BOLD,
    color_enabled,
    console_emit,
    paint,
    strip_ansi,
)
from ...console.theme import theme
from ...console_menu import ConsoleChoice, ConsoleMenuOption, interactive_menu_enabled, run_multi_select_menu
from ...paths import rel
from ...status_cache import write_status_snapshot
from ...plugin_build import build_plugins
from ...plugin_status import collect_plugin_status, stale_sync_targets, write_plugin_status_report
from ..context import load_suite_context


@dataclass(frozen=True)
class PluginHealthSnapshot:
    status: dict[str, Any]

    @property
    def summary(self) -> dict[str, Any]:
        raw = self.status.get("summary", {})
        return raw if isinstance(raw, dict) else {}

    @property
    def records(self) -> list[dict[str, Any]]:
        raw = self.status.get("records", [])
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    @property
    def total(self) -> int:
        return int(self.summary.get("total", 0) or 0)

    @property
    def plugin_total(self) -> int:
        return int(self.summary.get("plugins", 0) or 0)

    @property
    def codec_total(self) -> int:
        return int(self.summary.get("codec_workers", 0) or 0)

    @property
    def ready(self) -> int:
        return int(self.summary.get("up_to_date", 0) or 0)

    @property
    def stale(self) -> int:
        return int(self.summary.get("need_rebuild", 0) or 0)

    @property
    def invalid(self) -> int:
        return int(self.summary.get("invalid_metadata", 0) or 0)

    @property
    def skipped(self) -> int:
        return int(self.summary.get("disabled", 0) or 0) + int(self.summary.get("missing_source", 0) or 0)

    @property
    def health(self) -> str:
        if self.invalid:
            return "error"
        if self.stale:
            return "warn"
        return "ok"

    @property
    def build_targets(self) -> list[str]:
        return stale_sync_targets(self.status)

    def line(self) -> str:
        return f"{self.total} total · {self.ready} ready · {self.stale} stale"

    def plugin_line(self) -> str:
        plugin_records = [r for r in self.records if r.get("kind") == "plugin"]
        ready = sum(1 for r in plugin_records if r.get("status_key") == "up_to_date")
        stale = sum(1 for r in plugin_records if r.get("needs_rebuild"))
        return f"{len(plugin_records)} total · {ready} ready · {stale} stale"

    def codec_line(self) -> str:
        codec_records = [r for r in self.records if r.get("kind") == "codec-worker"]
        ready = sum(1 for r in codec_records if r.get("status_key") == "up_to_date")
        stale = sum(1 for r in codec_records if r.get("needs_rebuild"))
        return f"{len(codec_records)} total · {ready} ready · {stale} stale"


def collect_plugin_health(root: Path, *, profile: str | None = None, platform_id: str | None = None) -> PluginHealthSnapshot:
    context = load_suite_context(root)
    status = collect_plugin_status(
        root,
        build_type=profile or context.profile,
        platform_id=platform_id or context.platform.id,
    )
    write_status_snapshot(root, "plugin-health", status, source="suite.status.plugin_health.collect_plugin_health")
    return PluginHealthSnapshot(status=status)


def _style_status(record: dict[str, Any]) -> str:
    key = str(record.get("status_key", ""))
    label = {
        "up_to_date": "READY",
        "need_rebuild": "STALE",
        "invalid_metadata": "INVALID",
        "missing_source": "MISSING",
        "disabled": "DISABLED",
    }.get(key, str(record.get("status", key)).upper())
    if not color_enabled():
        return label
    current = theme()
    style = {
        "up_to_date": current.status_ok + ANSI_BOLD,
        "need_rebuild": current.status_warn + ANSI_BOLD,
        "invalid_metadata": current.status_error + ANSI_BOLD,
        "missing_source": current.status_error,
        "disabled": current.text_muted,
    }.get(key, current.status_info)
    return paint(label, style)


def _action_for(record: dict[str, Any]) -> str:
    if record.get("status_key") == "up_to_date":
        return "-"
    if record.get("status_key") in {"disabled", "missing_source"}:
        return "inspect"
    if record.get("needs_rebuild"):
        return "rebuild"
    return "inspect"


def _fit(text: str, width: int) -> str:
    plain = strip_ansi(text)
    if len(plain) <= width:
        return text + " " * (width - len(plain))
    if width <= 1:
        return "…"[:width]
    return plain[: width - 1] + "…"


def _record_label(record: dict[str, Any]) -> str:
    name = str(record.get("name", ""))
    kind = "codec" if record.get("kind") == "codec-worker" else "plugin"
    return f"{name} ({kind})"


def _record_detail(record: dict[str, Any]) -> str:
    status = _style_status(record)
    reason = str(record.get("reason", "")) or "no reason"
    action = _action_for(record)
    chunks = [status, reason, action]
    return " · ".join(chunks)


def _print_matrix(snapshot: PluginHealthSnapshot) -> None:
    status = snapshot.status
    console_emit("[STATUS] Plugin Health Matrix")
    print(f"  Profile : {status.get('build_type', '')}")
    print(f"  Platform: {status.get('platform', '')}")
    print()
    headers = ("Plugin", "Status", "Reason", "Action")
    widths = (28, 12, 46, 12)
    header_line = "  " + "  ".join(_fit(h, w) for h, w in zip(headers, widths))
    print(paint(header_line, theme().border_muted) if color_enabled() else header_line)
    print(paint("  " + "─" * (sum(widths) + 6), theme().border_muted) if color_enabled() else "  " + "-" * (sum(widths) + 6))
    for record in snapshot.records:
        name = str(record.get("name", ""))
        if record.get("kind") == "codec-worker":
            name = f"codec-{name}"
        name_text = paint(name, theme().text_heading) if color_enabled() else name
        row = "  " + "  ".join(
            [
                _fit(name_text, widths[0]),
                _fit(_style_status(record), widths[1]),
                _fit(str(record.get("reason", "")), widths[2]),
                _fit(_action_for(record), widths[3]),
            ]
        )
        print(row)


def _build_target_args(snapshot: PluginHealthSnapshot, targets: list[str], *, force: bool = False) -> list[str]:
    build_type = str(snapshot.status.get("build_type", "dev"))
    platform = str(snapshot.status.get("platform", ""))
    args: list[str] = []
    if targets:
        args.append(",".join(targets))
    args.append(build_type)
    if platform:
        args.extend(["--platform", platform])
    if force:
        args.append("--force")
    return args


def rebuild_stale_plugins(root: Path, *, force: bool = False) -> int:
    snapshot = collect_plugin_health(root)
    targets = snapshot.build_targets
    if not targets:
        console_emit("[OK] No stale buildable plugin/codec targets for active Suite context.")
        return 0
    console_emit(f"[BUILD] Rebuilding {len(targets)} stale target(s): {', '.join(targets)}")
    return build_plugins(root, _build_target_args(snapshot, targets, force=force), pause=False)


def force_rebuild_stale_plugins(root: Path) -> int:
    return rebuild_stale_plugins(root, force=True)


def explain_plugin_state(root: Path) -> int:
    snapshot = collect_plugin_health(root)
    latest_json, latest_md = write_plugin_status_report(root, snapshot.status)
    _print_matrix(snapshot)
    print()
    console_emit(f"[LOG] Plugin status JSON: {rel(root, latest_json)}")
    console_emit(f"[LOG] Plugin status MD: {rel(root, latest_md)}")
    print()
    for record in snapshot.records:
        reason = str(record.get("reason", ""))
        artifact = str(record.get("artifact", ""))
        stamp = str(record.get("stamp", ""))
        name = str(record.get("name", ""))
        status = str(record.get("status", ""))
        print(f"- {name}: {status} — {reason}")
        if artifact:
            print(f"  artifact: {artifact}")
        if stamp:
            print(f"  stamp:    {stamp}")
    return 0


def plugin_health_matrix(root: Path) -> int:
    snapshot = collect_plugin_health(root)
    latest_json, latest_md = write_plugin_status_report(root, snapshot.status)
    if not interactive_menu_enabled():
        _print_matrix(snapshot)
        console_emit(f"[LOG] Plugin status JSON: {rel(root, latest_json)}")
        console_emit(f"[LOG] Plugin status MD: {rel(root, latest_md)}")
        return 0

    choices: list[ConsoleChoice[dict[str, Any]]] = []
    for index, record in enumerate(snapshot.records, start=1):
        buildable = bool(record.get("needs_rebuild")) and record.get("status_key") not in {"disabled", "missing_source"}
        choices.append(
            ConsoleChoice(
                value=record,
                number=index,
                label=_record_label(record),
                detail=_record_detail(record),
                checked=buildable,
                marker="BUILD" if buildable else "STATUS",
            )
        )

    result = run_multi_select_menu(
        title=f"Plugin Health Matrix — {snapshot.status.get('build_type')} / {snapshot.status.get('platform')}",
        choices=choices,
        action_label="Rebuild selected",
        footer="A all  N none  F force rebuild  R reveal logs  D diagnostics  Enter rebuild  Esc back",
        options=[
            ConsoleMenuOption("select_all", "A", "Select all", "checks every row"),
            ConsoleMenuOption("select_none", "N", "Select none", "clears selection"),
            ConsoleMenuOption("force", "F", "Force rebuild selected", "ignores build stamps"),
            ConsoleMenuOption("reveal", "R", "Reveal logs", "prints status report paths"),
            ConsoleMenuOption("diagnostics", "D", "Diagnostics", "prints matrix details"),
            ConsoleMenuOption("cancel", "Q", "Back", "return to Suite"),
        ],
        default_checked=False,
    )

    if result.special in {"cancel", "quit", "back"}:
        return 0
    if result.special == "reveal":
        console_emit(f"[LOG] Plugin status JSON: {rel(root, latest_json)}")
        console_emit(f"[LOG] Plugin status MD: {rel(root, latest_md)}")
        return 0
    if result.special == "diagnostics":
        _print_matrix(snapshot)
        return 0

    selected_records = [record for record in result.selected_values if isinstance(record, dict)]
    targets: list[str] = []
    seen: set[str] = set()
    for record in selected_records:
        if record.get("status_key") in {"disabled", "missing_source"}:
            continue
        if not record.get("needs_rebuild") and result.special != "force":
            continue
        name = str(record.get("name", ""))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        targets.append(name)

    if not targets:
        console_emit("[OK] No selected buildable targets.")
        return 0
    force = result.special == "force"
    console_emit(f"[BUILD] {'Force rebuilding' if force else 'Rebuilding'} {len(targets)} selected target(s): {', '.join(targets)}")
    return build_plugins(root, _build_target_args(snapshot, targets, force=force), pause=False)
