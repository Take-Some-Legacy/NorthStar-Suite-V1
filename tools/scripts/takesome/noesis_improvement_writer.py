from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


RULES_PATH = Path("tools/scripts/takesome/rules/noesis-improvement-writer.md")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def read_json(path: Path, default: Any) -> Any:
    raw = read_text(path)
    if not raw.strip():
        return default
    try:
        value = json.loads(raw)
    except Exception:
        return default
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def extract_json_block(markdown: str) -> Dict[str, Any]:
    match = re.search(r"```json\s*(.*?)\s*```", markdown, re.DOTALL | re.IGNORECASE)
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
    return {
        "schema": "noesis.suite.improvement_writer_rules.v1",
        "protocol": {
            "schema": "noesis.suite.improvement_packet.v1",
            "directory": ".takesome/intelligence/improvements",
            "state": "improvement-writer-state.json",
            "journal": "improvement-writer-events.jsonl",
            "current_markdown": "current-improvement.md",
            "current_draft_markdown": "current-improved-version.md",
            "current_review_json": "current-review-packet.json",
            "review_request_markdown": "assistant-review-request.md",
        },
        "trigger_policy": {
            "stage_any": ["self_improvement_requested"],
            "action_id_any": ["noesis.self_improvement.audit"],
            "write_once_per_cycle_action": True,
            "allow_force": True,
        },
        "safety_policy": {
            "mode": "artifact_only",
            "auto_apply_source_changes": False,
            "auto_commit": False,
            "auto_push": False,
            "requires_approval_for_source_write": True,
            "requires_approval_for_destructive": True,
        },
        "inputs": {
            "decision": ".takesome/intelligence/workloop-decision.json",
            "assigned_task": ".takesome/intelligence/assigned-task.json",
            "task_scan": ".takesome/intelligence/task-scan.json",
            "workloop_trace": ".takesome/intelligence/workloop-trace.md",
            "operator_response": ".takesome/intelligence/operator-response.md",
        },
        "packet": {
            "title": "Noesis Self-Improvement Packet",
            "draft_title": "Noesis Improved Version Draft",
            "review_title": "Noesis Review Request for Assistant",
            "default_focus": ["remove duplicated decision paths", "keep rules in Markdown rule files"],
            "candidate_sections": ["Observed state", "Detected risks", "Proposed improved version", "Draft patch request", "Validation plan", "Approval gate"],
            "review_question": "Please review this generated improvement packet and decide which safe patch should be implemented next.",
        },
    }


def proto(root: Path) -> Dict[str, Any]:
    value = load_rules(root).get("protocol")
    return value if isinstance(value, dict) else {}


def out_dir(root: Path) -> Path:
    return root / str(proto(root).get("directory") or ".takesome/intelligence/improvements")


def out_path(root: Path, key: str) -> Path:
    return out_dir(root) / str(proto(root).get(key) or key)


def inputs(root: Path) -> Dict[str, Path]:
    value = load_rules(root).get("inputs")
    raw = value if isinstance(value, dict) else {}
    return {str(k): root / str(v) for k, v in raw.items()}


def state_path(root: Path) -> Path:
    return out_path(root, "state")


def journal_path(root: Path) -> Path:
    return out_path(root, "journal")


def load_state(root: Path) -> Dict[str, Any]:
    value = read_json(state_path(root), {})
    return value if isinstance(value, dict) else {}


def save_state(root: Path, state: Dict[str, Any]) -> None:
    payload = dict(state)
    payload.setdefault("schema", "noesis.suite.improvement_writer_state.v1")
    payload["updated_utc"] = utc_now()
    write_json(state_path(root), payload)


def selected_action_id(decision: Dict[str, Any]) -> str:
    final = decision.get("final") if isinstance(decision.get("final"), dict) else {}
    selected = decision.get("selected_candidate") if isinstance(decision.get("selected_candidate"), dict) else {}
    assigned = decision.get("assigned_task") if isinstance(decision.get("assigned_task"), dict) else {}
    return str(final.get("selected_action_id") or assigned.get("id") or selected.get("action_id") or "")


