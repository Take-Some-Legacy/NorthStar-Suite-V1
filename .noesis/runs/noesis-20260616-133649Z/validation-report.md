# NOESIS testDevRepo validation — noesis-20260616-133649Z

Final status: `rejected`

## Contract

NOESIS does not produce patches. NOESIS produces verified workspaces.

```text
merge_ready = audit.ok && tests.ok && build.ok && verify.ok
```

## Phases

| Phase | Status | Reason |
|---|---|---|
| workspace | ok | - |
| changes | ok | - |
| forbidden | ok | - |
| audit | ok | - |
| tests | ok | - |
| build | ok | - |
| verify | ok | - |

## Merge readiness

```json
{
  "checks": {
    "artifactsVerified": true,
    "auditPassed": true,
    "buildPassed": true,
    "changesApplied": true,
    "testsPassed": true,
    "verified": true,
    "workspaceCreated": true
  },
  "previousRejections": [
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "workspace",
      "reason": "git worktree add failed",
      "runId": "noesis-20260616-133058Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "build",
      "reason": "git rev-parse --is-inside-work-tree",
      "runId": "noesis-20260616-133211Z"
    }
  ],
  "readinessKind": "global_merge_ready",
  "reason": "full_repo_gate_not_implemented",
  "runId": "noesis-20260616-133649Z",
  "schema": "noesis.merge_readiness.v2",
  "scope": "full-repo",
  "scopeDescription": "Whole repository validation is requested, but readiness is denied until the full gate is implemented.",
  "scopeWarning": "Full repository gate is registered but intentionally rejects until full checks are implemented.",
  "status": "rejected",
  "summary": {
    "auditIssues": 0,
    "changedFiles": 0,
    "previousRejections": 2,
    "readinessKind": "global_merge_ready",
    "scope": "full-repo",
    "testsFailed": 0,
    "testsPassed": 2,
    "wholeRepositoryReady": false
  },
  "utc": "2026-06-16T13:37:02Z",
  "wholeRepositoryReady": false,
  "workspace": "/mnt/data/suite_mig/.noesis/workspaces/testDevRepo-noesis-20260616-133649Z/repo"
}
```
