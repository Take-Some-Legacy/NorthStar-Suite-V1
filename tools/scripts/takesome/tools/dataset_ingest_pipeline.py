from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..logs import TeeLog
from ..paths import rel
from .dataset_entry_value import analyze_entry, dataset_entry_value_analysis
from .dataset_maturity import dataset_maturity_command

ARCHIVE_SUFFIXES = {".zip"}


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")



class DatasetHeartbeat:
    def __init__(self, repo_root: Path, log: TeeLog | None = None, interval_sec: float = 5.0) -> None:
        self.repo_root = repo_root
        self.log = log
        self.interval_sec = interval_sec
        self.started = time.monotonic()
        self.last = 0.0
        self.status_path = repo_root / ".takesome" / "dataSet" / "index" / "ingest-pipeline" / "heartbeat.json"

    def beat(self, stage: str, **fields: Any) -> None:
        now = time.monotonic()
        if now - self.last < self.interval_sec:
            return
        self.last = now
        elapsed = int(now - self.started)
        payload = {
            "schema": "northstar.dataset.ingest_heartbeat.v1",
            "updated_at": _now(),
            "stage": stage,
            "elapsed_sec": elapsed,
            "alive": True,
            **fields,
        }
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            self.status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        if self.log is not None:
            detail = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
            self.log.emit(f"[ALIVE] dataSet ingest heartbeat stage={stage} elapsed={elapsed}s {detail}".rstrip())


def _slug(value: str, default: str = "dataset") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug[:96] or default


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_member_path(name: str) -> Path | None:
    clean = name.replace("\\", "/").strip()
    if not clean or clean.startswith("/"):
        return None
    parts: list[str] = []
    for part in clean.split("/"):
        if not part or part in {".", ".."}:
            return None
        parts.append(part)
    return Path(*parts) if parts else None


def _dataset_roots(data_root: Path) -> list[Path]:
    roots = [data_root, data_root / "archives"]
    return [p for p in roots if p.exists()]


def _iter_root_archives(data_root: Path) -> list[Path]:
    seen: set[Path] = set()
    archives: list[Path] = []
    for root in _dataset_roots(data_root):
        for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            if child.is_file() and child.suffix.lower() in ARCHIVE_SUFFIXES and child not in seen:
                seen.add(child)
                archives.append(child)
    return archives


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": "northstar.dataset.ingest_state.v1", "archives": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("archives"), dict):
            return data
    except Exception:
        pass
    return {"schema": "northstar.dataset.ingest_state.v1", "archives": {}}


def _extract_archive(archive: Path, target: Path, heartbeat: DatasetHeartbeat | None = None) -> dict[str, Any]:
    target.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    with zipfile.ZipFile(archive, "r") as zf:
        members = zf.infolist()
        total = sum(1 for item in members if not item.is_dir())
        if heartbeat is not None:
            heartbeat.beat("extract", archive=archive.name, files_written=written, files_total=total)
        for info in members:
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
            if heartbeat is not None and (written == total or written % 1000 == 0):
                heartbeat.beat("extract", archive=archive.name, files_written=written, files_total=total)
    return {"files_written": written, "unsafe_skipped": skipped}

def _contains_files(path: Path) -> bool:
    if not path.exists():
        return False
    for item in path.rglob("*"):
        if item.is_file():
            return True
    return False


def _semantic_roots(target: Path) -> list[Path]:
    direct_dirs = sorted([p for p in target.iterdir() if p.is_dir() and _contains_files(p)], key=lambda p: p.name.lower()) if target.exists() else []
    direct_files = [p for p in target.iterdir() if p.is_file()] if target.exists() else []
    if len(direct_dirs) == 1 and not direct_files:
        nested_dirs = sorted([p for p in direct_dirs[0].iterdir() if p.is_dir() and _contains_files(p)], key=lambda p: p.name.lower())
        nested_files = [p for p in direct_dirs[0].iterdir() if p.is_file()]
        if len(nested_dirs) > 1 and not nested_files:
            return nested_dirs
    if len(direct_dirs) > 1:
        return direct_dirs
    return [target]


