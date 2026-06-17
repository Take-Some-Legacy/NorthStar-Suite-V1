from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _audit(kind: str, path: Path, *, cycle: int | str = '', task: str = '', action: str = '') -> dict[str, Any]:
    path = Path(path)
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    digest = _sha256(path) if exists and path.is_file() else ''
    event = {
        'kind': kind,
        'path': str(path),
        'utc': utc_now(),
        'cycle': str(cycle),
        'task': str(task),
        'action': str(action),
        'exists': bool(exists),
        'bytes': int(size),
        'sha256': digest,
    }
    print(
        f"VERIFY kind={kind} path={path} utc={event['utc']} cycle={event['cycle']} "
        f"task={event['task']} action={event['action']} exists={str(exists).lower()} "
        f"bytes={size} sha256={digest}",
        flush=True,
    )
    return event


def _atomic_write_text(path: Path, text: str, *, kind: str, cycle: int | str, task: str, action: str) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)
    size = path.stat().st_size
    digest = _sha256(path)
    now = utc_now()
    print(
        f"WRITE kind={kind} path={path} utc={now} cycle={cycle} task={task} "
        f"action={action} bytes={size} sha256={digest}",
        flush=True,
    )
    return _audit(kind, path, cycle=cycle, task=task, action=action)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return {}


def _load_rules(root: Path) -> dict[str, Any]:
    rules_path = root / 'tools' / 'scripts' / 'takesome' / 'rules' / 'noesis-task-completion.md'
    text = rules_path.read_text(encoding='utf-8') if rules_path.exists() else ''
    m = re_search_json_block(text)
    if not m:
        return {'required_files': [], 'done_markers': ['TASK_DONE:', 'DONE:'], 'stop_when_done': True}
    return m


def re_search_json_block(text: str) -> dict[str, Any] | None:
    import re
    m = re.search(r'```json\s*(\{.*?\})\s*```', text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _contains_done_marker(root: Path, markers: list[str]) -> bool:
    op = root / '.takesome' / 'intelligence' / 'operator-response.md'
    text = op.read_text(encoding='utf-8', errors='replace') if op.exists() else ''
    return any(marker and marker in text for marker in markers)


def _required_files_exist(root: Path, rels: list[str]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for rel in rels:
        if not (root / rel).exists():
            missing.append(rel)
    return (not missing, missing)


def update_task_completion_state(root: Path, *, cycle: int | str, task: str, status: str = '') -> dict[str, Any]:
    root = Path(root)
    rules = _load_rules(root)
    required_files = [str(x) for x in rules.get('required_files', [])]
    done_markers = [str(x) for x in rules.get('done_markers', ['TASK_DONE:', 'DONE:'])]
    files_ok, missing = _required_files_exist(root, required_files)
    marker_done = _contains_done_marker(root, done_markers)
    done = bool(marker_done or (required_files and files_ok and str(status).lower() in {'done', 'ok', 'completed'}))
    reason = 'operator_done_marker' if marker_done else ('required_files_present_and_status_done' if done else 'criteria_not_met')
    state = {
        'schema': 'noesis.suite.task_completion_state.v1',
        'updated_utc': utc_now(),
        'cycle': cycle,
        'task': task,
        'done': done,
        'reason': reason,
        'status': status,
        'required_files': required_files,
        'missing_required_files': missing,
        'done_markers': done_markers,
        'proof_chain': ['INTENT', 'ACTION', 'WRITE', 'VERIFY', 'TRACE'],
    }
    state_path = root / '.takesome' / 'intelligence' / 'task-completion-state.json'
    md_path = root / '.takesome' / 'intelligence' / 'task-completion-state.md'
    _atomic_write_text(state_path, json.dumps(state, ensure_ascii=False, indent=2), kind='task-completion-state', cycle=cycle, task=task, action='write-task-completion-state')
    md = '\n'.join([
        '# NOESIS Task Completion State',
        '',
        f"updated_utc: {state['updated_utc']}",
        f"cycle: {cycle}",
        f"task: {task}",
        f"done: {str(done).lower()}",
        f"reason: {reason}",
        '',
        'Proof chain: INTENT -> ACTION -> WRITE -> VERIFY -> TRACE',
    ]) + '\n'
    _atomic_write_text(md_path, md, kind='task-completion-summary', cycle=cycle, task=task, action='write-task-completion-summary')
    print(f"TRACE kind=task-completion utc={utc_now()} cycle={cycle} task={task} done={str(done).lower()} reason={reason}", flush=True)
    return state


def should_stop_for_completion(root: Path) -> bool:
    state = _load_json(Path(root) / '.takesome' / 'intelligence' / 'task-completion-state.json')
    if not state.get('done'):
        return False
    rules = _load_rules(Path(root))
    return bool(rules.get('stop_when_done', True))
