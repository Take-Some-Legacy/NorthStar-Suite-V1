# NOESIS testDevRepo validation — noesis-20260616-083414Z

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
| audit | failed | git diff --check failed; conflict markers found |

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
  "runId": "noesis-20260616-083414Z",
  "schema": "noesis.merge_readiness.v1",
  "status": "rejected",
  "summary": {
    "auditIssues": 2,
    "changedFiles": 15,
    "testsFailed": 0,
    "testsPassed": 0
  },
  "utc": "2026-06-16T08:34:29Z",
  "workspace": "C:\\Users\\HUAWEI\\Documents\\TakeSomeDevSuite\\.noesis\\workspaces\\testDevRepo-noesis-20260616-083414Z\\repo"
}
```