def _applicability(report: dict[str, Any]) -> dict[str, Any]:
    domains = list(report.get("mapped_engine_domains") or [])
    score = int(report.get("architectural_value_score") or 0)
    level = str(report.get("value_level") or "unknown")
    return {
        "value_score": score,
        "value_level": level,
        "domains": domains,
        "capability_candidates": report.get("capability_candidates") or [],
        "conformance_candidates": report.get("conformance_candidates") or [],
        "use_policy": "reference_behavior_only_no_direct_copy",
        "applies_to_foundation": any(d in domains for d in ["engine.assets", "engine.render", "engine.ui", "engine.world", "engine.scene", "engine.schema", "engine.time"]),
    }


def _write_particle(root: Path, archive_slug: str, particle_root: Path, report: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    data_root = root / ".takesome" / "dataSet"
    particles_root = data_root / "index" / "knowledge-particles" / archive_slug
    particles_root.mkdir(parents=True, exist_ok=True)
    particle_id = _slug(f"{archive_slug}-{particle_root.name}")
    payload = {
        "schema": "northstar.dataset.knowledge_particle.v1",
        "created_at": _now(),
        "particle_id": particle_id,
        "semantic_group": particle_root.name,
        "entry_path": rel(root, particle_root),
        "source": source,
        "classification": {
            "kind": "reference_dataset_fragment",
            "domains": report.get("mapped_engine_domains") or [],
            "topic_tags": report.get("topic_tags") or [],
            "risk_flags": report.get("risk_flags") or [],
        },
        "value": {
            "score": report.get("architectural_value_score"),
            "level": report.get("value_level"),
        },
        "applicability": _applicability(report),
        "recommended_actions": report.get("recommended_actions") or [],
        "forbidden_direct_copy_notes": report.get("forbidden_direct_copy_notes") or [],
    }
    json_path = particles_root / f"{particle_id}.json"
    md_path = particles_root / f"{particle_id}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join([
            f"# dataSet Knowledge Particle — {particle_id}",
            "",
            f"- path: `{payload['entry_path']}`",
            f"- value: `{payload['value']['level']}` / `{payload['value']['score']}`",
            f"- domains: `{', '.join(payload['classification']['domains'])}`",
            f"- use_policy: `{payload['applicability']['use_policy']}`",
            "",
        ]),
        encoding="utf-8",
    )
    return {**payload, "json_path": rel(root, json_path), "md_path": rel(root, md_path)}


