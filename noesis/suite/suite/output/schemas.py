from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


DIAGNOSTIC_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["severity", "check", "message"],
    "properties": {
        "severity": {"enum": ["info", "warn", "error"]},
        "check": {"type": "string"},
        "path": {"type": "string"},
        "message": {"type": "string"},
        "data": {"type": "object"},
    },
    "additionalProperties": True,
}

ARTIFACT_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["kind", "path"],
    "properties": {
        "kind": {"type": "string"},
        "path": {"type": "string"},
        "schema": {"type": ["string", "null"]},
        "description": {"type": "string"},
    },
    "additionalProperties": True,
}

NEXT_ACTION_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["priority", "action_id", "reason"],
    "properties": {
        "priority": {"enum": ["P0", "P1", "P2", "P3", "info"]},
        "action_id": {"type": "string"},
        "reason": {"type": "string"},
        "command": {"type": "string"},
    },
    "additionalProperties": True,
}

MODEL_HINTS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["read_order", "truth_source", "stdout_policy", "status_policy"],
    "properties": {
        "read_order": {"type": "array", "items": {"type": "string"}},
        "truth_source": {"type": "string"},
        "stdout_policy": {"type": "string"},
        "status_policy": {"type": "string"},
    },
    "additionalProperties": True,
}

SUITE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "northstar.suite.output.v1",
    "title": "North Star Suite Output Envelope",
    "type": "object",
    "required": [
        "schema",
        "suite_version",
        "action_id",
        "run_id",
        "status",
        "started_at",
        "finished_at",
        "duration_ms",
        "profile",
        "summary",
        "result_schema",
        "result",
        "diagnostics",
        "artifacts",
        "next_actions",
        "model_hints",
    ],
    "properties": {
        "schema": {"const": "northstar.suite.output.v1"},
        "suite_version": {"type": "string"},
        "action_id": {"type": "string"},
        "run_id": {"type": "string"},
        "status": {"enum": ["ok", "failed", "error", "skipped"]},
        "started_at": {"type": "string"},
        "finished_at": {"type": "string"},
        "duration_ms": {"type": "integer"},
        "profile": {"type": "object"},
        "summary": {
            "type": "object",
            "required": ["title", "severity", "human"],
            "properties": {
                "title": {"type": "string"},
                "severity": {"enum": ["info", "warn", "error"]},
                "human": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "result_schema": {"type": ["string", "null"]},
        "result": {"type": "object"},
        "diagnostics": {"type": "array", "items": DIAGNOSTIC_ITEM_SCHEMA},
        "artifacts": {"type": "array", "items": ARTIFACT_ITEM_SCHEMA},
        "next_actions": {"type": "array", "items": NEXT_ACTION_ITEM_SCHEMA},
        "model_hints": MODEL_HINTS_SCHEMA,
    },
    "additionalProperties": False,
}

PROCESS_RESULT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "northstar.suite.process_result.v1",
    "title": "North Star Suite Process Result",
    "type": "object",
    "required": ["exit_code", "stdout", "stderr", "action", "process_contract"],
    "properties": {
        "exit_code": {"type": "integer"},
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
        "action": {"type": "object"},
        "process_contract": {"type": "string"},
        "declared_output_schema": {"type": ["string", "null"]},
        "exception": {"type": ["object", "null"]},
    },
    "additionalProperties": True,
}

ACTION_LIST_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "northstar.suite.action_list.v1",
    "title": "North Star Suite Action List",
    "type": "object",
    "required": ["actions", "action_count"],
    "properties": {
        "action_count": {"type": "integer"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key", "label", "category", "target_domain", "risk_level", "output_schema", "output_mode"],
                "properties": {
                    "key": {"type": "string"},
                    "label": {"type": "string"},
                    "detail": {"type": "string"},
                    "category": {"type": "string"},
                    "primary_tag": {"type": "string"},
                    "target_domain": {"type": "string"},
                    "risk_level": {"type": "string"},
                    "profile": {"type": "string"},
                    "chips": {"type": "array", "items": {"type": "string"}},
                    "progress_total": {"type": "integer"},
                    "progress_unit": {"type": "string"},
                    "output_schema": {"type": ["string", "null"]},
                    "output_mode": {"type": "string"},
                },
                "additionalProperties": True,
            },
        }
    },
    "additionalProperties": True,
}

