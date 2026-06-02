from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from .contracts import BridgeContext, BridgeError, MAX_READ_BYTES_DEFAULT, MAX_SEARCH_FILE_BYTES, now_utc
from .paths import is_text_file, norm_rel, rel, slug
from .dataset_core import archive_info, dataset_dirs, dataset_root, iter_archives, safe_dataset_path, top_extracted_dirs


def status(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    dirs = dataset_dirs(ctx)
    archives = iter_archives(ctx, True) if dirs["root"].exists() else []
    extracted = top_extracted_dirs(ctx, 20)
    index_file = dirs["index"] / "dataset-index.json"
    browser_index = dirs["index"] / "dataset-browser-index.json"
    return {
        "dataSetDirectory": str(dirs["root"]),
        "exists": dirs["root"].exists(),
        "preferredMode": "directories_first",
        "zipFallback": False,
        "directories": {k: rel(ctx.root, v) for k, v in dirs.items()},
        "archive_count": len(archives),
        "newest_archives": [archive_info(ctx, p) for p in archives[:10]],
        "extracted_count": len(extracted),
        "newest_extracted": [rel(ctx.root, p) for p in extracted],
        "index": {
            "dataset_index": rel(ctx.root, index_file) if index_file.exists() else None,
            "browser_index": rel(ctx.root, browser_index) if browser_index.exists() else None,
        },
        "browser": {
            "enabled": dirs["extracted"].exists(),
            "root": rel(ctx.root, dirs["extracted"]),
            "tools": ["northstar.dataset_browse_directories", "northstar.dataset_profile_directory", "northstar.dataset_search_logic"],
        },
    }


def list_archives(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    limit = max(1, min(int(args.get("limit", 50)), 500))
    archives = iter_archives(ctx, bool(args.get("recursive", True)))
    return {"dataSetDirectory": str(dataset_root(ctx)), "archives": [archive_info(ctx, p) for p in archives[:limit]], "truncated": len(archives) > limit}


def scan_archive(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    archive = safe_dataset_path(ctx, str(args.get("archive_path", "")))
    limit = max(1, min(int(args.get("limit", 300)), 2000))
    entries: List[Dict[str, Any]] = []
    summary: Dict[str, int] = {}
    with zipfile.ZipFile(archive, "r") as zf:
        infos = zf.infolist()
        for info in infos:
            suffix = Path(info.filename).suffix.lower() or "<none>"
            summary[suffix] = summary.get(suffix, 0) + 1
            if len(entries) < limit:
                entries.append({"path": info.filename, "size_bytes": info.file_size, "compressed_size_bytes": info.compress_size, "is_dir": info.is_dir(), "text_like": is_text_file(Path(info.filename))})
    return {"archive": rel(dataset_root(ctx), archive), "entry_count": len(infos), "extension_summary": dict(sorted(summary.items(), key=lambda kv: (-kv[1], kv[0]))), "entries": entries, "truncated": len(infos) > limit}


def read_archive_member(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    archive = safe_dataset_path(ctx, str(args.get("archive_path", "")))
    member = str(args.get("member", ""))
    max_bytes = max(1, min(int(args.get("max_bytes", MAX_READ_BYTES_DEFAULT)), 2 * 1024 * 1024))
    if not is_text_file(Path(member)):
        raise BridgeError("archive member is not text-whitelisted", "not_text", {"member": member})
    with zipfile.ZipFile(archive, "r") as zf:
        info = zf.getinfo(member)
        data = zf.read(member)[:max_bytes]
    return {"archive": rel(dataset_root(ctx), archive), "member": member, "size_bytes": info.file_size, "truncated": info.file_size > len(data), "content": data.decode("utf-8", errors="replace")}


def search_archives(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query", ""))
    case = bool(args.get("case_sensitive", False))
    q_cmp = query if case else query.lower()
    limit = max(1, min(int(args.get("limit", 50)), 500))
    hits: List[Dict[str, Any]] = []
    for archive in iter_archives(ctx, True):
        if len(hits) >= limit:
            break
        name_cmp = archive.name if case else archive.name.lower()
        if q_cmp in name_cmp:
            hits.append({"archive": rel(dataset_root(ctx), archive), "match": "archive_name"})
            continue
        if not bool(args.get("search_content", False)):
            continue
        try:
            with zipfile.ZipFile(archive, "r") as zf:
                for info in zf.infolist()[:5000]:
                    if len(hits) >= limit:
                        break
                    if info.is_dir() or not is_text_file(Path(info.filename)) or info.file_size > MAX_SEARCH_FILE_BYTES:
                        continue
                    text = zf.read(info.filename).decode("utf-8", errors="replace")
                    hay = text if case else text.lower()
                    if q_cmp in hay:
                        hits.append({"archive": rel(dataset_root(ctx), archive), "member": info.filename, "match": "content"})
        except Exception as exc:
            hits.append({"archive": rel(dataset_root(ctx), archive), "error": str(exc)})
    return {"query": query, "hits": hits, "truncated": len(hits) >= limit}


def _materialized_target_for_archive(ctx: BridgeContext, archive: Path) -> Path:
    return dataset_dirs(ctx)["extracted"] / slug(archive.stem)


def _archive_manifest_payload(ctx: BridgeContext, archive: Path, target: Path, *, written: int, skipped: int, archive_lifecycle: str) -> Dict[str, Any]:
    return {
        "schema": "northstar.dataset.manifest.v1",
        "archive_id": slug(archive.stem),
        "source_archive_path": rel(ctx.root, archive),
        "source_date_utc": int(archive.stat().st_mtime),
        "source_size_bytes": archive.stat().st_size,
        "extracted_path": rel(ctx.root, target),
        "file_count": written,
        "unsafe_skipped": skipped,
        "topic_tags": [],
        "mapped_engine_domains": [],
        "parity_status": "unmapped",
        "visible_gaps": [],
        "forbidden_direct_copy_notes": [
            "Reference/dataSet archive is behavioral corpus only; do not directly copy foreign source into North Star runtime."
        ],
        "materialized_at": now_utc(),
        "archive_lifecycle": archive_lifecycle,
    }


def materialize_archives(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("dataset materialization requires write mode", "write_disabled")
    dirs = dataset_dirs(ctx)
    dirs["extracted"].mkdir(parents=True, exist_ok=True)
    out: List[Dict[str, Any]] = []
    limit = max(1, min(int(args.get("limit", 200) or 200), 1000))
    keep_archives = bool(args.get("keep_archives", False))
    delete_archives = bool(args.get("delete_archives", True)) and not keep_archives
    for archive in iter_archives(ctx, True)[:limit]:
        target = _materialized_target_for_archive(ctx, archive)
        manifest_path = target / ".northstar-dataset-manifest.json"
        archive_rel = rel(dataset_root(ctx), archive)
        target.mkdir(parents=True, exist_ok=True)
        record: Dict[str, Any] = {
            "archive": archive_rel,
            "target": rel(ctx.root, target),
            "archive_lifecycle": "delete_after_materialization" if delete_archives else "keep_archives_debug",
        }
        if target.exists() and manifest_path.exists():
            record.update({"skipped": True, "reason": "already_materialized"})
        else:
            written = 0
            skipped = 0
            with zipfile.ZipFile(archive, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    try:
                        rel_member = norm_rel(info.filename)
                    except BridgeError:
                        skipped += 1
                        continue
                    dest = (target / rel_member).resolve()
                    try:
                        dest.relative_to(target.resolve())
                    except ValueError:
                        skipped += 1
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, "r") as src, dest.open("wb") as fh:
                        shutil.copyfileobj(src, fh)
                    written += 1
            manifest = _archive_manifest_payload(
                ctx,
                archive,
                target,
                written=written,
                skipped=skipped,
                archive_lifecycle="delete_after_materialization" if delete_archives else "keep_archives_debug",
            )
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            record.update({"archive": archive_rel, "target": rel(ctx.root, target), **manifest})
        if delete_archives:
            try:
                archive.unlink()
                record["archive_deleted"] = True
            except OSError as exc:
                record["archive_deleted"] = False
                record["archive_delete_error"] = str(exc)
        else:
            record["archive_deleted"] = False
        out.append(record)
    return {"ok": True, "policy": "archives_are_ingest_only_delete_after_materialization", "materialized": out}


def purge_materialized_archives(ctx: BridgeContext, args: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.write_enabled:
        raise BridgeError("dataset archive purge requires write mode", "write_disabled")
    limit = max(1, min(int(args.get("limit", 1000) or 1000), 5000))
    dry_run = bool(args.get("dry_run", False))
    purged: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for archive in iter_archives(ctx, True)[:limit]:
        target = _materialized_target_for_archive(ctx, archive)
        manifest_path = target / ".northstar-dataset-manifest.json"
        item = {"archive": rel(dataset_root(ctx), archive), "target": rel(ctx.root, target)}
        if not manifest_path.exists():
            skipped.append({**item, "reason": "not_materialized"})
            continue
        if dry_run:
            purged.append({**item, "dry_run": True})
            continue
        archive.unlink()
        purged.append({**item, "deleted": True})
    return {
        "ok": True,
        "policy": "archives_are_ingest_only_delete_after_materialization",
        "dry_run": dry_run,
        "purged": purged,
        "skipped": skipped,
    }
