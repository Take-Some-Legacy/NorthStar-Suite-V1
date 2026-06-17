# Noesis operator response rules

This file is the single source of truth for operator-response interpretation.
Python code must execute this declarative rule set and must not hard-code operator commands, intent markers, action ids, or self-improvement vocabulary.

```json
{
  "schema": "noesis.suite.operator_response_rules.v1",
  "normalization": {
    "strip": true,
    "remove_codepoints": [
      "﻿",
      "​",
      "‌",
      "‍"
    ],
    "replace": []
  },
  "special": {
    "missing": {
      "kind": "missing",
      "available": false,
      "summary": "operator response is not available",
      "stage": "waiting_for_operator",
      "state": "waiting",
      "ready_to_assign": true,
      "busy": false,
      "blocked": false,
      "policy": {
        "assign": true,
        "status": "assigned",
        "execution_policy": "assignment_only_no_auto_execute"
      }
    },
    "timed_out": {
      "kind": "timed_out",
      "available": false,
      "summary": "operator response timed out",
      "stage": "waiting_for_operator",
      "state": "waiting",
      "ready_to_assign": true,
      "busy": false,
      "blocked": false,
      "policy": {
        "assign": true,
        "status": "assigned",
        "execution_policy": "assignment_only_no_auto_execute"
      }
    }
  },
  "response_kinds": [
    {
      "id": "operator_approved",
      "kind": "approved",
      "summary": "operator approved current request",
      "match": {
        "regex": "^\\s*APPROVE\\b"
      },
      "stage": "operator_approved",
      "state": "working",
      "ready_to_assign": false,
      "busy": true,
      "blocked": false,
      "policy": {
        "assign": false,
        "status": "not_assigned",
        "execution_policy": "operator_approved_existing_request"
      },
      "reasons": [
        "matched approved operator command from markdown rules"
      ]
    },
    {
      "id": "operator_override",
      "kind": "override",
      "summary": "operator supplied override",
      "match": {
        "regex": "^\\s*OVERRIDE\\b"
      },
      "extract": {
        "override_body": "^\\s*OVERRIDE\\s*:?\\s*(?P<override_body>.*)$"
      },
      "stage": "operator_override",
      "state": "working",
      "ready_to_assign": true,
      "busy": true,
      "blocked": false,
      "candidate": {
        "action_id_template": "{override_body}",
        "label_template": "{override_body}",
        "detail": "operator override from operator-response.md",
        "category": "operator",
        "target_domain": "operator",
        "risk_level": "unknown",
        "requires_approval": true,
        "final_score": 1.0,
        "classification_reasons": [
          "operator override matched markdown rules"
        ]
      },
      "policy": {
        "assign": true,
        "status": "needs_approval",
        "execution_policy": "requires_explicit_approval_no_auto_execute"
      },
      "reasons": [
        "matched override operator command from markdown rules"
      ]
    },
    {
      "id": "operator_task",
      "kind": "task",
      "summary": "operator supplied an executable generic task",
      "match": {
        "regex": "^\\s*TASK\\b"
      },
      "extract": {
        "task_title": "^\\s*TASK\\s*:?\\s*(?P<task_title>[^\\r\\n]*)"
      },
      "stage": "operator_task_requested",
      "state": "working",
      "ready_to_assign": true,
      "busy": true,
      "blocked": false,
      "candidate": {
        "action_id": "operator.task",
        "label_template": "{task_title}",
        "detail_template": "{text}",
        "category": "operator",
        "target_domain": "operator_assigned_task",
        "primary_tag": "NOESIS_TASK",
        "risk_level": "variable",
        "requires_approval": false,
        "final_score": 1.5,
        "classification_reasons": [
          "operator TASK directive matched markdown rules",
          "generic task assignment; no task-type registry"
        ]
      },
      "policy": {
        "assign": true,
        "status": "assigned",
        "execution_policy": "admin_runtime_or_capability_gated_execution"
      },
      "reasons": [
        "matched generic TASK operator directive from markdown rules"
      ]
    },
    {
      "id": "operator_note",
      "kind": "note",
      "summary": "operator supplied a note",
      "match": {
        "regex": "^\\s*NOTE\\b"
      },
      "stage": "operator_note_available",
      "state": "waiting",
      "ready_to_assign": true,
      "busy": false,
      "blocked": false,
      "policy": {
        "assign": true,
        "status": "assigned",
        "execution_policy": "assignment_only_no_auto_execute"
      },
      "reasons": [
        "matched note operator command from markdown rules"
      ]
    }
  ],
  "fallback_kind": {
    "id": "operator_freeform",
    "kind": "freeform",
    "summary": "operator supplied freeform response",
    "stage": "operator_note_available",
    "state": "waiting",
    "ready_to_assign": true,
    "busy": false,
    "blocked": false,
    "policy": {
      "assign": true,
      "status": "assigned",
      "execution_policy": "assignment_only_no_auto_execute"
    },
    "reasons": [
      "freeform fallback from markdown rules"
    ]
  },
  "intent_rules": [
    {
      "id": "noesis_self_improvement_pipeline",
      "priority": 100,
      "summary": "operator requested Noesis self-improvement pipeline",
      "match": {
        "all_regex": [
          "^\\s*OVERRIDE\\b"
        ],
        "any_regex": [
          "self[-\\s]?improvement",
          "самоулучш\\w*",
          "развити\\w*",
          "сокращ\\w*\\s+повтор\\w*",
          "дубл\\w*",
          "связк\\w*",
          "архитект\\w*",
          "refactor",
          "cohesion",
          "legacy",
          "hardcode\\w*",
          "pipeline",
          "конвей\\w*"
        ]
      },
      "stage": "self_improvement_requested",
      "state": "working",
      "ready_to_assign": true,
      "busy": true,
      "blocked": false,
      "candidate": {
        "action_id": "noesis.self_improvement.audit",
        "label": "Noesis self-improvement architecture audit",
        "detail": "Read-only audit for duplicated logic, weak coupling, legacy fallbacks and non-centralized configuration paths.",
        "category": "architecture",
        "target_domain": "noesis",
        "primary_tag": "NOESIS",
        "risk_level": "read_only",
        "requires_approval": false,
        "final_score": 1.25,
        "classification_reasons": [
          "self-improvement intent matched markdown rules",
          "read-only audit assignment",
          "no write/destructive execution without approval"
        ]
      },
      "policy": {
        "assign": true,
        "status": "assigned",
        "execution_policy": "assignment_only_no_auto_execute"
      },
      "reasons": [
        "matched Noesis self-improvement intent from markdown rules"
      ]
    }
  ],
  "default_assignment": {
    "action_id": "suite.doctor",
    "label": "Run Suite doctor and summarize blocking issues",
    "detail": "Default read-only maintenance task from operator-response-rules.md.",
    "category": "diagnostics",
    "target_domain": "suite",
    "risk_level": "read_only",
    "requires_approval": false,
    "final_score": 0.5,
    "classification_reasons": [
      "default assignment from markdown rules"
    ]
  },
  "scoring_rules": [
    {
      "id": "diagnostics_for_failed_checks",
      "when_stage_any": [
        "self_checks_failing",
        "blocked_runtime_state_in_worktree"
      ],
      "candidate_regex_any": [
        "doctor",
        "validate",
        "status",
        "check",
        "audit"
      ],
      "boost": 0.35,
      "reason": "stage boost from markdown rules: diagnostics needed"
    },
    {
      "id": "worktree_review_for_dirty_repo",
      "when_signal_true": "dirty_worktree",
      "candidate_regex_any": [
        "git",
        "diff",
        "status",
        "patch"
      ],
      "boost": 0.25,
      "reason": "stage boost from markdown rules: worktree has changes"
    },
    {
      "id": "safe_diagnostic_policy_boost",
      "candidate_regex_any": [
        "status",
        "list",
        "validate",
        "doctor"
      ],
      "risk_any": [
        "read_only",
        "safe",
        "diagnostics",
        "none",
        ""
      ],
      "boost": 0.12,
      "reason": "policy boost from markdown rules: safe/diagnostic task"
    },
    {
      "id": "approval_penalty_for_write_risk",
      "risk_any": [
        "writes_workspace",
        "write",
        "sudo_write",
        "destructive",
        "dangerous"
      ],
      "boost": -0.3,
      "reason": "policy penalty from markdown rules: write/destructive task requires explicit approval"
    }
  ]
}
```
