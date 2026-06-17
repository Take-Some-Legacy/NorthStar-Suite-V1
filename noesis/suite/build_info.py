from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .paths import rel, suite_path, utc_iso


def build_log_dir(root: Path) -> Path:
    return suite_path(root, "buildLog")


def build_info_dir(root: Path) -> Path:
    """Compatibility name for callers that need the authoritative build-log root."""
    return build_log_dir(root)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_manifest(root: Path, path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {
            "path": rel(root, path),
            "exists": False,
            "size_bytes": 0,
            "sha256": "",
        }
    return {
        "path": rel(root, path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def record_build_info(records: list[dict] | None, **fields) -> None:
    if records is None:
        return
    records.append(fields)


def write_plugin_target_log_archive(
    root: Path,
    *,
    run_stamp: str,
    target_logs: list[Path],
) -> Path | None:
    """Archive per-target logs for multi-plugin runs.

    The files stay readable on disk, but the archive is the primary handoff
    artifact when a build selected more than one target.
    """
    seen_paths: set[str] = set()
    existing: list[Path] = []
    for path in target_logs:
        if not path.exists() or not path.is_file():
            continue
        key = str(path.resolve()).lower()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        existing.append(path)
    if len(existing) <= 1:
        return None
    out_dir = build_log_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"plugin-sync-{run_stamp}-items.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in existing:
            zf.write(path, f"plugin-logs/{path.name}")
    latest_archive = out_dir / "plugin-sync-latest-items.zip"
    shutil.copyfile(archive, latest_archive)
    return archive


def _artifact_records(root: Path, records: list[dict]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in records:
        raw = str(item.get("installed_path") or item.get("expected_path") or "")
        if not raw:
            continue
        path = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        manifest = file_manifest(root, path)
        manifest.update({
            "display_name": item.get("display_name", ""),
            "kind": item.get("kind", ""),
            "package_name": item.get("package_name", ""),
            "version": item.get("version", ""),
            "platform": item.get("platform", ""),
            "rust_target": item.get("rust_target", ""),
            "status": item.get("status", ""),
            "validity": item.get("validity", ""),
        })
        artifacts.append(manifest)
    return artifacts


def _log_payload(root: Path, current_log: Path, latest_log: Path, root_last_log: Path, log_archive: Path | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "current": file_manifest(root, current_log),
        "latest": file_manifest(root, latest_log),
        "root_last": file_manifest(root, root_last_log),
    }
    latest_target_archive = build_log_dir(root) / "plugin-sync-latest-items.zip"
    if log_archive is not None:
        payload["target_archive"] = file_manifest(root, log_archive)
        payload["latest_target_archive"] = file_manifest(root, latest_target_archive)
    elif latest_target_archive.exists():
        try:
            latest_target_archive.unlink()
        except OSError:
            pass
    return payload


def _write_main_manifest(root: Path, run_payload: dict[str, Any]) -> Path:
    out_dir = build_log_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "buildInfo.json"
    history: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_history = old.get("history", [])
            if isinstance(raw_history, list):
                history = [item for item in raw_history if isinstance(item, dict)]
        except Exception:
            history = []
    history.append(run_payload)
    history = history[-100:]
    main_payload = {
        "schema": "takesome.buildInfo.v2",
        "updated_utc": utc_iso(),
        "root": str(root),
        "latest": run_payload,
        "history": history,
    }
    manifest_path.write_text(json.dumps(main_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path


def write_plugin_build_info(
    root: Path,
    *,
    run_stamp: str,
    started_utc: str,
    finished_utc: str,
    args: list[str],
    build_type: str,
    exit_code: int,
    records: list[dict],
    current_log: Path,
    latest_log: Path,
    root_last_log: Path,
    log_archive: Path | None = None,
) -> tuple[Path, Path]:
    out_dir = build_log_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    built = sum(1 for item in records if item.get("status") == "built")
    skipped = sum(1 for item in records if item.get("status") == "skipped")
    failed = sum(1 for item in records if item.get("status") == "failed")
    invalid = sum(1 for item in records if item.get("validity") != "valid")
    artifacts = _artifact_records(root, records)
    platforms = sorted({str(item.get("platform", "")) for item in records if item.get("platform")})
    rust_targets = sorted({str(item.get("rust_target", "")) for item in records if item.get("rust_target")})
    valid_artifacts = [item for item in artifacts if item.get("exists")]
    logs = _log_payload(root, current_log, latest_log, root_last_log, log_archive)
    primary_log_artifact = logs.get("target_archive") or logs.get("current")

    payload = {
        "schema": "takesome.pluginBuildInfo.v2",
        "run_stamp": run_stamp,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "root": str(root),
        "args": args,
        "build_type": build_type,
        "platforms": platforms,
        "rust_targets": rust_targets,
        "exit_code": exit_code,
        "build_file": primary_log_artifact,
        "logs": logs,
        "summary": {
            "total": len(records),
            "built": built,
            "skipped": skipped,
            "failed": failed,
            "invalid": invalid,
            "valid": len(records) - invalid,
            "artifact_count": len(valid_artifacts),
        },
        "artifacts": artifacts,
        "records": records,
    }
    json_path = out_dir / f"plugin-build-{run_stamp}.json"
    md_path = out_dir / f"plugin-build-{run_stamp}.md"
    latest_json = out_dir / "plugin-build-latest.json"
    latest_md = out_dir / "plugin-build-latest.md"
    json_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")

    lines = [
        "# North Star / Take Some plugin buildInfo",
        "",
        f"- started_utc: `{started_utc}`",
        f"- finished_utc: `{finished_utc}`",
        f"- build_type: `{build_type}`",
        f"- platforms: `{', '.join(platforms) if platforms else 'host'}`",
        f"- rust_targets: `{', '.join(rust_targets) if rust_targets else 'host default'}`",
        f"- exit_code: `{exit_code}`",
        f"- build_file: `{primary_log_artifact.get('path', '') if isinstance(primary_log_artifact, dict) else ''}`",
        f"- artifact_count: `{len(valid_artifacts)}`",
        f"- hash: `{primary_log_artifact.get('sha256', '') if isinstance(primary_log_artifact, dict) else ''}`",
        "",
        "| status | validity | platform | kind | name | package | version | elapsed_ms | artifact | artifact_hash |",
        "|---|---|---|---|---|---|---:|---:|---|---|",
    ]
    artifact_by_path = {item.get("path", ""): item for item in artifacts}
    for item in records:
        artifact_path = item.get("installed_path", item.get("expected_path", ""))
        artifact = artifact_by_path.get(artifact_path, {})
        lines.append(
            "| {status} | {validity} | {platform} | {kind} | {display_name} | {package_name} | {version} | {elapsed_ms} | `{artifact}` | `{artifact_hash}` |".format(
                status=item.get("status", ""),
                validity=item.get("validity", ""),
                platform=item.get("platform", ""),
                kind=item.get("kind", ""),
                display_name=item.get("display_name", ""),
                package_name=item.get("package_name", ""),
                version=item.get("version", ""),
                elapsed_ms=item.get("elapsed_ms", ""),
                artifact=artifact_path,
                artifact_hash=artifact.get("sha256", ""),
            )
        )
    md_text = "\n".join(lines) + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    run_manifest = {
        "run_stamp": run_stamp,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "build_type": build_type,
        "platforms": platforms,
        "rust_targets": rust_targets,
        "exit_code": exit_code,
        "build_file": primary_log_artifact,
        "report_json": file_manifest(root, json_path),
        "report_md": file_manifest(root, md_path),
        "artifact_count": len(valid_artifacts),
        "artifacts": artifacts,
    }
    _write_main_manifest(root, run_manifest)
    return json_path, md_path
