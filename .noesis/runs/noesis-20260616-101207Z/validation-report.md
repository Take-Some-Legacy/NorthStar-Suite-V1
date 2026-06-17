# NOESIS testDevRepo validation — noesis-20260616-101207Z

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
      "fixed": true,
      "line": 174,
      "path": "tools/scripts/takesome/noesis_task_artifact_writer.py",
      "phase": "audit",
      "reason": "git diff --check failed; conflict markers found",
      "runId": "noesis-20260616-083414Z"
    },
    {
      "fixed": true,
      "line": 1,
      "path": "tools/toolbelt/first_party/northstar/nemat_packer/test/test.bat",
      "phase": "audit",
      "reason": "git diff --check failed",
      "runId": "noesis-20260616-083537Z"
    },
    {
      "fixed": true,
      "line": 180,
      "path": "tools/scripts/takesome/noesis_task_artifact_writer.py",
      "phase": "build",
      "reason": "SyntaxError: 'return' outside function",
      "runId": "noesis-20260616-083645Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "full_repo_gate_not_implemented",
      "reason": "unknown_failed",
      "runId": "noesis-20260616-093617Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "full_repo_gate_not_implemented",
      "reason": "unknown_failed",
      "runId": "noesis-20260616-093807Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "full_repo_gate_not_implemented",
      "reason": "unknown_failed",
      "runId": "noesis-20260616-094623Z"
    }
  ],
  "readinessKind": "focused_merge_ready",
  "reason": "",
  "runId": "noesis-20260616-101207Z",
  "schema": "noesis.merge_readiness.v2",
  "scope": "noesis-core",
  "scopeDescription": "Focused NOESIS/Suite/action-layer changes only.",
  "scopeWarning": "Focused NOESIS-core gate; not whole repository readiness.",
  "status": "merge_ready",
  "summary": {
    "auditIssues": 0,
    "changedFiles": 18,
    "previousRejections": 6,
    "readinessKind": "focused_merge_ready",
    "scope": "noesis-core",
    "testsFailed": 0,
    "testsPassed": 2,
    "wholeRepositoryReady": false
  },
  "utc": "2026-06-16T10:13:41Z",
  "wholeRepositoryReady": false,
  "workspace": "C:\\Users\\HUAWEI\\Documents\\TakeSomeDevSuite\\.noesis\\workspaces\\testDevRepo-noesis-20260616-101207Z\\repo"
}
```