def _render_report_md(report: dict[str, Any]) -> str:
    lines = [
        "# North Star dataSet Ingest Pipeline",
        "",
        f"- updated_at: `{report.get('updated_at')}`",
        f"- archives_seen: `{report.get('archives_seen')}`",
        f"- new_archives: `{report.get('new_archives')}`",
        f"- particles_written: `{report.get('particles_written')}`",
        "",
        "## Rule",
        "",
        "New archives in `.takesome/dataSet` or `.takesome/dataSet/archives` are ingest-only objects. The pipeline materializes them, classifies their semantic fragments, scores value/applicability and caches knowledge particles before build/runtime work continues.",
        "",
        "## Archives",
        "",
    ]
    for item in report.get("archives", []):
        lines.extend([
            f"### `{item.get('archive_path')}`",
            "",
            f"- status: `{item.get('status')}`",
            f"- digest: `{item.get('sha256', '')[:16]}`",
            f"- extracted: `{item.get('extracted_path', '')}`",
            f"- particles: `{len(item.get('particles') or [])}`",
            "",
        ])
        for particle in item.get("particles") or []:
            lines.append(f"- `{particle.get('particle_id')}` value=`{particle.get('value', {}).get('level')}` score=`{particle.get('value', {}).get('score')}` domains=`{', '.join(particle.get('classification', {}).get('domains') or [])}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def dataset_ingest_pipeline(repo_root: Path, *, keep_archives: bool = False, log: TeeLog | None = None) -> int:
    own_log = log or TeeLog()
    heartbeat = DatasetHeartbeat(repo_root, own_log)
    heartbeat.beat("start")
    data_root = repo_root / ".takesome" / "dataSet"
    extracted_root = data_root / "extracted"
    index_root = data_root / "index"
    reports_root = index_root / "ingest-pipeline"
    extracted_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)
    state_path = index_root / "dataset-ingest-state.json"
    state = _load_state(state_path)
    archives = _iter_root_archives(data_root)
    records: list[dict[str, Any]] = []
    processed = state.setdefault("archives", {})

    for archive in archives:
        digest = _sha256(archive)
        archive_key = digest
        if archive_key in processed:
            records.append({
                "archive_path": rel(repo_root, archive),
                "sha256": digest,
                "status": "already_processed",
                "extracted_path": processed[archive_key].get("extracted_path", ""),
                "particles": [],
            })
            continue
        archive_slug = _slug(archive.stem)
        target = extracted_root / archive_slug
        record: dict[str, Any] = {
            "archive_path": rel(repo_root, archive),
            "sha256": digest,
            "status": "processing",
            "extracted_path": rel(repo_root, target),
            "particles": [],
        }
        try:
            heartbeat.beat("archive", archive=archive.name, status="extracting")
            own_log.emit(f"[DATASET] ingest archive {record['archive_path']}")
            record["extract"] = _extract_archive(archive, target, heartbeat)
            semantic_roots = _semantic_roots(target)
            record["semantic_root_count"] = len(semantic_roots)
            heartbeat.beat("classify", archive=archive.name, semantic_roots=len(semantic_roots))
            for index, semantic_root in enumerate(semantic_roots, start=1):
                heartbeat.beat("analyze", archive=archive.name, semantic_root=semantic_root.name, semantic_index=index, semantic_total=len(semantic_roots))
                value_report = analyze_entry(repo_root, semantic_root, max_files=5000)
                particle = _write_particle(
                    repo_root,
                    archive_slug,
                    semantic_root,
                    value_report,
                    {"archive_path": record["archive_path"], "sha256": digest, "extracted_path": record["extracted_path"]},
                )
                record["particles"].append(particle)
            if not keep_archives:
                archive.unlink()
                record["archive_deleted"] = True
            else:
                record["archive_deleted"] = False
            record["status"] = "processed"
            processed[archive_key] = {
                "archive_path": record["archive_path"],
                "sha256": digest,
                "processed_at": _now(),
                "extracted_path": record["extracted_path"],
                "particle_count": len(record["particles"]),
                "archive_deleted": record["archive_deleted"],
            }
            own_log.emit(f"[OK] dataSet archive processed {record['archive_path']}")
            own_log.emit(f"     particles={len(record['particles'])} value_cache=knowledge-particles/{archive_slug}")
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            heartbeat.beat("error", archive=archive.name, error=str(exc))
            own_log.emit(f"[ERROR] dataSet ingest failed {record['archive_path']}")
            own_log.emit(f"        reason={exc}")
        records.append(record)

    new_count = sum(1 for r in records if r.get("status") == "processed")
    state["updated_at"] = _now()
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Rebuild value/maturity indexes after new materialization.  This is part of
    # the dataSet gate, not optional post-processing.
    value_rc = dataset_entry_value_analysis(repo_root, log=own_log) if new_count else 0
    maturity_rc = dataset_maturity_command(repo_root, SimpleNamespace(strict=False, no_write=False), log=own_log) if new_count else 0

    report = {
        "schema": "northstar.dataset.ingest_pipeline.v1",
        "updated_at": _now(),
        "policy": {
            "archive_roots": [rel(repo_root, p) for p in _dataset_roots(data_root)],
            "new_archive_rule": "root archives trigger materialize -> semantic split -> value/applicability classification -> knowledge-particle cache",
            "authoritative_cache": rel(repo_root, index_root / "knowledge-particles"),
            "keep_archives": keep_archives,
        },
        "archives_seen": len(archives),
        "new_archives": new_count,
        "particles_written": sum(len(r.get("particles") or []) for r in records),
        "archives": records,
        "post_checks": {
            "entry_value_exit_code": value_rc,
            "maturity_exit_code": maturity_rc,
        },
    }
    report_json = reports_root / "latest.json"
    report_md = reports_root / "latest.md"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(_render_report_md(report), encoding="utf-8")
    own_log.emit(f"[OK] dataSet ingest report: {rel(repo_root, report_md)}")
    if new_count == 0:
        own_log.emit("[OK] dataSet ingest: no new root archives")
    final_rc = (0 if all(r.get("status") in {"processed", "already_processed"} for r in records) else 1) or value_rc or maturity_rc
    heartbeat.beat("done", exit_code=final_rc, new_archives=new_count, particles=report.get("particles_written"))
    return final_rc
