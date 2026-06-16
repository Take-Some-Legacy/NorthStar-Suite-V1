# Noesis Config Overlay Protocol

This file defines task behavior for config override work. It does not define root keys, file paths, task types, or storage directories. Those are config data.

```json
{
  "schema": "noesis.suite.config_override_rules.v1",
  "policy": {
    "overrides_are_allowed_during_tasks": true,
    "override_scope": "any_config_data_registered_in_config_map",
    "default_mode": "runtime_overlay",
    "base_config_write_requires_explicit_approval": true,
    "audit_trail_required": true,
    "effective_config_must_be_reconstructable": true,
    "active_overlays_must_be_reversible": true,
    "direct_source_rewrite_is_not_part_of_config_overlay_protocol": true
  },
  "allowed_operations": ["set", "replace", "merge", "remove"],
  "required_review_fields": ["config_key", "operations", "task_id", "reason", "approval"]
}
```
