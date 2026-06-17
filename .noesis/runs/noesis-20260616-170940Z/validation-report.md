# NOESIS testDevRepo validation — noesis-20260616-170940Z

Final status: `merge_ready`

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
| runtime-boundaries | ok | - |
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
  "previousRejections": [],
  "readinessKind": "focused_merge_ready",
  "reason": "",
  "runId": "noesis-20260616-170940Z",
  "schema": "noesis.merge_readiness.v2",
  "scope": "noesis-core",
  "scopeDescription": "Focused NOESIS/Suite/action-layer changes only.",
  "scopeWarning": "Focused NOESIS-core gate; not whole repository readiness.",
  "status": "merge_ready",
  "summary": {
    "auditIssues": 0,
    "changedFiles": 0,
    "previousRejections": 0,
    "readinessKind": "focused_merge_ready",
    "scope": "noesis-core",
    "testsFailed": 0,
    "testsPassed": 2,
    "wholeRepositoryReady": false
  },
  "utc": "2026-06-16T17:10:01Z",
  "wholeRepositoryReady": false,
  "workspace": "/mnt/data/mayday_final/.noesis/workspaces/testDevRepo-noesis-20260616-170940Z/repo"
}
```
