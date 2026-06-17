from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import runpy
from pathlib import Path
from typing import Any, Dict, Iterable, List

RULES_PATH = Path("noesis/suite/rules/noesis-chat-protocol.md")

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
    if value:
        return value
    raise RuntimeError(f"Missing or invalid Noesis chat rules file: {root / RULES_PATH}")


def chat_paths(root: Path) -> Dict[str, Path]:
    files = resolve_files(root)
    required = {
        "decision": "workloop_decision",
        "journal": "chat_journal",
        "state": "chat_state",
        "noesis_md": "chat_noesis_to_assistant",
        "assistant_md": "chat_assistant_to_noesis",
        "unread_assistant": "chat_unread_for_assistant",
        "unread_noesis": "chat_unread_for_noesis",
    }
    missing = [file_key for file_key in required.values() if file_key not in files]
    if missing:
        raise RuntimeError("Noesis chat missing configured file keys: " + ", ".join(sorted(missing)))
    paths = {role: files[file_key] for role, file_key in required.items()}
    paths["dir"] = paths["journal"].parent
    return paths


def _flatten_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    final = decision.get("final") if isinstance(decision.get("final"), dict) else {}
    selected = decision.get("selected_candidate") if isinstance(decision.get("selected_candidate"), dict) else {}
    assigned = decision.get("assigned_task") if isinstance(decision.get("assigned_task"), dict) else {}
    return {
        "cycle": int(final.get("cycle") or decision.get("cycle") or 0),
        "stage": str(final.get("stage") or decision.get("stage") or ""),
        "task_id": str(final.get("assigned_task_id") or final.get("selected_action_id") or assigned.get("id") or selected.get("action_id") or ""),
        "decision_status": str(decision.get("status") or ""),
        "checks_failed": int(final.get("checks_failed") or decision.get("checks_failed") or 0),
    }


def should_emit(facts: Dict[str, Any], rules: Dict[str, Any], state: Dict[str, Any], *, force: bool = False) -> bool:
    if force:
        return True
    policy = rules.get("emit_policy", {}) if isinstance(rules.get("emit_policy"), dict) else {}
    stages = {str(x) for x in policy.get("emit_when_stage_any", []) if isinstance(x, str)}
    if stages and facts["stage"] not in stages:
        return False
    last = state.get("last_noesis_message") if isinstance(state.get("last_noesis_message"), dict) else {}
    if policy.get("dedupe_same_cycle", True) and int(last.get("cycle") or -1) == facts["cycle"]:
        return False
    if policy.get("dedupe_same_stage_and_task", False):
        if str(last.get("stage") or "") == facts["stage"] and str(last.get("task_id") or "") == facts["task_id"]:
            return False
    return True


def _attachment_paths(root: Path, template: Dict[str, Any]) -> List[str]:
    files = resolve_files(root)
    result: List[str] = []
    for key in template.get("attachment_file_keys", []):
        if isinstance(key, str) and key in files:
            result.append(str(files[key]))
    return result


