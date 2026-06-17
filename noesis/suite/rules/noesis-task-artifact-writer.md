# Noesis Task Artifact Writer Rules

This file dictates the currently assigned task behavior for the generic task artifact writer.
Storage roots and file destinations are configured in `.takesome/config/noesis-roots.v1.json`.
The assigned task may be self-improvement, game development, website work, UI work, research, or any other task. Python must not contain a task-type registry.

```json noesis-task-artifact-writer.v1
{
  "schema": "noesis.suite.task_artifact_writer_rules.v1",
  "artifact_mode": "task_artifact_with_repository_file_updates",
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
    "root_keys_from_config": true,
    "repo_file_updates_required": true,
    "actual_repository_files_are_target": true
  },
  "focus": [
    "Create artifacts for the current assigned task, regardless of task domain.",
    "Do not use a task-type registry.",
    "Read root/file locations from `.takesome/config/noesis-roots.v1.json`.",
    "Use chat/task artifacts/source apply gates/capability state as runtime evidence.",
    "If source changes are needed, produce a reviewable patch artifact and route it through the approval executor.",
    "The iteration result must name and stage repository file updates, not only descriptive artifacts.",
    "Repository file updates are represented as staged file snapshots plus a unified patch artifact.",
    "The target repository root is selected by rules/config and can be changed without a task-type registry."
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
    "chat_state",
    "task_artifact_current_repo_update_manifest",
    "task_artifact_current_repo_patch",
    "task_artifact_current_updated_version"
  ],
  "templates": {
    "proposal_title": "Noesis generic assigned task proposal",
    "proposal_body": "Noesis accepted assigned task `{assigned_task_id}` in stage `{stage}`. Review root context, capability state, current operator directive and attached runtime files. Produce the safest next executable step without assuming a task type.",
    "draft_title": "Noesis generic assigned task draft",
    "draft_body": "Draft for `{assigned_task_id}`: use configured roots/files; inspect runtime evidence; report risks; prepare source/config changes only as reviewable artifacts unless capability and approval executor permit execution.",
    "review_request_title": "Noesis generic assigned task review request",
    "review_request_body": "Please review the task artifact packet for `{assigned_task_id}`. The result must include repository file update candidates: staged snapshots and a unified patch. Confirm whether Noesis should continue staging repo file updates or execute the patch through the configured executor.",
    "updated_version_title": "Noesis generic assigned task updated version",
    "updated_version_body": "Updated version for `{assigned_task_id}` at cycle `{cycle}`. The result of this iteration must be expressed as repository file changes: target root, repo-relative paths, staged snapshots, patch artifact, validation notes and next action.",
    "repo_update_file_title": "Noesis Current Task Repository Update",
    "repo_update_file_body": "# {repo_update_file_title}\n\ngenerated_utc: {generated_utc}\ncycle: {cycle}\nstage: {stage}\nassigned_task_id: `{assigned_task_id}`\n\n## Target\n\nThis file is an actual repository-file update candidate generated for the currently assigned task.\n\n## Current task\n\n{label}\n\n## Required direction\n\n- Improve the repository, not only runtime artifacts.\n- Reduce duplication and root confusion.\n- Improve usability and diagnostics.\n- Keep task behavior controlled by Markdown rules and config.\n\n## Next concrete action\n\nInspect the repo-relative paths named in the repo update manifest and produce the next patchable revision.\n"
  },
  "repo_file_updates": {
    "enabled": true,
    "target_root_key": "suite_root",
    "manifest_current_file_key": "task_artifact_current_repo_update_manifest",
    "patch_current_file_key": "task_artifact_current_repo_patch",
    "files_current_dir_key": "task_artifact_current_repo_files_dir",
    "manifest_archive_dir_key": "task_artifact_repo_update_manifests_dir",
    "patch_archive_dir_key": "task_artifact_repo_patches_dir",
    "files_archive_dir_key": "task_artifact_repo_files_dir",
    "updated_version_current_file_key": "task_artifact_current_updated_version",
    "updated_versions_archive_dir_key": "task_artifact_updated_versions_dir",
    "file_snapshots": [
      {
        "path": "docs/noesis/current-task-updated-version.md",
        "content_template": "repo_update_file_body",
        "description": "Repository-visible current task updated version. This is a repo file candidate, not runtime-only state."
      }
    ]
  }
}
```
