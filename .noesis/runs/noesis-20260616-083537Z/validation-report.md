# NOESIS testDevRepo validation — noesis-20260616-083537Z

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
| audit | failed | git diff --check failed |

## Merge readiness

```json
{
  "checks": {
    "artifactsVerified": false,
    "auditPassed": false,
    "buildPassed": false,
    "changesApplied": true,
    "testsPassed": false,
    "verified": false,
    "workspaceCreated": true
  },
  "reason": "audit_failed",
  "runId": "noesis-20260616-083537Z",
  "schema": "noesis.merge_readiness.v1",
  "status": "rejected",
  "summary": {
    "auditIssues": 1,
    "changedFiles": 15,
    "testsFailed": 0,
    "testsPassed": 0
  },
  "utc": "2026-06-16T08:35:43Z",
  "workspace": "C:\\Users\\HUAWEI\\Documents\\TakeSomeDevSuite\\.noesis\\workspaces\\testDevRepo-noesis-20260616-083537Z\\repo"
}
```