def make_message(root: Path, rules: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
    paths = chat_paths(root)
    decision = read_json(paths["decision"])
    facts = _flatten_decision(decision)
    template_root = rules.get("message_templates", {}) if isinstance(rules.get("message_templates"), dict) else {}
    template = template_root.get("noesis_cycle_message", {}) if isinstance(template_root.get("noesis_cycle_message"), dict) else {}
    policy = rules.get("emit_policy", {}) if isinstance(rules.get("emit_policy"), dict) else {}
    generated = now_utc()
    attachments = _attachment_paths(root, template)
    text_template = str(template.get("text_template") or "")
    text = text_template.format(**facts, generated_utc=generated)
    digest = hashlib.sha256((generated + text).encode("utf-8")).hexdigest()[:16]
    return {
        "schema": "noesis.suite.chat_message.v1",
        "id": f"msg-{facts['cycle']:06d}-{digest}",
        "created_utc": generated,
        "cycle": facts["cycle"],
        "from": str(policy.get("default_from") or "noesis"),
        "to": str(policy.get("default_to") or "assistant"),
        "kind": str(policy.get("default_kind") or "status_request"),
        "stage": facts["stage"],
        "task_id": facts["task_id"],
        "decision_status": facts["decision_status"],
        "checks_failed": facts["checks_failed"],
        "requires_response": bool(policy.get("requires_response", True)),
        "text": text,
        "attachments": attachments,
        "root_context": root_context(root),
        "ack": False,
    }


def render_noesis_message(message: Dict[str, Any]) -> str:
    attachments = "\n".join(f"- `{item}`" for item in message.get("attachments", []) if isinstance(item, str))
    return (
        "# Noesis -> Assistant\n\n"
        f"created_utc: {message.get('created_utc')}\n"
        f"cycle: {message.get('cycle')}\n"
        f"stage: {message.get('stage')}\n"
        f"task_id: `{message.get('task_id')}`\n"
        f"kind: {message.get('kind')}\n"
        f"requires_response: {message.get('requires_response')}\n\n"
        f"{message.get('text', '')}\n\n"
        "## Attachments\n\n"
        f"{attachments}\n"
    )


def emit_from_state(root: Path, *, force: bool = False) -> Dict[str, Any]:
    rules = load_rules(root)
    paths = chat_paths(root)
    state = read_json(paths["state"])
    decision = read_json(paths["decision"])
    facts = _flatten_decision(decision)
    if not should_emit(facts, rules, state, force=force):
        heartbeat_utc = now_utc()
        state.update({
            "schema": "noesis.suite.chat_state.v1",
            "updated_utc": heartbeat_utc,
            "last_noesis_heartbeat_utc": heartbeat_utc,
            "last_seen_decision": facts,
            "last_emit_result": "emit_policy_not_matched_or_deduped",
            "unread_for_assistant": paths["unread_assistant"].exists(),
            "unread_for_noesis": paths["unread_noesis"].exists(),
            "chat_dir": str(paths["dir"]),
        })
        write_json(paths["state"], state)
        return {"ok": True, "emitted": False, "heartbeated": True, "reason": "emit_policy_not_matched_or_deduped", "facts": facts}
    message = make_message(root, rules, force=force)
    append_jsonl(paths["journal"], message)
    write_text(paths["noesis_md"], render_noesis_message(message))
    write_json(paths["unread_assistant"], message)
    state = {
        "schema": "noesis.suite.chat_state.v1",
        "updated_utc": message["created_utc"],
        "last_noesis_message": {"id": message["id"], "cycle": message["cycle"], "stage": message["stage"], "task_id": message["task_id"]},
        "unread_for_assistant": True,
        "unread_for_noesis": paths["unread_noesis"].exists(),
        "chat_dir": str(paths["dir"]),
    }
    write_json(paths["state"], state)
    return {"ok": True, "emitted": True, "message": message}


def reply(root: Path, text: str, *, kind: str = "assistant_reply") -> Dict[str, Any]:
    rules = load_rules(root)
    paths = chat_paths(root)
    policy = rules.get("reply_policy", {}) if isinstance(rules.get("reply_policy"), dict) else {}
    message = {
        "schema": "noesis.suite.chat_message.v1",
        "id": "reply-" + hashlib.sha256((now_utc() + text).encode("utf-8")).hexdigest()[:16],
        "created_utc": now_utc(),
        "from": "assistant",
        "to": "noesis",
        "kind": str(policy.get("default_reply_kind") or kind),
        "text": text,
        "ack": False,
    }
    append_jsonl(paths["journal"], message)
    write_text(paths["assistant_md"], "# Assistant -> Noesis\n\n" + text.rstrip() + "\n")
    write_json(paths["unread_noesis"], message)
    if policy.get("mirror_to_operator_response", True):
        files = resolve_files(root)
        key = str(policy.get("operator_response_file_key") or "operator_response")
        if key not in files:
            raise RuntimeError(f"Noesis chat reply policy references missing file key: {key}")
        write_text(files[key], text.rstrip() + "\n")
    state = read_json(paths["state"])
    state.update({
        "schema": "noesis.suite.chat_state.v1",
        "updated_utc": message["created_utc"],
        "last_assistant_reply": {"id": message["id"], "kind": message["kind"]},
        "unread_for_noesis": True,
    })
    write_json(paths["state"], state)
    return {"ok": True, "message": message}


def status(root: Path) -> Dict[str, Any]:
    paths = chat_paths(root)
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
    journal = chat_paths(root)["journal"]
    if not journal.exists():
        return []
    lines = journal.read_text(encoding="utf-8-sig", errors="replace").splitlines()[-max(1, tail):]
    out: List[Dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Noesis file-based assistant chat")
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
            raise SystemExit("--text is required for reply")
        print(json.dumps(reply(root, ns.text), ensure_ascii=False, indent=2))
        return 0
    return 2


def emit_from_current_state(root: Path, *, force: bool = False) -> Dict[str, Any]:
    return emit_from_state(root, force=force)


if __name__ == "__main__":
    raise SystemExit(_main())
