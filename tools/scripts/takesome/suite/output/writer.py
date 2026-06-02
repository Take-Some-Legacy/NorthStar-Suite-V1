from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .markdown_view import render_suite_output_markdown

_RUN_INDEX_LIMIT = 200


def _run_output_dir(root: Path, run_id: str, output_dir: str | Path | None = None) -> Path:
    if output_dir:
        raw = Path(output_dir)
        base = raw if raw.is_absolute() else root / raw
        return base / run_id
    return root / ".takesome" / "suite" / "runs" / run_id


def _runs_root(root: Path) -> Path:
    return root / ".takesome" / "suite" / "runs"


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_suite_output(root: Path, envelope: Dict[str, Any], output_dir: str | Path | None = None) -> Dict[str, Any]:
    run_id = str(envelope.get("run_id") or "suite-run")
    target = _run_output_dir(root, run_id, output_dir)
    target.mkdir(parents=True, exist_ok=True)

    result_path = target / "result.json"
    md_path = target / "result.md"
    diagnostics_path = target / "diagnostics.json"

    artifacts = list(envelope.get("artifacts") or [])
    for path, kind in ((result_path, "suite.output.json"), (md_path, "suite.output.markdown"), (diagnostics_path, "suite.diagnostics.json")):
        rel_path = _rel(root, path)
        if not any(isinstance(item, dict) and item.get("path") == rel_path for item in artifacts):
            artifacts.append({"kind": kind, "path": rel_path})
    envelope = {**envelope, "artifacts": artifacts}

    result_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    diagnostics_path.write_text(json.dumps(envelope.get("diagnostics") or [], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = render_suite_output_markdown(envelope)
    md_path.write_text(markdown, encoding="utf-8")
    _update_run_index(root, envelope, result_path, md_path, diagnostics_path)
    return envelope


def _update_run_index(root: Path, envelope: Dict[str, Any], result_path: Path, md_path: Path, diagnostics_path: Path) -> None:
    if not _is_inside_runs_root(root, result_path):
        return
    runs_root = _runs_root(root)
    runs_root.mkdir(parents=True, exist_ok=True)
    index_path = runs_root / "index.json"
    latest_path = runs_root / "latest.md"
    entry = {
        "run_id": envelope.get("run_id"),
        "action_id": envelope.get("action_id"),
        "status": envelope.get("status"),
        "result_schema": envelope.get("result_schema"),
        "started_at": envelope.get("started_at"),
        "finished_at": envelope.get("finished_at"),
        "duration_ms": envelope.get("duration_ms"),
        "summary": envelope.get("summary"),
        "result_json": _rel(root, result_path),
        "result_md": _rel(root, md_path),
        "diagnostics_json": _rel(root, diagnostics_path),
    }
    history: list[dict[str, Any]] = []
    if index_path.exists():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            raw_history = payload.get("history", []) if isinstance(payload, dict) else []
            history = [item for item in raw_history if isinstance(item, dict)]
        except Exception:
            history = []
    history = [item for item in history if item.get("run_id") != entry.get("run_id")]
    history.append(entry)
    history = history[-_RUN_INDEX_LIMIT:]
    payload = {
        "schema": "northstar.suite.run_index.v1",
        "latest": entry,
        "history_count": len(history),
        "history": history,
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest_path.write_text(_render_latest_markdown(payload), encoding="utf-8")


def _is_inside_runs_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(_runs_root(root).resolve())
        return True
    except ValueError:
        return False


def _render_latest_markdown(payload: dict[str, Any]) -> str:
    latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else {}
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    lines = [
        "# Suite run index",
        "",
        f"- schema: `{payload.get('schema')}`",
        f"- history_count: `{payload.get('history_count')}`",
        "",
        "## Latest",
        "",
        f"- run_id: `{latest.get('run_id')}`",
        f"- action_id: `{latest.get('action_id')}`",
        f"- status: `{latest.get('status')}`",
        f"- result_md: `{latest.get('result_md')}`",
        f"- result_json: `{latest.get('result_json')}`",
        "",
        "## Recent history",
        "",
    ]
    for item in reversed(history[-20:]):
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('status')}` `{item.get('action_id')}` `{item.get('run_id')}` → `{item.get('result_md')}`")
    return "\n".join(lines).rstrip() + "\n"
