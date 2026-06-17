# Noesis Source Apply Gate

This file defines task behavior for source-apply capability gating. It does not define root keys, task types, or storage paths.

The source-apply capability is not permanently locked. Noesis may enable or disable it through runtime config overlays. Base config writes, source writes, commits and pushes remain gated by explicit policy and audit trail.

```json
{
  "schema": "noesis.suite.source_apply_gate_rules.v1",
  "policy": {
    "capability_may_be_enabled_by_noesis": true,
    "enablement_mechanism": "runtime_config_overlay",
    "base_config_write_required_for_enablement": false,
    "base_config_write_requires_explicit_approval": true,
    "source_apply_requires_capability_enabled": true,
    "source_apply_requires_explicit_approval": true,
    "direct_source_write_without_approval": false,
    "prepare_request_only_when_disabled": true,
    "validation_required_after_approval": true,
    "commit_requires_separate_request": true,
    "push_requires_separate_request": true
  },
  "config": {
    "config_key": "noesis_roots_config",
    "capability_path": "/source_apply",
    "overlay_paths": {
      "enabled": "/source_apply/enabled",
      "enablement_mode": "/source_apply/enablement_mode",
      "auto_apply": "/source_apply/auto_apply",
      "auto_commit": "/source_apply/auto_commit",
      "auto_push": "/source_apply/auto_push",
      "enabled_by": "/source_apply/enabled_by",
      "enabled_utc": "/source_apply/enabled_utc",
      "enable_reason": "/source_apply/enable_reason",
      "last_enable_task_id": "/source_apply/last_enable_task_id"
    }
  },
  "gate_chain": [
    "task_artifact",
    "review_packet",
    "capability_status",
    "enable_capability_overlay_if_task_requires_it",
    "approval_required",
    "approval_executor",
    "patch_apply_after_approval",
    "validate",
    "commit_request",
    "push_request"
  ]
}
```

Admin runtime default: when the Suite process is launched with administrator/write privileges and config `runtime_permissions.admin_defaults.enabled` is true, permissions are active by default. Explicit disable creates a runtime overlay with `source_apply.admin_default_overridden=true`.

