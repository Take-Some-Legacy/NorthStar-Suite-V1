# Noesis Improvement Writer Rules

This file is the declarative source of truth for how Noesis materializes
self-improvement output artifacts.

Python code must execute this declarative rule set and must not hard-code
semantic task ids, stages, improvement vocabulary, output categories or approval policy.

```json
{
  "schema": "noesis.suite.improvement_writer_rules.v1",
  "protocol": {
    "schema": "noesis.suite.improvement_packet.v1",
    "directory": ".takesome/intelligence/improvements",
    "state": "improvement-writer-state.json",
    "journal": "improvement-writer-events.jsonl",
    "current_markdown": "current-improvement.md",
    "current_draft_markdown": "current-improved-version.md",
    "current_review_json": "current-review-packet.json",
    "review_request_markdown": "assistant-review-request.md"
  },
  "trigger_policy": {
    "stage_any": ["self_improvement_requested"],
    "action_id_any": ["noesis.self_improvement.audit"],
    "write_once_per_cycle_action": true,
    "allow_force": true
  },
  "safety_policy": {
    "mode": "artifact_only",
    "auto_apply_source_changes": false,
    "auto_commit": false,
    "auto_push": false,
    "requires_approval_for_source_write": true,
    "requires_approval_for_destructive": true,
    "allowed_output_root": ".takesome/intelligence/improvements",
    "forbidden_roots": [
      ".takesome/authority",
      ".takesome/ai-bridge/state",
      ".takesome/ai-bridge/tmp",
      ".takesome/ai-bridge/patch-backups"
    ]
  },
  "inputs": {
    "decision": ".takesome/intelligence/workloop-decision.json",
    "assigned_task": ".takesome/intelligence/assigned-task.json",
    "task_scan": ".takesome/intelligence/task-scan.json",
    "workloop_trace": ".takesome/intelligence/workloop-trace.md",
    "operator_response": ".takesome/intelligence/operator-response.md",
    "operator_rules": "tools/scripts/takesome/rules/operator-response-rules.md",
    "chat_rules": "tools/scripts/takesome/rules/noesis-chat-protocol.md"
  },
  "packet": {
    "title": "Noesis Self-Improvement Packet",
    "draft_title": "Noesis Improved Version Draft",
    "review_title": "Noesis Review Request for Assistant",
    "default_focus": [
      "remove duplicated decision paths",
      "keep rules in Markdown rule files",
      "keep Python as generic protocol executor",
      "improve config/binding/registry/workloop/chat cohesion",
      "make status and trace machine-readable",
      "do not auto-apply source changes without approval"
    ],
    "candidate_sections": [
      "Observed state",
      "Detected risks",
      "Proposed improved version",
      "Draft patch request",
      "Validation plan",
      "Approval gate"
    ],
    "review_question": "Please review this generated improvement packet and decide which safe patch should be implemented next."
  }
}
```
