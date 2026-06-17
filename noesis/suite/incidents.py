from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Iterable

from .build_info import build_log_dir, file_manifest
from .cargo import build_state_root
from .console import colorize_script_line
from .paths import now_stamp, rel, suite_path, utc_iso


def safe_incident_name(value: str | None, *, fallback: str = "incident") -> str:
    raw = str(value or fallback).strip()
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw)
    return safe.strip("-._") or fallback


def incident_root(root: Path) -> Path:
    return suite_path(root, "incidents")


def _read_text(path: Path, *, limit_bytes: int = 2 * 1024 * 1024) -> str:
    try:
        data = path.read_bytes()[-limit_bytes:]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _tail_lines(path: Path, *, max_lines: int = 160) -> list[str]:
    text = _read_text(path)
    if not text:
        return []
    return text.splitlines()[-max_lines:]



def _write_missing_placeholder(root: Path, dest: Path, *, artifact_key: str, source: Path | None) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix.lower() == ".json":
        payload = {
            "schema": "takesome.incident.missingArtifact.v1",
            "artifact": artifact_key,
            "source": rel(root, source) if source is not None else "",
            "reason": "source artifact was not available when the incident was written",
            "generated_utc": utc_iso(),
        }
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        dest.write_text(
            "# Missing incident artifact\n\n"
            f"- artifact: `{artifact_key}`\n"
            f"- source: `{rel(root, source) if source is not None else ''}`\n"
            "- reason: `source artifact was not available when the incident was written`\n",
            encoding="utf-8",
        )
    return file_manifest(root, dest)

def _copy_if_exists(root: Path, source: Path, dest: Path) -> dict[str, Any]:
    if source.exists() and source.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    return file_manifest(root, dest)


