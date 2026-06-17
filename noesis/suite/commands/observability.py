from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from ..paths import engine_core_root
from ..registry.suite_bridge_menu import write_bridge_menu_json


class _LogLike(Protocol):
    def emit(self, message: str) -> None: ...


def run_suite_observability_check(repo_root: Path, output_dir: Path | None = None, log: _LogLike | None = None) -> int:
    output_dir = output_dir or engine_core_root(repo_root) / "buildInfo" / "tools"
    errors, warnings, payload = build_suite_observability_report(repo_root, output_dir)
    if log:
        log.emit(f"[INFO] Suite observability report: {output_dir / 'SUITE_OBSERVABILITY.md'}")
        for warning in warnings:
            log.emit(f"[WARN] observability: {warning}")
        for error in errors:
            log.emit(f"[ERROR] observability: {error}")
        if errors:
            log.emit("[ERROR] Suite observability contract failed.")
        else:
            log.emit("[OK] Suite observability contract passed.")
    return 0 if not errors else 2


def build_suite_observability_report(repo_root: Path, output_dir: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    warnings: list[str] = []
    runs_root = repo_root / ".takesome" / "suite" / "runs"
    bridge_menu_path = write_bridge_menu_json(repo_root, output_path=output_dir / "SUITE_ACTIONS_BRIDGE_MENU.json")

    run_entries = _collect_run_entries(repo_root, runs_root, errors, warnings)
    bridge_errors, bridge_warnings = _check_bridge_menu(bridge_menu_path)
    errors.extend(bridge_errors)
    warnings.extend(bridge_warnings)

    payload = {
        "schema": "northstar.suite.observability_report.v1",
        "ok": not errors,
        "runs_root": _rel(repo_root, runs_root),
        "bridge_menu": _rel(repo_root, bridge_menu_path),
        "run_count_checked": len(run_entries),
        "errors": errors,
        "warnings": warnings,
        "runs": run_entries,
    }
    (output_dir / "SUITE_OBSERVABILITY.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "SUITE_OBSERVABILITY.md").write_text(_render_observability_markdown(payload), encoding="utf-8")
    return errors, warnings, payload


def _collect_run_entries(repo_root: Path, runs_root: Path, errors: list[str], warnings: list[str]) -> list[dict[str, Any]]:
    if not runs_root.exists():
        warnings.append(f"Suite runs root does not exist yet: {_rel(repo_root, runs_root)}")
        return []
    result_files = sorted(runs_root.glob("*/result.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:25]
    if not result_files:
        warnings.append(f"Suite runs root has no result.json files: {_rel(repo_root, runs_root)}")
        return []
    entries: list[dict[str, Any]] = []
    for result_path in result_files:
        run_dir = result_path.parent
        md_path = run_dir / "result.md"
        diagnostics_path = run_dir / "diagnostics.json"
        try:
            envelope = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - report exact broken artifact.
            errors.append(f"{_rel(repo_root, result_path)} is not valid JSON: {exc}")
            continue
        _check_envelope(repo_root, envelope, result_path, md_path, diagnostics_path, errors, warnings)
        entries.append({
            "run_id": envelope.get("run_id"),
            "action_id": envelope.get("action_id"),
            "status": envelope.get("status"),
            "result_schema": envelope.get("result_schema"),
            "result_json": _rel(repo_root, result_path),
            "result_md": _rel(repo_root, md_path),
            "diagnostics_json": _rel(repo_root, diagnostics_path),
        })
    index_path = runs_root / "index.json"
    latest_path = runs_root / "latest.md"
    if not index_path.exists():
        warnings.append("Suite run index is not present yet; run one structured suite command to generate it.")
    if not latest_path.exists():
        warnings.append("Suite latest.md is not present yet; run one structured suite command to generate it.")
    return entries


def _check_envelope(repo_root: Path, envelope: dict[str, Any], result_path: Path, md_path: Path, diagnostics_path: Path, errors: list[str], warnings: list[str]) -> None:
    rel_result = _rel(repo_root, result_path)
    for key in ("schema", "run_id", "action_id", "status", "summary", "result", "artifacts"):
        if key not in envelope:
            errors.append(f"{rel_result} missing {key}")
    if envelope.get("schema") != "northstar.suite.output.v1":
        errors.append(f"{rel_result} schema mismatch: {envelope.get('schema')}")
    if not md_path.exists():
        errors.append(f"missing readable markdown artifact: {_rel(repo_root, md_path)}")
    else:
        md = md_path.read_text(encoding="utf-8", errors="replace")
        for marker in ("# Suite action result", "## Summary", "## Artifacts"):
            if marker not in md:
                errors.append(f"{_rel(repo_root, md_path)} missing marker {marker!r}")
        if "```json" not in md and "```text" not in md:
            warnings.append(f"{_rel(repo_root, md_path)} has no fenced output block")
    if not diagnostics_path.exists():
        errors.append(f"missing diagnostics artifact: {_rel(repo_root, diagnostics_path)}")


def _check_bridge_menu(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"bridge menu JSON failed to load: {exc}"], warnings
    if payload.get("schema") != "northstar.suite.bridge_menu_actions.v1":
        errors.append("bridge menu schema mismatch")
    if payload.get("ok") is not True:
        errors.append("bridge menu reports ok=false")
    if not payload.get("actions"):
        errors.append("bridge menu has no actions")
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        if not str(action.get("descriptor_path") or "").startswith("tools/suite/actions/"):
            errors.append(f"bridge action {action.get('key')} is not descriptor-backed")
    return errors, warnings


def _render_observability_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Suite observability report",
        "",
        f"- schema: `{payload.get('schema')}`",
        f"- ok: `{payload.get('ok')}`",
        f"- runs_root: `{payload.get('runs_root')}`",
        f"- bridge_menu: `{payload.get('bridge_menu')}`",
        f"- run_count_checked: `{payload.get('run_count_checked')}`",
        "",
    ]
    if payload.get("errors"):
        lines.extend(["## Errors", ""])
        for item in payload.get("errors") or []:
            lines.append(f"- ERROR: {item}")
        lines.append("")
    if payload.get("warnings"):
        lines.extend(["## Warnings", ""])
        for item in payload.get("warnings") or []:
            lines.append(f"- WARN: {item}")
        lines.append("")
    lines.extend(["## Recent runs", ""])
    for item in payload.get("runs") or []:
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('status')}` `{item.get('action_id')}` `{item.get('run_id')}` → `{item.get('result_md')}`")
    lines.append("")
    return "\n".join(lines)


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
