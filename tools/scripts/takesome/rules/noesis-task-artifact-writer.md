# Noesis Task Artifact Writer Rules

This file dictates the currently assigned task behavior for the generic task artifact writer.
Storage roots and file destinations are configured in `.takesome/config/noesis-roots.v1.json`.
The assigned task may be self-improvement, game development, website work, UI work, research, or any other task. Python must not contain a task-type registry.

```json noesis-task-artifact-writer.v1
{
  "schema": "noesis.suite.task_artifact_writer_rules.v1",
  "artifact_mode": "task_artifact_only",
  "activation": [
    {
      "field": "assigned_task_id",
      "op": "nonempty"
    },
    {
      "field": "decision_status",
      "op": "in",
      "values": [
        "assigned",
        "needs_approval"
      ]
    }
  ],
  "safety": {
    "auto_apply_source_changes": false,
    "auto_commit": false,
    "auto_push": false,
    "base_config_write_requires_explicit_approval": true,
    "task_type_registry_required": false,
    "root_keys_from_config": true
  },
  "focus": [
    "Create artifacts for the current assigned task, regardless of task domain.",
    "Do not use a task-type registry.",
    "Read root/file locations from `.takesome/config/noesis-roots.v1.json`.",
    "Use chat/task artifacts/source apply gates/capability state as runtime evidence.",
    "If source changes are needed, produce a reviewable patch artifact and route it through the approval executor."
  ],
  "attachment_file_keys": [
    "workloop_decision",
    "workloop_trace_summary",
    "assigned_task_md",
    "task_scan",
    "config_override_state",
    "source_apply_state",
    "source_apply_executor_state",
    "source_apply_validation_current",
    "source_apply_commit_request_current",
    "operator_response",
    "chat_state"
  ],
  "templates": {
    "proposal_title": "Noesis generic assigned task proposal",
    "proposal_body": "Noesis accepted assigned task `{assigned_task_id}` in stage `{stage}`. Review root context, capability state, current operator directive and attached runtime files. Produce the safest next executable step without assuming a task type.",
    "draft_title": "Noesis generic assigned task draft",
    "draft_body": "Draft for `{assigned_task_id}`: use configured roots/files; inspect runtime evidence; report risks; prepare source/config changes only as reviewable artifacts unless capability and approval executor permit execution.",
    "review_request_title": "Noesis generic assigned task review request",
    "review_request_body": "Please review the task artifact packet for `{assigned_task_id}`. Confirm whether Noesis should continue artifact-only analysis, enable/keep execution capabilities, or prepare an approved patch execution."
  }
}
```