def _latest_build_error_log(root: Path) -> Path | None:
    candidates = sorted(
        (p for p in root.glob("buildERR-*.log") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _ensure_workspace_registry(root: Path) -> tuple[Path | None, Path | None, str]:
    try:
        from .workspace_registry import build_workspace_registry, write_registry_files

        payload = build_workspace_registry(root)
        json_path, md_path = write_registry_files(root, payload)
        return json_path, md_path, "generated"
    except Exception as exc:
        latest_json = suite_path(root, "workspace", "workspace-registry-latest.json")
        latest_md = suite_path(root, "workspace", "workspace-registry-latest.md")
        return (latest_json if latest_json.exists() else None, latest_md if latest_md.exists() else None, f"failed: {exc}")


def _collect_latest_reports(root: Path) -> dict[str, Path | None]:
    workspace_json, workspace_md, _workspace_status = _ensure_workspace_registry(root)
    return {
        "plugin_build_latest": build_log_dir(root) / "plugin-build-latest.json",
        "plugin_build_latest_md": build_log_dir(root) / "plugin-build-latest.md",
        "plugin_status_latest": build_state_root(root) / "plugin-status-latest.json",
        "plugin_status_latest_md": build_state_root(root) / "plugin-status-latest.md",
        "workspace_registry_latest": workspace_json,
        "workspace_registry_latest_md": workspace_md,
    }


def _copy_reports(root: Path, incident_dir: Path, reports: dict[str, Path | None]) -> dict[str, dict[str, Any]]:
    copied: dict[str, dict[str, Any]] = {}
    names = {
        "plugin_build_latest": "plugin-build-latest.json",
        "plugin_build_latest_md": "plugin-build-latest.md",
        "plugin_status_latest": "plugin-status-latest.json",
        "plugin_status_latest_md": "plugin-status-latest.md",
        "workspace_registry_latest": "workspace-registry-latest.json",
        "workspace_registry_latest_md": "workspace-registry-latest.md",
    }
    for key, path in reports.items():
        dest = incident_dir / names.get(key, f"{key}.json")
        if path is None or not path.exists():
            copied[key] = _write_missing_placeholder(root, dest, artifact_key=key, source=path)
            continue
        copied[key] = _copy_if_exists(root, path, dest)
    return copied


def _recommended_next(kind: str, target: str, exit_code: int, error_log: Path | None) -> str:
    clean_target = safe_incident_name(target, fallback="target")
    if kind == "run":
        if "plugin" in clean_target.lower():
            return "Run Plugin Maintenance, then retry runGame with the same profile."
        return "Open the run log, fix the runtime/build failure, then retry runGame."
    if error_log and "locked" in _read_text(error_log).lower():
        return "Close running editor/runtime if a DLL is locked, then run Plugin Maintenance."
    if clean_target.lower() in {"tool-registry-validation", "suite-preflight", "target-selection"}:
        return "Run Workspace Doctor, fix blocking diagnostics, then retry the build."
    return "Close running editor if DLL is locked, then run Plugin Maintenance."


def write_incident_bundle(
    root: Path,
    *,
    kind: str,
    target: str | None,
    exit_code: int,
    primary_log: Path | None = None,
    error_log: Path | None = None,
    message: str = "",
    command: str = "",
    started_utc: str = "",
    finished_utc: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a production-style failure bundle under .takesome/incidents.

    This is the single Take Some incident path. Root-level buildERR-* logs remain
    operator shortcuts, while the incident directory owns the full diagnostic
    handoff payload.
    """

    target_name = safe_incident_name(target, fallback=kind or "incident")
    stamp = now_stamp()
    incident_id = f"incident-{stamp}-{target_name}"
    out_dir = incident_root(root) / incident_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if error_log is None or not error_log.exists():
        error_log = _latest_build_error_log(root)

    copied_logs: dict[str, dict[str, Any]] = {}
    if error_log is not None:
        copied_logs["source_error_log"] = file_manifest(root, error_log)
        copied_logs["error_log"] = _copy_if_exists(root, error_log, out_dir / error_log.name)
    else:
        copied_logs["source_error_log"] = file_manifest(root, root / f"buildERR-{target_name}.log")
        copied_logs["error_log"] = file_manifest(root, out_dir / f"buildERR-{target_name}.log")
    if primary_log is not None:
        copied_logs["source_primary_log"] = file_manifest(root, primary_log)
        copied_logs["primary_log"] = _copy_if_exists(root, primary_log, out_dir / primary_log.name)
    else:
        copied_logs["source_primary_log"] = file_manifest(root, out_dir / "primary.log")
        copied_logs["primary_log"] = file_manifest(root, out_dir / "primary.log")

    cargo_tail_source = error_log if error_log and error_log.exists() else primary_log
    cargo_tail_path = out_dir / "cargo-tail.txt"
    cargo_tail = _tail_lines(cargo_tail_source, max_lines=180) if cargo_tail_source else []
    cargo_tail_path.write_text("\n".join(cargo_tail) + ("\n" if cargo_tail else ""), encoding="utf-8")

    reports = _copy_reports(root, out_dir, _collect_latest_reports(root))
    next_step = _recommended_next(kind, target_name, exit_code, error_log)
    finished = finished_utc or utc_iso()

    payload: dict[str, Any] = {
        "schema": "takesome.incident.v1",
        "incident_id": incident_id,
        "kind": kind,
        "target": target_name,
        "exit_code": exit_code,
        "message": message,
        "command": command,
        "started_utc": started_utc,
        "finished_utc": finished,
        "root": str(root.resolve()),
        "next": next_step,
        "paths": {
            "incident_dir": rel(root, out_dir),
            "summary_md": rel(root, out_dir / "summary.md"),
            "incident_json": rel(root, out_dir / "incident.json"),
        },
        "logs": copied_logs,
        "reports": reports,
        "cargo_tail": file_manifest(root, cargo_tail_path),
        "extra": extra or {},
    }

    json_path = out_dir / "incident.json"
    summary_path = out_dir / "summary.md"
    json_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    json_path.write_text(json_text, encoding="utf-8")

    error_log_path = copied_logs.get("source_error_log", {}).get("path", "") or copied_logs.get("error_log", {}).get("path", "")
    primary_log_path = copied_logs.get("source_primary_log", {}).get("path", "") or copied_logs.get("primary_log", {}).get("path", "")
    lines = [
        f"# Take Some incident: {incident_id}",
        "",
        f"- kind: `{kind}`",
        f"- target: `{target_name}`",
        f"- exit_code: `{exit_code}`",
        f"- message: `{message}`",
        f"- command: `{command}`",
        f"- started_utc: `{started_utc}`",
        f"- finished_utc: `{finished}`",
        "",
        "## First files to open",
        "",
        f"1. `{error_log_path}`",
        f"2. `{primary_log_path}`",
        f"3. `{rel(root, cargo_tail_path)}`",
        "",
        "## Captured state",
        "",
        f"- plugin build: `{reports.get('plugin_build_latest', {}).get('path', '')}`",
        f"- plugin status: `{reports.get('plugin_status_latest', {}).get('path', '')}`",
        f"- workspace registry: `{reports.get('workspace_registry_latest', {}).get('path', '')}`",
        "",
        "## Next step",
        "",
        next_step,
        "",
        "## Cargo / process tail",
        "",
        "```text",
        *cargo_tail[-120:],
        "```",
        "",
    ]
    summary_text = "\n".join(lines)
    summary_path.write_text(summary_text, encoding="utf-8")

    root_json = root / "last-incident.json"
    root_md = root / "last-incident.md"
    root_json.write_text(json_text, encoding="utf-8")
    root_md.write_text(summary_text, encoding="utf-8")

    payload["paths"]["root_shortcut_json"] = rel(root, root_json)
    payload["paths"]["root_shortcut_md"] = rel(root, root_md)
    json_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    root_json.write_text(json_text, encoding="utf-8")
    return payload


def emit_incident_console_lines(root: Path, incident: dict[str, Any], *, label: str | None = None) -> None:
    target = incident.get("target", "target")
    kind = incident.get("kind", "action")
    logs = incident.get("logs", {})
    error_log = logs.get("source_error_log", {}).get("path", "") or logs.get("error_log", {}).get("path", "")
    diag = incident.get("paths", {}).get("summary_md", "")
    next_step = incident.get("next", "")
    title = label or ("Run" if kind == "run" else "Build")
    print(colorize_script_line(f"[ERROR] {title} failed: {target}"))
    if error_log:
        print(colorize_script_line(f"[LOG]   {error_log}"))
    if diag:
        print(colorize_script_line(f"[DIAG]  {diag}"))
    if next_step:
        print(colorize_script_line(f"[NEXT]  {next_step}"))
