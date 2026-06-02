from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from ..logs import TeeLog
from ..paths import rel
from .dataset_entry_value import dataset_entry_value_analysis


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slug(value: str, default: str = "dataset") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip("-._")
    return cleaned[:80] or default


def _safe_member_path(name: str) -> str | None:
    raw = name.replace("\\", "/").strip().strip('"')
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        return None
    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) if parts else None


def _archive_target(extracted_root: Path, archive: Path) -> Path:
    return extracted_root / _slug(archive.stem)


def _iter_archives(data_root: Path) -> list[Path]:
    if not data_root.exists():
        return []
    return sorted(
        {p for p in data_root.rglob("*.zip") if p.is_file()},
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _extract_archive(repo_root: Path, archive: Path, target: Path) -> dict[str, Any]:
    written = 0
    skipped = 0
    with zipfile.ZipFile(archive, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            member = _safe_member_path(info.filename)
            if member is None:
                skipped += 1
                continue
            dest = (target / member).resolve()
            try:
                dest.relative_to(target.resolve())
            except ValueError:
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            written += 1
    return {"files_written": written, "unsafe_skipped": skipped}


def dataset_lifecycle_cleanup(
    repo_root: Path,
    *,
    limit: int = 500,
    keep_archives: bool = False,
    log: TeeLog | None = None,
) -> int:
    own_log = log or TeeLog()
    data_root = repo_root / ".takesome" / "dataSet"
    archives_root = data_root / "archives"
    extracted_root = data_root / "extracted"
    index_root = data_root / "index"
    extracted_root.mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)

    archives = _iter_archives(data_root)[: max(1, limit)]
    records: list[dict[str, Any]] = []
    own_log.emit(f"[INFO] dataSet lifecycle: found {len(archives)} archive ingest object(s).")

    for archive in archives:
        source_mtime = int(archive.stat().st_mtime)
        source_size = archive.stat().st_size
        target = _archive_target(extracted_root, archive)
        manifest_path = target / ".northstar-dataset-manifest.json"
        target.mkdir(parents=True, exist_ok=True)
        extracted = False
        record: dict[str, Any] = {
            "archive_id": _slug(archive.stem),
            "archive_path": rel(repo_root, archive),
            "source_date_utc": source_mtime,
            "source_size_bytes": source_size,
            "extracted_path": rel(repo_root, target),
            "manifest_path": rel(repo_root, manifest_path),
            "archive_lifecycle": "keep_archives_debug" if keep_archives else "delete_after_materialization",
        }
        try:
            if not manifest_path.exists():
                extracted_info = _extract_archive(repo_root, archive, target)
                extracted = True
                manifest = {
                    "schema": "northstar.dataset.manifest.v1",
                    "archive_id": record["archive_id"],
                    "source_archive_path": record["archive_path"],
                    "source_date_utc": source_mtime,
                    "source_size_bytes": source_size,
                    "extracted_path": record["extracted_path"],
                    "file_count": extracted_info["files_written"],
                    "unsafe_skipped": extracted_info["unsafe_skipped"],
                    "topic_tags": [],
                    "mapped_engine_domains": [],
                    "parity_status": "unmapped",
                    "visible_gaps": [],
                    "forbidden_direct_copy_notes": [
                        "Reference/dataSet archive is behavioral corpus only; do not directly copy foreign source into North Star runtime."
                    ],
                    "materialized_at": _utc_now(),
                    "archive_lifecycle": record["archive_lifecycle"],
                }
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                record.update(extracted_info)
            else:
                record.update({"files_written": 0, "unsafe_skipped": 0, "already_materialized": True})
            if not keep_archives:
                archive.unlink()
                record["archive_deleted"] = True
            else:
                record["archive_deleted"] = False
            record["ok"] = True
            own_log.emit(
                f"[OK] {'extracted ' if extracted else ''}{record['archive_path']} -> {record['extracted_path']}"
                + ("; archive deleted" if record["archive_deleted"] else "; archive kept")
            )
        except Exception as exc:
            record.update({"ok": False, "error": str(exc), "archive_deleted": False})
            own_log.emit(f"[ERROR] dataSet lifecycle failed for {record['archive_path']}: {exc}")
        records.append(record)

    report = {
        "schema": "northstar.dataset.archive_lifecycle.v1",
        "updated_at": _utc_now(),
        "policy": {
            "archive_storage_role": "ingest_only",
            "authoritative_storage": ".takesome/dataSet/extracted",
            "delete_archives_after_materialization": not keep_archives,
            "archives_root": rel(repo_root, archives_root),
            "extracted_root": rel(repo_root, extracted_root),
        },
        "archive_count_seen": len(archives),
        "archive_count_deleted": sum(1 for item in records if item.get("archive_deleted")),
        "archive_count_kept": sum(1 for item in records if item.get("ok") and not item.get("archive_deleted")),
        "records": records,
    }
    report_path = index_root / "dataset-archive-lifecycle-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    own_log.emit(f"[OK] dataSet lifecycle report: {rel(repo_root, report_path)}")
    value_rc = dataset_entry_value_analysis(repo_root, log=own_log)
    return (0 if all(item.get("ok") for item in records) else 1) or value_rc
