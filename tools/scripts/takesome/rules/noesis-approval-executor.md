# Noesis Approval Executor

This file defines task behavior for approval-gated patch execution. It does not define root keys or storage paths.

The executor is allowed to apply source changes only after an explicit approval record exists and the source-apply capability is enabled in effective config. Commit and push remain separate request gates.

```json
{
  "schema": "noesis.suite.approval_executor_rules.v1",
  "policy": {
    "requires_source_apply_capability_enabled": true,
    "requires_explicit_approval_record": true,
    "approval_status_required": "approved",
    "git_apply_check_required": true,
    "validation_required_after_apply": true,
    "commit_request_required_after_apply": true,
    "auto_commit_default": false,
    "auto_push_default": false,
    "allow_patch_from_review_packet": true,
    "allow_patch_from_cli_file": true,
    "allow_patch_from_cli_text": true,
    "dirty_workspace_requires_override": true
  },
  "files": {
    "review_packet": "task_artifact_current_review_packet",
    "source_apply_state": "source_apply_state",
    "source_apply_request_current": "source_apply_request_current",
    "source_apply_requests_dir": "source_apply_requests_dir",
    "approval_current": "source_apply_approval_current",
    "approvals_dir": "source_apply_approvals_dir",
    "executor_state": "source_apply_executor_state",
    "executor_events": "source_apply_executor_events",
    "executions_dir": "source_apply_executions_dir",
    "patch_staging_dir": "source_apply_patch_staging_dir",
    "validation_current": "source_apply_validation_current",
    "validation_reports_dir": "source_apply_validation_reports_dir",
    "commit_request_current": "source_apply_commit_request_current",
    "commit_requests_dir": "source_apply_commit_requests_dir"
  },
  "validation": {
    "python_compile_changed": true,
    "git_status_after_apply": true
  },
  "patch_sources": [
    "/patch_text",
    "/patch",
    "/unified_diff",
    "/diff",
    "/artifact/patch_text",
    "/artifact/patch",
    "/artifacts/patch_text",
    "/artifacts/patch"
  ]
}
```

Admin runtime default: when effective capability has `approval_required=false`, the executor may use an implicit admin-runtime approval record. This is still recorded in executor state/events.

