# Noesis Source Apply Gate

This file defines task behavior for source-apply approval. It does not define root keys, task types, or storage paths.

```json
{
  "schema": "noesis.suite.source_apply_gate_rules.v1",
  "policy": {
    "source_apply_requires_explicit_approval": true,
    "direct_source_write_without_approval": false,
    "auto_commit": false,
    "auto_push": false,
    "prepare_request_only_by_default": true,
    "validation_required_after_approval": true,
    "commit_requires_separate_request": true
  },
  "gate_chain": [
    "task_artifact",
    "review_packet",
    "approval_required",
    "patch_apply_after_approval",
    "validate",
    "commit_request"
  ]
}
```