def current_context(root: Path) -> Dict[str, Any]:
    paths = inputs(root)
    decision = read_json(paths.get("decision", root / ".takesome/intelligence/workloop-decision.json"), {})
    scan = read_json(paths.get("task_scan", root / ".takesome/intelligence/task-scan.json"), {})
    assigned = read_json(paths.get("assigned_task", root / ".takesome/intelligence/assigned-task.json"), {})
    decision = decision if isinstance(decision, dict) else {}
    scan = scan if isinstance(scan, dict) else {}
    assigned = assigned if isinstance(assigned, dict) else {}
    final = decision.get("final") if isinstance(decision.get("final"), dict) else {}
    return {
        "generated_utc": utc_now(),
        "cycle": int(final.get("cycle") or decision.get("cycle") or 0),
        "stage": str(final.get("stage") or decision.get("stage") or ""),
        "status": str(decision.get("status") or ""),
        "selected_action_id": selected_action_id(decision),
        "assigned_task_id": str(final.get("assigned_task_id") or selected_action_id(decision)),
        "operator_response_kind": str(decision.get("operator_response_kind") or ""),
        "decision": decision,
        "task_scan": scan,
        "assigned": assigned,
        "operator_response_preview": read_text(paths.get("operator_response", root / ".takesome/intelligence/operator-response.md"))[:4000],
        "workloop_trace_preview": read_text(paths.get("workloop_trace", root / ".takesome/intelligence/workloop-trace.md"))[:4000],
    }


def triggered(root: Path, ctx: Dict[str, Any], *, force: bool = False) -> bool:
    rules = load_rules(root)
    policy = rules.get("trigger_policy") if isinstance(rules.get("trigger_policy"), dict) else {}
    if force and bool(policy.get("allow_force", True)):
        return True
    stage_any = [str(x) for x in (policy.get("stage_any") or [])]
    action_any = [str(x) for x in (policy.get("action_id_any") or [])]
    if stage_any and str(ctx.get("stage") or "") not in stage_any:
        return False
    if action_any and str(ctx.get("selected_action_id") or "") not in action_any:
        return False
    if bool(policy.get("write_once_per_cycle_action", True)):
        state = load_state(root)
        key = f"{ctx.get('cycle')}::{ctx.get('selected_action_id')}"
        if key and key == state.get("last_written_key"):
            return False
    return True


def stable_slug(ctx: Dict[str, Any]) -> str:
    seed = f"{ctx.get('cycle')}:{ctx.get('selected_action_id')}:{ctx.get('stage')}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    cycle = int(ctx.get("cycle") or 0)
    return f"cycle-{cycle:06d}-{digest}"


def list_failing_checks(scan: Dict[str, Any]) -> List[str]:
    cycle = scan.get("cycle") if isinstance(scan.get("cycle"), dict) else {}
    values = cycle.get("failing_checks") if isinstance(cycle, dict) else []
    return [str(item) for item in values] if isinstance(values, list) else []


