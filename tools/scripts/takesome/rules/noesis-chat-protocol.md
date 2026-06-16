# Noesis Chat Protocol Rules

This file is the source of truth for the Noesis file-based assistant chat protocol.
Python code must execute this protocol and must not hard-code semantic routing policy.

```json noesis-chat-protocol.v1
{
  "schema": "noesis.suite.chat_protocol_rules.v1",
  "chat": {
    "directory": ".takesome/intelligence/chat",
    "journal": "noesis-chat.jsonl",
    "state": "chat-state.json",
    "latest_noesis_to_assistant": "noesis-to-assistant.md",
    "latest_assistant_to_noesis": "assistant-to-noesis.md",
    "unread_for_assistant": "unread-for-assistant.json",
    "unread_for_noesis": "unread-for-noesis.json"
  },
  "emit_policy": {
    "default_kind": "status_request",
    "default_to": "assistant",
    "default_from": "noesis",
    "requires_response": true,
    "emit_when_stage_any": ["self_improvement_requested", "operator_note_available", "assignment_pending", "blocked_runtime_state_in_worktree"],
    "dedupe_same_cycle": true,
    "dedupe_same_stage_and_task": false
  },
  "message_templates": {
    "noesis_cycle_message": {
      "title": "Noesis -> Assistant",
      "text_template": "I am in stage `{stage}` with task `{task_id}`. Decision status is `{decision_status}`. Checks failed: `{checks_failed}`. Please review my current trace and tell me the next safe step.",
      "attachments": [
        ".takesome/intelligence/workloop-decision.json",
        ".takesome/intelligence/workloop-trace.md",
        ".takesome/intelligence/assigned-task.md",
        ".takesome/intelligence/task-scan.json"
      ]
    }
  },
  "reply_policy": {
    "mirror_to_operator_response": true,
    "operator_response_path": ".takesome/intelligence/operator-response.md",
    "default_reply_kind": "assistant_reply"
  }
}
```
