from __future__ import annotations

from typing import Any, Dict, List

from . import bridge_restart, dataset, memory, repo, status, workflow
from .auth import forget_key, openai_env, openai_status
from .contracts import BridgeContext, ToolSpec
from .suite import run_takesome, suite_command


def schema(props: Dict[str, Any] | None = None, required: List[str] | None = None) -> Dict[str, Any]:
    return {"type": "object", "properties": props or {}, "required": required or [], "additionalProperties": False}


def build_tools(ctx: BridgeContext) -> Dict[str, ToolSpec]:
    def bind(fn):
        return lambda args: fn(ctx, args)

    specs = {
        "northstar.status": ("Return AI bridge, Suite and repository status without mutating the workspace.", schema(), status.status),
        "northstar.operator_snapshot": ("Return combined status/logs/dataset/operator-memory snapshot.", schema({"logs_limit": {"type": "integer"}, "dataset_limit": {"type": "integer"}}), status.operator_snapshot),
        "northstar.operator_note_append": ("Append an operator note to .takesome/ai-bridge/notes and current-flow.md.", schema({"title": {"type": "string"}, "note": {"type": "string"}, "content": {"type": "string"}, "phase": {"type": "string"}, "task_id": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}), memory.note_append),
        "northstar.operator_note_read": ("Read recent operator notes and current-flow metadata.", schema({"limit": {"type": "integer"}, "max_bytes": {"type": "integer"}, "include_current_flow": {"type": "boolean"}}), memory.note_read),
        "northstar.operator_state_get": ("Read JSON operator state from .takesome/ai-bridge/state.", schema({"namespace": {"type": "string"}, "key": {"type": "string"}}), memory.state_get),
        "northstar.operator_state_set": ("Write JSON operator state. Requires write mode.", schema({"namespace": {"type": "string"}, "key": {"type": "string"}, "value": {}}, ["key", "value"]), memory.state_set),
        "northstar.operator_cache_get": ("Read operator cache entry from .takesome/ai-bridge/cache.", schema({"namespace": {"type": "string"}, "key": {"type": "string"}}, ["key"]), memory.cache_get),
        "northstar.operator_cache_set": ("Write operator cache entry. Requires write mode.", schema({"namespace": {"type": "string"}, "key": {"type": "string"}, "value": {}}, ["key", "value"]), memory.cache_set),
        "northstar.operator_scratch_read": ("Read a scratch markdown draft.", schema({"name": {"type": "string"}, "max_bytes": {"type": "integer"}}, ["name"]), memory.scratch_read),
        "northstar.operator_scratch_write": ("Write a scratch markdown draft. Requires write mode.", schema({"name": {"type": "string"}, "content": {"type": "string"}}, ["name", "content"]), memory.scratch_write),
        "northstar.operator_task_record": ("Create or refresh a durable task record under .takesome/ai-bridge/tasks. Requires write mode.", schema({"task_id": {"type": "string"}, "title": {"type": "string"}, "task": {"type": "string"}, "intent": {"type": "string"}, "status": {"type": "string"}, "phase": {"type": "string"}, "priority": {"type": "string"}, "source": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "constraints": {}, "requested_output": {}, "state_snapshot": {}, "summary": {"type": "string"}}), memory.task_record),
        "northstar.operator_task_update": ("Append a structured event/state delta to a task record. Requires write mode.", schema({"task_id": {"type": "string"}, "title": {"type": "string"}, "status": {"type": "string"}, "phase": {"type": "string"}, "event_type": {"type": "string"}, "summary": {"type": "string"}, "diagnostics": {}, "next_actions": {}, "state_delta": {}, "engine_state_delta": {}, "artifacts": {}, "knowledge_links": {}}), memory.task_update),
        "northstar.operator_task_snapshot": ("Read current task, recent tasks and project knowledge memory.", schema({"limit": {"type": "integer"}, "knowledge_limit": {"type": "integer"}, "include_events": {"type": "boolean"}}), memory.task_snapshot),
        "northstar.operator_knowledge_update": ("Record a durable project knowledge item linked to tasks/artifacts. Requires write mode.", schema({"knowledge_id": {"type": "string"}, "type": {"type": "string"}, "entry_type": {"type": "string"}, "subject": {"type": "string"}, "title": {"type": "string"}, "summary": {"type": "string"}, "content": {"type": "string"}, "confidence": {"type": "string"}, "task_id": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "engine_domains": {"type": "array", "items": {"type": "string"}}, "artifacts": {}, "evidence": {}, "next_actions": {}}), memory.knowledge_update),
        "northstar.operator_knowledge_read": ("Read recent project knowledge items from .takesome/ai-bridge/knowledge.", schema({"limit": {"type": "integer"}}), memory.knowledge_read),
        "northstar.operator_current_state": ("Collect compact current North Star/Suite/dataSet/operator state without mutating memory.", schema({"artifact_limit": {"type": "integer"}}), memory.current_state),
        "northstar.operator_memory_maintain": ("Prune old generated operator memory and refresh current-state knowledge. Requires write mode unless dry_run + refresh_current=false.", schema({"dry_run": {"type": "boolean"}, "refresh_current": {"type": "boolean"}, "max_tasks": {"type": "integer"}, "max_knowledge": {"type": "integer"}, "max_notes": {"type": "integer"}, "max_cache_items_per_namespace": {"type": "integer"}, "max_scratch_items": {"type": "integer"}, "artifact_limit": {"type": "integer"}}), memory.memory_maintain),
        "northstar.read_text": ("Read a whitelisted text file or list a whitelisted directory.", schema({"path": {"type": "string"}, "max_bytes": {"type": "integer"}}, ["path"]), repo.read_text),
        "northstar.read_log": ("Read a recent log by repository-relative path.", schema({"path": {"type": "string"}, "max_bytes": {"type": "integer"}}, ["path"]), repo.read_text),
        "northstar.search_text": ("Search whitelisted repository text roots.", schema({"query": {"type": "string"}, "roots": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer"}, "regex": {"type": "boolean"}, "case_sensitive": {"type": "boolean"}}, ["query"]), repo.search_text),
        "northstar.list_tree": ("List a shallow repository tree for whitelisted roots.", schema({"path": {"type": "string"}, "max_depth": {"type": "integer"}, "limit": {"type": "integer"}}), repo.list_tree),
        "northstar.write_text": ("Write a whitelisted text file with backup. Requires write mode.", schema({"path": {"type": "string"}, "content": {"type": "string"}, "create_parents": {"type": "boolean"}}, ["path", "content"]), repo.write_text),
        "northstar.patch_preview": ("Inspect a changed-files patch zip without applying it.", schema({"patch_path": {"type": "string"}}, ["patch_path"]), repo.patch_preview),
        "northstar.apply_changed_files_zip": ("Apply a changed-files patch zip with backups. Requires write mode.", schema({"patch_path": {"type": "string"}}, ["patch_path"]), repo.apply_changed_files_zip),
        "northstar.latest_incident": ("Read latest Suite incident handoff files.", schema({"max_bytes": {"type": "integer"}}), repo.latest_incident),
        "northstar.list_logs": ("List recent build/run/incident logs.", schema({"limit": {"type": "integer"}}), repo.list_logs),
        "northstar.git_status": ("Return git status --short.", schema(), repo.git_status),
        "northstar.bridge_restart": ("Run safe local AI bridge restart helper. Commands: status, stop-origin, wait-down, wait-up.", schema({"command": {"type": "string"}, "host": {"type": "string"}, "port": {"type": "integer"}, "timeout": {"type": "number"}, "wait_sec": {"type": "number"}, "dry_run": {"type": "boolean"}}), bridge_restart.bridge_restart),
        "northstar.bridge_restart_sequence": ("Run safe bounded local-origin restart sequence: status -> stop-origin -> wait-down. Requires write mode.", schema({"host": {"type": "string"}, "port": {"type": "integer"}, "timeout": {"type": "number"}, "wait_sec": {"type": "number"}, "dry_run": {"type": "boolean"}}), bridge_restart.bridge_restart_sequence),
        "northstar.suite_actions": ("Ask SuiteRegistry for available Suite actions.", schema({"timeout_sec": {"type": "integer"}}), lambda c, a: run_takesome(c, ["suite", "--list-actions", "--json"], max(5, min(int(a.get("timeout_sec", 60)), 300)))),
        "northstar.suite_command": ("Run an allow-listed Suite command.", schema({"command_id": {"type": "string"}, "timeout_sec": {"type": "integer"}, "requires_openai_key": {"type": "boolean"}, "allow_unlisted": {"type": "boolean"}}, ["command_id"]), suite_command),
        "northstar.dataset_status": ("Return dataSetDirectory status and newest archives/directories.", schema(), dataset.status),
        "northstar.dataset_list_archives": ("List zip archives under dataSetDirectory.", schema({"limit": {"type": "integer"}, "recursive": {"type": "boolean"}}), dataset.list_archives),
        "northstar.dataset_scan_archive": ("Scan one dataSetDirectory zip archive.", schema({"archive_path": {"type": "string"}, "limit": {"type": "integer"}, "include_samples": {"type": "boolean"}}, ["archive_path"]), dataset.scan_archive),
        "northstar.dataset_search_archives": ("Search archive names and whitelisted text members.", schema({"query": {"type": "string"}, "limit": {"type": "integer"}, "search_content": {"type": "boolean"}, "case_sensitive": {"type": "boolean"}}, ["query"]), dataset.search_archives),
        "northstar.dataset_read_archive_member": ("Read a whitelisted text member from a zip.", schema({"archive_path": {"type": "string"}, "member": {"type": "string"}, "max_bytes": {"type": "integer"}}, ["archive_path", "member"]), dataset.read_archive_member),
        "northstar.dataset_materialize_archives": ("Extract dataset archives into .takesome/dataSet/extracted, then delete archive ingest objects by default. Requires write mode.", schema({"limit": {"type": "integer"}, "force": {"type": "boolean"}, "keep_archives": {"type": "boolean"}, "delete_archives": {"type": "boolean"}}), dataset.materialize_archives),
        "northstar.dataset_purge_archives": ("Delete dataSet .zip ingest objects that already have materialized extracted manifests. Requires write mode.", schema({"limit": {"type": "integer"}, "dry_run": {"type": "boolean"}}), dataset.purge_materialized_archives),
        "northstar.dataset_browse_directories": ("Browse materialized dataSet directories with logic scores, key files and extension stats.", schema({"path": {"type": "string"}, "depth": {"type": "integer"}, "limit": {"type": "integer"}, "max_files": {"type": "integer"}, "profile": {"type": "boolean"}}), dataset.browse_directories),
        "northstar.dataset_profile_directory": ("Profile one materialized dataSet directory as a reference corpus candidate.", schema({"path": {"type": "string"}, "max_files": {"type": "integer"}, "sample_limit": {"type": "integer"}}), dataset.profile_directory),
        "northstar.dataset_search_logic": ("Search materialized dataSet directories with logic-aware ranking.", schema({"query": {"type": "string"}, "path": {"type": "string"}, "limit": {"type": "integer"}, "case_sensitive": {"type": "boolean"}}), dataset.search_logic),
        "northstar.dataset_search_directories": ("Search materialized dataset directories first.", schema({"query": {"type": "string"}, "limit": {"type": "integer"}, "case_sensitive": {"type": "boolean"}}, ["query"]), dataset.search_directories),
        "northstar.dataset_rebuild_index": ("Rebuild directory-first dataset index. Requires write mode.", schema(), dataset.rebuild_index),
        "northstar.openai_key_status": ("Return OpenAI API key availability without revealing it.", schema(), lambda c, a: openai_status(c)),
        "northstar.openai_key_require": ("Ensure an OpenAI API key exists.", schema(), lambda c, a: {"ok": True, **openai_status(c)} if openai_env(c, True) else {}),
        "northstar.openai_key_forget": ("Delete cached OpenAI API key. Requires write mode or interactive.", schema(), lambda c, a: forget_key(c)),
        "northstar.workflow_spiral": ("Run a bounded synchronous observe/analyze/verify/build spiral workflow with persistent notes/state/cache.", schema({"task": {"type": "string"}, "task_id": {"type": "string"}, "phases": {"type": "array", "items": {"type": "string"}}, "include_build": {"type": "boolean"}, "include_runtime": {"type": "boolean"}, "materialize_dataset": {"type": "boolean"}, "browse_dataset": {"type": "boolean"}, "dataset_path": {"type": "string"}, "dataset_query": {"type": "string"}, "query": {"type": "string"}, "dataset_limit": {"type": "integer"}, "dataset_browser_depth": {"type": "integer"}, "dataset_browser_limit": {"type": "integer"}, "dataset_browser_max_files": {"type": "integer"}, "dataset_profile_max_files": {"type": "integer"}, "dataset_profile_sample_limit": {"type": "integer"}, "dataset_search_limit": {"type": "integer"}, "logs_limit": {"type": "integer"}, "max_steps": {"type": "integer"}, "timeout_sec": {"type": "integer"}, "stop_on_failure": {"type": "boolean"}, "allow_unlisted": {"type": "boolean"}, "force_dataset": {"type": "boolean"}, "case_sensitive": {"type": "boolean"}}), workflow.workflow_spiral),
    }
    return {name: ToolSpec(name, desc, spec_schema, bind(fn)) for name, (desc, spec_schema, fn) in specs.items()}