def render_proposal(root: Path, ctx: Dict[str, Any], paths: Dict[str, str]) -> str:
    rules = load_rules(root)
    packet = rules.get("packet") if isinstance(rules.get("packet"), dict) else {}
    safety = rules.get("safety_policy") if isinstance(rules.get("safety_policy"), dict) else {}
    focus = [str(x) for x in (packet.get("default_focus") or [])]
    scan = ctx.get("task_scan") if isinstance(ctx.get("task_scan"), dict) else {}
    failing = list_failing_checks(scan)
    lines = [
        f"# {packet.get('title') or 'Noesis Self-Improvement Packet'}",
        "",
        f"schema: {proto(root).get('schema') or 'noesis.suite.improvement_packet.v1'}",
        f"generated_utc: {ctx.get('generated_utc')}",
        f"cycle: {ctx.get('cycle')}",
        f"stage: {ctx.get('stage')}",
        f"selected_action_id: {ctx.get('selected_action_id')}",
        f"assigned_task_id: {ctx.get('assigned_task_id')}",
        f"operator_response_kind: {ctx.get('operator_response_kind')}",
        "",
        "## Observed state",
        f"- decision status: `{ctx.get('status')}`",
        f"- failing checks: `{len(failing)}`",
        f"- worktree changed files: `{(((scan.get('repo') or {}) if isinstance(scan, dict) else {}).get('changed_file_count', ''))}`",
        "",
        "## Detected risks",
    ]
    if failing:
        lines.extend([f"- self-check failing: `{item}`" for item in failing])
    else:
        lines.append("- no failing checks listed in task scan")
    lines.extend([
        "",
        "## Proposed improved version",
    ])
    if focus:
        lines.extend([f"- {item}" for item in focus])
    else:
        lines.append("- continue read-only architecture audit and generate a concrete patch proposal")
    lines.extend([
        "",
        "## Draft patch request",
        "Create a reviewed source patch only after explicit approval. The next patch should be small, testable, and limited to the weakest link found by the current scan.",
        "",
        "## Validation plan",
        "- compile changed Python modules",
        "- run Noesis workloop once in --no-openai mode",
        "- verify workloop-decision.json, assigned-task.md and workloop-trace.md agree",
        "- verify git status does not include runtime/secrets",
        "",
        "## Approval gate",
        f"- auto_apply_source_changes: `{bool(safety.get('auto_apply_source_changes', False))}`",
        f"- auto_commit: `{bool(safety.get('auto_commit', False))}`",
        f"- auto_push: `{bool(safety.get('auto_push', False))}`",
        f"- requires_approval_for_source_write: `{bool(safety.get('requires_approval_for_source_write', True))}`",
        "",
        "## Generated artifacts",
    ])
    lines.extend([f"- `{value}`" for value in paths.values()])
    return "\n".join(lines).rstrip() + "\n"


def render_improved_version(root: Path, ctx: Dict[str, Any]) -> str:
    packet = load_rules(root).get("packet") if isinstance(load_rules(root).get("packet"), dict) else {}
    scan = ctx.get("task_scan") if isinstance(ctx.get("task_scan"), dict) else {}
    failing = list_failing_checks(scan)
    lines = [
        f"# {packet.get('draft_title') or 'Noesis Improved Version Draft'}",
        "",
        f"generated_utc: {ctx.get('generated_utc')}",
        f"cycle: {ctx.get('cycle')}",
        f"source_action: {ctx.get('selected_action_id')}",
        "",
        "## Improved behavior draft",
        "Noesis should produce a concrete improvement packet whenever the active workloop decision asks for self-improvement. The packet is an artifact-only draft and must not mutate source files without approval.",
        "",
        "## Current focus",
    ]
    if failing:
        lines.extend([f"- resolve or explain self-check: `{item}`" for item in failing])
    else:
        lines.append("- continue architecture improvement scan")
    lines.extend([
        "",
        "## Proposed next source patch",
        "The assistant/operator should review this draft and select one small source patch. Noesis may then prepare a reviewed patch request, but source edits remain gated by explicit approval.",
        "",
        "## Non-goals",
        "- no model provider required",
        "- no auto-apply",
        "- no auto-commit",
        "- no auto-push",
        "- no runtime/secrets tracking",
    ])
    return "\n".join(lines).rstrip() + "\n"


def render_review_request(root: Path, ctx: Dict[str, Any], paths: Dict[str, str]) -> str:
    packet = load_rules(root).get("packet") if isinstance(load_rules(root).get("packet"), dict) else {}
    return "\n".join([
        f"# {packet.get('review_title') or 'Noesis Review Request for Assistant'}",
        "",
        f"generated_utc: {ctx.get('generated_utc')}",
        f"cycle: {ctx.get('cycle')}",
        f"stage: {ctx.get('stage')}",
        f"task: {ctx.get('assigned_task_id')}",
        "",
        "## Request",
        str(packet.get("review_question") or "Review the generated improvement packet and choose the next safe patch."),
        "",
        "## Artifacts",
        *[f"- `{value}`" for value in paths.values()],
    ]).rstrip() + "\n"


