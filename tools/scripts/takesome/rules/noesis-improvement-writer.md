# Noesis Improvement Writer Rules

This file is the source of truth for the Noesis improvement artifact writer.
Python executes this declarative rule set and must not hard-code semantic stages, action ids, focus areas or write policy.

```json noesis-improvement-writer.v1
{
  "schema": "noesis.suite.improvement_writer_rules.v1",
  "artifact_mode": "artifact_only",
  "safety": {
    "auto_apply_source_changes": false,
    "auto_commit": false,
    "auto_push": false,
    "source_write_requires_explicit_approval": true,
    "destructive_requires_explicit_approval": true
  },
  "activation": [
    {"field": "stage", "op": "in", "values": ["self_improvement_requested"]},
    {"field": "assigned_task_id", "op": "in", "values": ["noesis.self_improvement.audit"]}
  ],
  "paths": {
    "root": ".takesome/intelligence/improvements",
    "proposal_current": "current-improvement.md",
    "draft_current": "current-improved-version.md",
    "review_current": "current-review-packet.json",
    "request_current": "assistant-review-request.md",
    "state": "improvement-writer-state.json",
    "events": "improvement-writer-events.jsonl",
    "proposals_dir": "proposals",
    "drafts_dir": "drafts",
    "review_packets_dir": "review-packets",
    "review_requests_dir": "review-requests"
  },
  "templates": {
    "proposal_title": "Noesis self-improvement proposal",
    "proposal_body": "Noesis is in stage `{stage}` and assigned `{assigned_task_id}`. The next safe improvement is to continue read-only architecture audit, identify duplicated logic, legacy fallbacks and weak coupling, then request approval before source changes.",
    "draft_title": "Improved Version Draft",
    "draft_body": "Draft improved version: keep MD rules as source of truth; keep Python as generic executor; emit trace/chat/improvement artifacts from one final decision path; do not auto-apply source writes without approval.",
    "review_request_title": "Assistant Review Request",
    "review_request_body": "Please review the generated proposal and draft. Approve a concrete source patch only after checking rule-source compliance, trace consistency and git hygiene."
  },
  "focus": [
    "duplicate config/rule loaders",
    "trace and decision consistency",
    "missing Noesis descriptors",
    "legacy fallback cleanup",
    "chat protocol integration",
    "improvement artifact review gate"
  ],
  "attachments": [
    ".takesome/intelligence/workloop-decision.json",
    ".takesome/intelligence/workloop-trace.md",
    ".takesome/intelligence/assigned-task.md",
    ".takesome/intelligence/task-scan.json"
  ]
}
```
