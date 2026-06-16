from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

RULES_PATH = Path("tools/scripts/takesome/rules/noesis-chat-protocol.md")
DECISION_PATH = Path(".takesome/intelligence/workloop-decision.json")
TRACE_SUMMARY_PATH = Path(".takesome/intelligence/workloop-trace.md")
ASSIGNED_TASK_PATH = Path(".takesome/intelligence/assigned-task.md")
TASK_SCAN_PATH = Path(".takesome/intelligence/task-scan.json")


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
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(value, ensure_ascii=False) + "\n")


def extract_json_block(markdown: str) -> Dict[str, Any]:
    match = re.search(r"```json[^\n]*\n(.*?)\n```", markdown, re.S)
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def load_rules(root: Path) -> Dict[str, Any]:
    value = extract_json_block(read_text(root / RULES_PATH))
    if isinstance(value, dict) and value:
        return value
    raise RuntimeError(f"Missing or invalid Noesis chat rules file: {root / RULES_PATH}")


def chat_paths(root: Path, rules: Dict[str, Any]) -> Dict[str, Path]:
    cfg = rules.get("chat", {}) if isinstance(rules.get("chat"), dict) else {}
    directory = root / str(cfg.get("directory", ".takesome/intelligence/chat"))
    return {
        "dir": directory,
        "journal": directory / str(cfg.get("journal", "noesis-chat.jsonl")),
        "state": directory / str(cfg.get("state", "chat-state.json")),
        "noesis_md": directory / str(cfg.get("latest_noesis_to_assistant", "noesis-to-assistant.md")),
        "assistant_md": directory / str(cfg.get("latest_assistant_to_noesis", "assistant-to-noesis.md")),
        "unread_assistant": directory / str(cfg.get("unread_for_assistant", "unread-for-assistant.json")),
        "unread_noesis": directory / str(cfg.get("unread_for_noesis", "unread-for-noesis.json")),
    }


def _decision(root: Path) -> Dict[str, Any]:
    return read_json(root / DECISION_PATH)


def _selected_action_id(decision: Dict[str, Any]) -> str:
    final = decision.get("final") if isinstance(decision.get("final"), dict) else {}
    candidate = decision.get("selected_candidate") if isinstance(decision.get("selected_candidate"), dict) else {}
    assigned = decision.get("assigned_task") if isinstance(decision.get("assigned_task"), dict) else {}
    return str(final.get("assigned_task_id") or final.get("selected_action_id") or assigned.get("id") or candidate.get("action_id") or "")


def should_emit(decision: Dict[str, Any], rules: Dict[str, Any], force: bool = False) -> bool:
    if force:
        return True
    policy = rules.get("emit_policy", {}) if isinstance(rules.get("emit_policy"), dict) else {}
    stages = policy.get("emit_when_stage_any")
    if isinstance(stages, list) and stages:
        return str(decision.get("stage", "")) in {str(x) for x in stages}
    return False


def make_message(root: Path, rules: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
    decision = _decision(root)
    policy = rules.get("emit_policy", {}) if isinstance(rules.get("emit_policy"), dict) else {}
    template_root = rules.get("message_templates", {}) if isinstance(rules.get("message_templates"), dict) else {}
    template = template_root.get("noesis_cycle_message", {}) if isinstance(template_root.get("noesis_cycle_message"), dict) else {}
    stage = str(decision.get("stage") or "unknown")
    task_id = _selected_action_id(decision) or "unknown"
    decision_status = str(decision.get("status") or "unknown")
    final = decision.get("final") if isinstance(decision.get("final"), dict) else {}
    checks_failed = str(final.get("checks_failed") or decision.get("checks_failed") or "")
    text_template = str(template.get("text_template") or "Noesis status: stage={stage}, task={task_id}.")
    text = text_template.format(stage=stage, task_id=task_id, decision_status=decision_status, checks_failed=checks_failed)
    cycle = int(decision.get("cycle") or final.get("cycle") or 0)
    created = now_utc()
    raw_id = f"{created}|{cycle}|{stage}|{task_id}|{decision_status}"
    message_id = "msg-" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]
    attachments = template.get("attachments") if isinstance(template.get("attachments"), list) else []
    return {
        "schema": "noesis.suite.chat_message.v1",
        "id": message_id,
        "created_utc": created,
        "cycle": cycle,
        "from": str(policy.get("default_from") or "noesis"),
        "to": str(policy.get("default_to") or "assistant"),
        "kind": str(policy.get("default_kind") or "status_request"),
        "stage": stage,
        "task": task_id,
        "decision_status": decision_status,
        "text": text,
        "attachments": [str(x) for x in attachments],
        "requires_response": bool(policy.get("requires_response", True)),
        "ack": False,
        "force": bool(force),
    }


