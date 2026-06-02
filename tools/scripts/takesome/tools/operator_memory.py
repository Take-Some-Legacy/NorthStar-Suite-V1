from __future__ import annotations

import sys
from pathlib import Path

from ..logs import TeeLog


def operator_memory_maintenance(repo_root: Path, *, dry_run: bool = False, log: TeeLog | None = None) -> int:
    """Run generated operator-memory hygiene and current-state refresh.

    This is a Suite/devtools wrapper around northstar_bridge.memory so the
    command is available from `takesome.py tools operator-memory` without adding
    a second memory implementation.
    """

    own_log = log or TeeLog()
    scripts_root = repo_root / "tools" / "scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    try:
        from northstar_bridge.contracts import BridgeContext
        from northstar_bridge.memory import memory_maintain
    except Exception as exc:
        own_log.emit(f"[ERROR] operator memory module unavailable: {exc}")
        return 1

    ctx = BridgeContext(root=repo_root, write_enabled=not dry_run, python_cmd=[sys.executable], interactive=False)
    try:
        result = memory_maintain(ctx, {"dry_run": dry_run, "refresh_current": not dry_run})
    except Exception as exc:
        own_log.emit(f"[ERROR] operator memory maintenance failed: {exc}")
        return 1

    cleanup = result.get("cleanup", {}) if isinstance(result, dict) else {}
    removed = cleanup.get("removed", []) if isinstance(cleanup, dict) else []
    state = result.get("current_state", {}) if isinstance(result, dict) else {}
    memory = state.get("operator_memory", {}) if isinstance(state, dict) else {}
    own_log.emit("[OK] Operator memory hygiene completed")
    own_log.emit(f"[INFO] dry_run={result.get('dry_run')} removed={len(removed)}")
    own_log.emit(
        "[INFO] current memory: "
        f"tasks={memory.get('tasks_total')} knowledge={memory.get('knowledge_total')} "
        f"notes={memory.get('notes_total')} cache_namespaces={memory.get('cache_namespaces')}"
    )
    own_log.emit("[INFO] state keys refreshed: operator.engine_current_state, operator.memory_hygiene_last")
    return 0
