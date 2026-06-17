from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import now_stamp, rel, suite_path, utc_iso

STATUS_CACHE_SCHEMA = "takesome.statusCache.v1"
STATUS_SNAPSHOT_SCHEMA = "takesome.statusSnapshot.v1"


def status_cache_dir(root: Path) -> Path:
    """Canonical cache for reusable diagnostics/status snapshots.

    This cache is intentionally not a temporary report directory. `collect-run`
    copies it into the diagnostic bundle before any post-bundle cleanup so status
    analyses performed earlier in the Suite session remain inspectable.
    """

    return suite_path(root, "status-cache")


def _safe_kind(kind: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in kind.strip().lower())
    cleaned = cleaned.strip(".-_")
    return cleaned or "status"


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def write_status_snapshot(
    root: Path,
    kind: str,
    payload: dict[str, Any],
    *,
    summary_markdown: str = "",
    source: str = "",
) -> tuple[Path, Path | None]:
    """Persist one status payload to `.takesome/status-cache/<kind>/`.

    The latest JSON keeps the original payload shape under `payload`, together
    with a small envelope that explains where it came from. This prevents every
    status provider from inventing its own cache layout while still preserving
    each provider's native schema.
    """

    safe = _safe_kind(kind)
    out_dir = status_cache_dir(root) / safe
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    envelope = {
        "schema": STATUS_SNAPSHOT_SCHEMA,
        "kind": safe,
        "source": source,
        "generated_utc": utc_iso(),
        "payload_schema": payload.get("schema", "") if isinstance(payload, dict) else "",
        "payload": payload,
    }
    text = json.dumps(envelope, indent=2, ensure_ascii=False, default=_json_default) + "\n"
    dated_json = out_dir / f"{safe}-{stamp}.json"
    latest_json = out_dir / f"{safe}-latest.json"
    dated_json.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    latest_md: Path | None = None
    if summary_markdown:
        latest_md = out_dir / f"{safe}-latest.md"
        dated_md = out_dir / f"{safe}-{stamp}.md"
        md_text = summary_markdown if summary_markdown.endswith("\n") else summary_markdown + "\n"
        dated_md.write_text(md_text, encoding="utf-8")
        latest_md.write_text(md_text, encoding="utf-8")
    return latest_json, latest_md


def read_latest_status_snapshot(root: Path, kind: str) -> dict[str, Any]:
    safe = _safe_kind(kind)
    path = status_cache_dir(root) / safe / f"{safe}-latest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def build_status_cache_index(root: Path) -> dict[str, Any]:
    base = status_cache_dir(root)
    snapshots: list[dict[str, Any]] = []
    if base.exists():
        for latest in sorted(base.glob("*/*-latest.json"), key=lambda p: p.as_posix().lower()):
            try:
                data = json.loads(latest.read_text(encoding="utf-8"))
            except Exception as exc:
                snapshots.append({
                    "kind": latest.parent.name,
                    "path": rel(root, latest),
                    "valid": False,
                    "error": str(exc),
                })
                continue
            if not isinstance(data, dict):
                data = {}
            try:
                size = latest.stat().st_size
            except OSError:
                size = 0
            snapshots.append({
                "kind": str(data.get("kind", latest.parent.name)),
                "path": rel(root, latest),
                "valid": True,
                "generated_utc": str(data.get("generated_utc", "")),
                "payload_schema": str(data.get("payload_schema", "")),
                "source": str(data.get("source", "")),
                "size_bytes": size,
            })
    return {
        "schema": STATUS_CACHE_SCHEMA,
        "generated_utc": utc_iso(),
        "root": rel(root, base),
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
    }


def write_status_cache_index(root: Path) -> Path:
    base = status_cache_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    payload = build_status_cache_index(root)
    path = base / "status-cache-index-latest.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