def render_noesis_message(message: Dict[str, Any]) -> str:
    attachments = "\n".join(f"- `{x}`" for x in message.get("attachments", []))
    return (
        "# Noesis -> Assistant\n\n"
        f"id: `{message.get('id')}`\n"
        f"created_utc: {message.get('created_utc')}\n"
        f"cycle: {message.get('cycle')}\n"
        f"stage: {message.get('stage')}\n"
        f"task: `{message.get('task')}`\n"
        f"decision_status: {message.get('decision_status')}\n"
        f"requires_response: {message.get('requires_response')}\n\n"
        "## Message\n\n"
        f"{message.get('text')}\n\n"
        "## Attachments\n\n"
        f"{attachments or "- none"}\n"
    )


def emit_from_state(root: Path, *, force: bool = False) -> Dict[str, Any]:
    rules = load_rules(root)
    paths = chat_paths(root, rules)
    decision = _decision(root)
    if not should_emit(decision, rules, force=force):
        return {"ok": True, "emitted": False, "reason": "emit_policy_not_matched"}
    message = make_message(root, rules, force=force)
    append_jsonl(paths["journal"], message)
    write_text(paths["noesis_md"], render_noesis_message(message))
    write_json(paths["unread_assistant"], message)
    state = {
        "schema": "noesis.suite.chat_state.v1",
        "updated_utc": now_utc(),
        "last_noesis_message_id": message.get("id"),
        "last_cycle": message.get("cycle"),
        "unread_for_assistant": True,
        "unread_for_noesis": paths["unread_noesis"].exists(),
        "chat_dir": str(paths["dir"]),
    }
    write_json(paths["state"], state)
    return {"ok": True, "emitted": True, "message": message, "state": state}


def reply(root: Path, text: str, *, kind: str = "assistant_reply") -> Dict[str, Any]:
    rules = load_rules(root)
    paths = chat_paths(root, rules)
    message = {
        "schema": "noesis.suite.chat_message.v1",
        "id": "msg-" + hashlib.sha256((now_utc() + text).encode("utf-8")).hexdigest()[:16],
        "created_utc": now_utc(),
        "from": "assistant",
        "to": "noesis",
        "kind": kind,
        "text": text,
        "ack": False,
    }
    append_jsonl(paths["journal"], message)
    write_text(paths["assistant_md"], "# Assistant -> Noesis\n\n" + text.rstrip() + "\n")
    write_json(paths["unread_noesis"], message)
    reply_policy = rules.get("reply_policy", {}) if isinstance(rules.get("reply_policy"), dict) else {}
    if reply_policy.get("mirror_to_operator_response", True):
        op_path = root / str(reply_policy.get("operator_response_path", ".takesome/intelligence/operator-response.md"))
        write_text(op_path, text.rstrip() + "\n")
    state = read_json(paths["state"])
    state.update({
        "schema": "noesis.suite.chat_state.v1",
        "updated_utc": now_utc(),
        "last_assistant_message_id": message.get("id"),
        "unread_for_noesis": True,
    })
    write_json(paths["state"], state)
    return {"ok": True, "message": message, "state": state}


def status(root: Path) -> Dict[str, Any]:
    rules = load_rules(root)
    paths = chat_paths(root, rules)
    state = read_json(paths["state"])
    return {
        "schema": "noesis.suite.chat_status.v1",
        "ok": True,
        "chat_dir": str(paths["dir"]),
        "journal_exists": paths["journal"].exists(),
        "noesis_to_assistant_exists": paths["noesis_md"].exists(),
        "assistant_to_noesis_exists": paths["assistant_md"].exists(),
        "unread_for_assistant": paths["unread_assistant"].exists(),
        "unread_for_noesis": paths["unread_noesis"].exists(),
        "state": state,
    }


def read_messages(root: Path, tail: int = 10) -> List[Dict[str, Any]]:
    rules = load_rules(root)
    journal = chat_paths(root, rules)["journal"]
    if not journal.exists():
        return []
    lines = journal.read_text(encoding="utf-8", errors="replace").splitlines()
    result: List[Dict[str, Any]] = []
    for line in lines[-max(1, tail):]:
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Noesis file-based assistant chat protocol")
    parser.add_argument("command", choices=["emit-from-state", "status", "read", "reply"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--tail", type=int, default=10)
    parser.add_argument("--text", default="")
    ns = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(ns.root).resolve()
    if ns.command == "emit-from-state":
        print(json.dumps(emit_from_state(root, force=ns.force), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "status":
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "read":
        print(json.dumps(read_messages(root, tail=ns.tail), ensure_ascii=False, indent=2))
        return 0
    if ns.command == "reply":
        if not ns.text:
            raise SystemExit("--text is required")
        print(json.dumps(reply(root, ns.text), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())


def emit_from_current_state(root: Path, *, force: bool = False) -> Dict[str, Any]:
    return emit_from_state(root, force=force)
