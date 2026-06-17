# NOESIS testDevRepo validation — noesis-20260616-094623Z

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
      "line": 174,
      "path": "tools/scripts/takesome/noesis_task_artifact_writer.py",
      "phase": "audit",
      "reason": "git diff --check failed; conflict markers found",
      "runId": "noesis-20260616-083414Z"
    },
    {
      "fixed": false,
      "line": 1,
      "path": "tools/toolbelt/first_party/northstar/nemat_packer/test/test.bat",
      "phase": "audit",
      "reason": "git diff --check failed",
      "runId": "noesis-20260616-083537Z"
    },
    {
      "fixed": false,
      "line": 180,
      "path": "tools/scripts/takesome/noesis_task_artifact_writer.py",
      "phase": "build",
      "reason": "SyntaxError: 'return' outside function",
      "runId": "noesis-20260616-083645Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "full_repo_gate_not_implemented",
      "reason": "unknown_failed",
      "runId": "noesis-20260616-093617Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "full_repo_gate_not_implemented",
      "reason": "unknown_failed",
      "runId": "noesis-20260616-093807Z"
    }
  ],
  "readinessKind": "global_merge_ready",
  "reason": "full_repo_gate_not_implemented",
  "runId": "noesis-20260616-094623Z",
  "schema": "noesis.merge_readiness.v2",
  "scope": "full-repo",
  "scopeDescription": "Whole repository validation is requested, but readiness is denied until the full gate is implemented.",
  "scopeWarning": "Full repository gate is registered but intentionally rejects until full checks are implemented.",
  "status": "rejected",
  "summary": {
    "auditIssues": 0,
    "changedFiles": 26,
    "previousRejections": 5,
    "readinessKind": "global_merge_ready",
    "scope": "full-repo",
    "testsFailed": 0,
    "testsPassed": 2,
    "wholeRepositoryReady": false
  },
  "utc": "2026-06-16T09:46:33Z",
  "wholeRepositoryReady": false,
  "workspace": "C:\\Users\\HUAWEI\\Documents\\TakeSomeDevSuite\\.noesis\\workspaces\\testDevRepo-noesis-20260616-094623Z\\repo"
}
```
