# NOESIS testDevRepo validation — noesis-20260616-133058Z

Final status: `rejected`

## Contract

NOESIS does not produce patches. NOESIS produces verified workspaces.

```text
merge_ready = audit.ok && tests.ok && build.ok && verify.ok
```

## Phases

| Phase | Status | Reason |
|---|---|---|
| workspace | failed | git worktree add failed |

## Merge readiness

```json
{
  "checks": {
    "artifactsVerified": false,
    "auditPassed": false,
    "buildPassed": false,
    "changesApplied": false,
    "testsPassed": false,
    "verified": false,
    "workspaceCreated": false
  },
  "previousRejections": [],
  "readinessKind": "focused_merge_ready",
  "reason": "workspace_create_failed",
  "runId": "noesis-20260616-133058Z",
  "schema": "noesis.merge_readiness.v2",
  "scope": "noesis-core",
  "scopeDescription": "Focused NOESIS/Suite/action-layer changes only.",
  "scopeWarning": "Focused NOESIS-core gate; not whole repository readiness.",
  "status": "rejected",
  "summary": {
    "auditIssues": 0,
    "changedFiles": 0,
    "previousRejections": 0,
    "readinessKind": "focused_merge_ready",
    "scope": "noesis-core",
    "testsFailed": 0,
    "testsPassed": 0,
    "wholeRepositoryReady": false
  },
  "utc": "2026-06-16T13:30:58Z",
  "wholeRepositoryReady": false,
  "workspace": "/mnt/data/suite_mig/.noesis/workspaces/testDevRepo-noesis-20260616-133058Z/repo"
}
```
