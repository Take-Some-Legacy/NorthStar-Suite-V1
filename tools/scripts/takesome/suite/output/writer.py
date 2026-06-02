from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .markdown_view import render_suite_output_markdown


def _run_output_dir(root: Path, run_id: str, output_dir: str | Path | None = None) -> Path:
    if output_dir:
        raw = Path(output_dir)
        base = raw if raw.is_absolute() else root / raw
        return base / run_id
    return root / ".takesome" / "suite" / "runs" / run_id


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
    md_path.write_text(render_suite_output_markdown(envelope), encoding="utf-8")
    return envelope