DATASET_ENTRY_VALUE_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "northstar.dataset.entry_value.v1",
    "title": "North Star Dataset Entry Value Report",
    "type": "object",
    "required": [
        "schema", "entry_id", "entry_path", "analyzed_at", "architectural_value_score",
        "value_level", "topic_tags", "mapped_engine_domains", "how_it_can_help",
        "recommended_actions", "maturity_questions", "risk_flags", "forbidden_direct_copy_notes", "evidence",
    ],
    "properties": {
        "schema": {"const": "northstar.dataset.entry_value.v1"},
        "entry_id": {"type": "string"},
        "entry_path": {"type": "string"},
        "analyzed_at": {"type": "string"},
        "file_count_sampled": {"type": "integer"},
        "extension_summary": {"type": "object"},
        "architectural_value_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "value_level": {"enum": ["high", "medium", "low", "unknown"]},
        "topic_tags": {"type": "array", "items": {"type": "string"}},
        "mapped_engine_domains": {"type": "array", "items": {"type": "string"}},
        "capability_candidates": {"type": "array", "items": {"type": "string"}},
        "provider_candidates": {"type": "array", "items": {"type": "string"}},
        "conformance_candidates": {"type": "array", "items": {"type": "string"}},
        "how_it_can_help": {"type": "array", "items": {"type": "string"}},
        "recommended_actions": {"type": "array", "items": NEXT_ACTION_ITEM_SCHEMA},
        "maturity_questions": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "forbidden_direct_copy_notes": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "object"}},
    },
    "additionalProperties": True,
}

DATASET_ENTRY_VALUE_INDEX_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "northstar.dataset.entry_value_index.v1",
    "title": "North Star Dataset Entry Value Index",
    "type": "object",
    "required": ["schema", "updated_at", "entry_count", "entries"],
    "properties": {
        "schema": {"const": "northstar.dataset.entry_value_index.v1"},
        "updated_at": {"type": "string"},
        "entry_count": {"type": "integer"},
        "entries": {"type": "array", "items": DATASET_ENTRY_VALUE_SCHEMA},
    },
    "additionalProperties": True,
}

DATASET_ARCHIVE_LIFECYCLE_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "northstar.dataset.archive_lifecycle.v1",
    "title": "North Star Dataset Archive Lifecycle Report",
    "type": "object",
    "required": ["schema", "updated_at", "policy", "records"],
    "properties": {
        "schema": {"const": "northstar.dataset.archive_lifecycle.v1"},
        "updated_at": {"type": "string"},
        "policy": {"type": "object"},
        "archive_count_seen": {"type": "integer"},
        "archive_count_deleted": {"type": "integer"},
        "archive_count_kept": {"type": "integer"},
        "records": {"type": "array"},
    },
    "additionalProperties": True,
}

BUILTIN_SCHEMAS = {
    "suite.output.v1.json": SUITE_OUTPUT_SCHEMA,
    "suite.process_result.v1.json": PROCESS_RESULT_SCHEMA,
    "suite.action_list.v1.json": ACTION_LIST_SCHEMA,
    "dataset.entry_value.v1.json": DATASET_ENTRY_VALUE_SCHEMA,
    "dataset.entry_value_index.v1.json": DATASET_ENTRY_VALUE_INDEX_SCHEMA,
    "dataset.archive_lifecycle.v1.json": DATASET_ARCHIVE_LIFECYCLE_SCHEMA,
}


def ensure_builtin_output_schemas(root: Path) -> None:
    out = root / "config" / "noesis" / "output_schemas"
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in BUILTIN_SCHEMAS.items():
        path = out / name
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if not path.exists() or path.read_text(encoding="utf-8", errors="replace") != text:
            path.write_text(text, encoding="utf-8")


def _diag(severity: str, check: str, path: str, message: str) -> Dict[str, Any]:
    return {"severity": severity, "check": check, "path": path, "message": message}


def validate_suite_output_envelope(envelope: Dict[str, Any]) -> list[Dict[str, Any]]:
    diagnostics: list[Dict[str, Any]] = []
    required = SUITE_OUTPUT_SCHEMA["required"]
    for key in required:
        if key not in envelope:
            diagnostics.append(_diag("error", "suite.output.schema.required", key, f"SuiteOutputEnvelope is missing required field {key}"))
    if envelope.get("schema") != "northstar.suite.output.v1":
        diagnostics.append(_diag("error", "suite.output.schema.id", "schema", "SuiteOutputEnvelope has unexpected schema id"))
    if envelope.get("status") not in {"ok", "failed", "error", "skipped"}:
        diagnostics.append(_diag("error", "suite.output.status", "status", "SuiteOutputEnvelope has invalid status"))
    summary = envelope.get("summary")
    if not isinstance(summary, dict) or not {"title", "severity", "human"}.issubset(summary):
        diagnostics.append(_diag("error", "suite.output.summary", "summary", "summary must expose title/severity/human"))
    for idx, item in enumerate(envelope.get("diagnostics") or []):
        if not isinstance(item, dict):
            diagnostics.append(_diag("error", "suite.output.diagnostics.item", f"diagnostics[{idx}]", "diagnostic item must be an object"))
            continue
        for key in ("severity", "check", "message"):
            if key not in item:
                diagnostics.append(_diag("error", "suite.output.diagnostics.required", f"diagnostics[{idx}].{key}", "diagnostic item is missing a required field"))
    for idx, item in enumerate(envelope.get("artifacts") or []):
        if not isinstance(item, dict) or not item.get("kind") or not item.get("path"):
            diagnostics.append(_diag("error", "suite.output.artifacts.required", f"artifacts[{idx}]", "artifact must expose kind and path"))
    return diagnostics
