from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import runpy
from pathlib import Path
from typing import Any, Dict, Iterable

RULES_PATH = Path("tools/scripts/takesome/rules/noesis-source-apply-gate.md")

try:
    from .noesis_roots import resolve_files, root_context
except Exception:
    _module = runpy.run_path(str(Path(__file__).resolve().with_name("noesis_roots.py")))
    resolve_files = _module["resolve_files"]
    root_context = _module["root_context"]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        return ""


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(read_text(path))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def configured_paths(root: Path) -> Dict[str, Path]:
    files = resolve_files(root)
    required = {
        "review_packet": "task_artifact_current_review_packet",
        "request_current": "source_apply_request_current",
        "state": "source_apply_state",
        "events": "source_apply_events",
        "requests_dir": "source_apply_requests_dir",
    }
    missing = [value for value in required.values() if value not in files]
    if missing:
        raise RuntimeError("Noesis source apply file keys are missing from config: " + ", ".join(sorted(missing)))
    return {key: files[value] for key, value in required.items()}


def request_id(review_packet: Dict[str, Any], reason: str) -> str:
    payload = json.dumps({"review_packet": review_packet, "reason": reason, "time": now_utc()}, ensure_ascii=False, sort_keys=True)
    return "srcapply-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def render_request(envelope: Dict[str, Any]) -> str:
    return (
        "# Noesis Source Apply Request\n\n"
        f"schema: {envelope.get('schema')}\n"
        f"id: {envelope.get('id')}\n"
        f"created_utc: {envelope.get('created_utc')}\n"
        f"status: {envelope.get('status')}\n"
        f"source_apply_enabled: {envelope.get('source_apply_enabled')}\n"
        f"approval_required: {envelope.get('approval_required')}\n\n"
        "## Reason\n\n"
        f"{envelope.get('reason', '')}\n\n"
        "## Gate\n\n"
        "No source files were changed by this command. This request only records the approval gate.\n\n"
        "## Review Packet\n\n"
        "```json\n"
        + json.dumps(envelope.get("review_packet", {}), ensure_ascii=False, indent=2)
        + "\n```\n"
    )


def prepare(root: Path, *, reason: str = "") -> Dict[str, Any]:
    paths = configured_paths(root)
    review_packet = read_json(paths["review_packet"])
    created = now_utc()
    rid = request_id(review_packet, reason)
    envelope = {
        "schema": "noesis.suite.source_apply_request.v1",
        "id": rid,
        "created_utc": created,
        "updated_utc": created,
        "status": "approval_required",
        "source_apply_enabled": False,
        "approval_required": True,
        "auto_apply": False,
        "auto_commit": False,
        "auto_push": False,
        "reason": reason,
        "review_packet": review_packet,
        "root_context": root_context(root),
    }
    write_text(paths["request_current"], render_request(envelope))
    write_json(paths["requests_dir"] / f"{rid}.json", envelope)
    state = {
        "schema": "noesis.suite.source_apply_state.v1",
        "updated_utc": created,
        "status": "approval_required",
        "current_request_id": rid,
        "source_apply_enabled": False,
        "current_request": str(paths["request_current"]),
    }
    write_json(paths["state"], state)
    append_jsonl(paths["events"], {"schema": "noesis.suite.source_apply_event.v1", "created_utc": created, "kind": "request_prepared", "id": rid})
    return {"ok": True, "request": envelope, "request_md": str(paths["request_current"])}


def status(root: Path) -> Dict[str, Any]:
    paths = configured_paths(root)
    state = read_json(paths["state"])
    return {
        "schema": "noesis.suite.source_apply_status.v1",
        "ok": True,
        "generated_utc": now_utc(),
        "source_apply_enabled": False,
        "state": state,
        "paths": {key: str(value) for key, value in paths.items()},
    }


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Noesis source apply approval gate")
    parser.add_argument("command", choices=["status", "prepare"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--reason", default="")
    ns = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(ns.root).resolve()
    if ns.command == "status":
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "prepare":
        print(json.dumps(prepare(root, reason=ns.reason), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
