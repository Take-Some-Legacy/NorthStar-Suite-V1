# Noesis Task Artifact Writer Rules

This file dictates the currently assigned task behavior for the generic task artifact writer.
Storage roots and file destinations are configured in `.takesome/config/noesis-roots.v1.json`.
The assigned task may be self-improvement, game development, website work, UI work, research, or any other task. Python must not contain a task-type registry.

```json noesis-task-artifact-writer.v1
{
  "schema": "noesis.suite.task_artifact_writer_rules.v1",
  "artifact_mode": "artifact_only",
  "activation": [
    {"field": "stage", "op": "in", "values": ["self_improvement_requested"]},
    {"field": "assigned_task_id", "op": "in", "values": ["noesis.self_improvement.audit"]}
  ],
  "safety": {
    "auto_apply_source_changes": false,
    "auto_commit": false,
    "auto_push": false,
    "base_config_write_requires_explicit_approval": true
  },
  "focus": [
    "Keep task meaning in markdown rules or operator instructions, not in Python.",
    "Keep root and storage keys in `.takesome/config/noesis-roots.v1.json`.",
    "Keep Python as a generic resolver/executor.",
    "Write artifacts for the assigned task without assuming the task name or domain."
  ],
  "attachment_file_keys": [
    "workloop_decision",
    "workloop_trace_summary",
    "assigned_task_md",
    "task_scan"
  ],
  "templates": {
    "proposal_title": "Noesis assigned task proposal",
    "proposal_body": "Noesis is in stage `{stage}` and assigned `{assigned_task_id}`. The current task rules request an artifact-only proposal. Continue by reviewing the configured roots, current trace, assigned task and task scan, then produce a safe draft for operator review.",
    "draft_title": "Noesis assigned task draft",
    "draft_body": "Draft for assigned task `{assigned_task_id}`: keep task semantics outside Python; use configured root/file keys; produce reviewable artifacts; do not apply source/config writes without explicit approval.",
    "review_request_title": "Noesis assigned task review request",
    "review_request_body": "Please review the generated task artifact packet for `{assigned_task_id}` and decide whether to continue artifact-only work or approve a concrete source/config patch."
  }
}
```
