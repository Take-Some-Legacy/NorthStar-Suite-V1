# Noesis Chat Protocol Rules

This file dictates chat behavior and message content. Storage paths are configured in `.takesome/config/noesis-roots.v1.json`.
Python must execute the generic protocol and must not hard-code semantic routing policy.

```json noesis-chat-protocol.v1
{
  "schema": "noesis.suite.chat_protocol_rules.v1",
  "emit_policy": {
    "default_kind": "status_request",
    "default_to": "assistant",
    "default_from": "noesis",
    "requires_response": true,
    "emit_when_stage_any": [
      "self_improvement_requested",
      "operator_note_available",
      "assignment_pending",
      "blocked_runtime_state_in_worktree",
      "operator_task_requested"
    ],
    "dedupe_same_cycle": true,
    "dedupe_same_stage_and_task": false
  },
  "message_templates": {
    "noesis_cycle_message": {
      "title": "Noesis -> Assistant",
      "text_template": "I am in stage `{stage}` with task `{task_id}`. Decision status is `{decision_status}`. Checks failed: `{checks_failed}`. Please review my current trace and tell me the next safe step.",
      "attachment_file_keys": [
        "workloop_decision",
        "workloop_trace_summary",
        "assigned_task_md",
        "task_scan",
        "operator_response",
        "task_artifact_current_review_request",
        "task_artifact_current_review_packet",
        "source_apply_state",
        "source_apply_executor_state",
        "config_override_state"
      ]
    }
  },
  "reply_policy": {
    "mirror_to_operator_response": true,
    "operator_response_file_key": "operator_response",
    "default_reply_kind": "assistant_reply"
  }
}
```