def write_improvement_artifacts(root: Path, *, force: bool = False) -> Optional[Dict[str, Any]]:
    ctx = current_context(root)
    if not triggered(root, ctx, force=force):
        return None
    slug = stable_slug(ctx)
    base = out_dir(root)
    proposal = base / "proposals" / f"{slug}.md"
    draft = base / "drafts" / f"{slug}.md"
    review = base / "review-packets" / f"{slug}.json"
    review_md = base / "review-requests" / f"{slug}.md"
    paths = {
        "proposal": str(proposal.relative_to(root)),
        "draft": str(draft.relative_to(root)),
        "review_packet": str(review.relative_to(root)),
        "review_request": str(review_md.relative_to(root)),
    }
    packet = {
        "schema": proto(root).get("schema") or "noesis.suite.improvement_packet.v1",
        "generated_utc": ctx["generated_utc"],
        "cycle": ctx["cycle"],
        "stage": ctx["stage"],
        "selected_action_id": ctx["selected_action_id"],
        "assigned_task_id": ctx["assigned_task_id"],
        "operator_response_kind": ctx["operator_response_kind"],
        "safety_policy": load_rules(root).get("safety_policy") or {},
        "inputs": {k: str(v.relative_to(root)) for k, v in inputs(root).items() if v.exists()},
        "outputs": paths,
        "summary": {
            "mode": "artifact_only_improved_version_draft",
            "requires_review": True,
            "source_files_modified": False,
        },
    }
    write_text(proposal, render_proposal(root, ctx, paths))
    write_text(draft, render_improved_version(root, ctx))
    write_json(review, packet)
    write_text(review_md, render_review_request(root, ctx, paths))

    write_text(out_path(root, "current_markdown"), read_text(proposal))
    write_text(out_path(root, "current_draft_markdown"), read_text(draft))
    write_json(out_path(root, "current_review_json"), packet)
    write_text(out_path(root, "review_request_markdown"), read_text(review_md))

    event = {
        "schema": "noesis.suite.improvement_writer_event.v1",
        "generated_utc": utc_now(),
        "cycle": ctx["cycle"],
        "stage": ctx["stage"],
        "selected_action_id": ctx["selected_action_id"],
        "assigned_task_id": ctx["assigned_task_id"],
        "outputs": paths,
        "status": "written",
    }
    append_jsonl(journal_path(root), event)
    state = load_state(root)
    state["last_written_key"] = f"{ctx.get('cycle')}::{ctx.get('selected_action_id')}"
    state["last_packet"] = event
    save_state(root, state)
    return packet


def maybe_write_improvement_artifacts(root: Path, *, force: bool = False) -> Optional[Dict[str, Any]]:
    return write_improvement_artifacts(root, force=force)


def status(root: Path) -> Dict[str, Any]:
    return {
        "schema": "noesis.suite.improvement_writer_status.v1",
        "generated_utc": utc_now(),
        "directory": str(out_dir(root)),
        "state": load_state(root),
        "current_review_packet": str(out_path(root, "current_review_json")),
        "current_improvement": str(out_path(root, "current_markdown")),
        "current_improved_version": str(out_path(root, "current_draft_markdown")),
        "review_request": str(out_path(root, "review_request_markdown")),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Noesis improvement artifact writer.")
    parser.add_argument("--root", default=".", help="Suite root. Defaults to current directory.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    write = sub.add_parser("write-from-state")
    write.add_argument("--force", action="store_true")
    sub.add_parser("status")
    sub.add_parser("read-current")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if args.cmd == "write-from-state":
        packet = write_improvement_artifacts(root, force=bool(args.force))
        print(json.dumps(packet or {"ok": True, "written": False, "status": status(root)}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "status":
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "read-current":
        print(read_text(out_path(root, "current_markdown")))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
