# NOESIS testDevRepo validation — noesis-20260617-080052Z

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
    "fullRepoEnforcementReady": false,
    "fullRepoGate": false,
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
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "workspace",
      "reason": "git worktree add failed",
      "runId": "noesis-20260616-133058Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "build",
      "reason": "git rev-parse --is-inside-work-tree",
      "runId": "noesis-20260616-133211Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "full_repo_gate_not_implemented",
      "reason": "unknown_failed",
      "runId": "noesis-20260616-133649Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "workspace",
      "reason": "git worktree add failed",
      "runId": "noesis-20260616-154517Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "workspace",
      "reason": "git worktree add failed",
      "runId": "noesis-20260616-154524Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "workspace",
      "reason": "git worktree add failed",
      "runId": "noesis-20260616-154539Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "build",
      "reason": "git rev-parse --is-inside-work-tree",
      "runId": "noesis-20260616-154837Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "runtime-boundaries",
      "reason": "forbidden_runtime_roots_present",
      "runId": "noesis-20260616-182226Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "runtime-boundaries",
      "reason": "forbidden_runtime_roots_present",
      "runId": "noesis-20260616-184715Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "full-repo",
      "reason": "full-repo gate skeleton is present but not yet enforcement-ready",
      "runId": "noesis-20260616-190344Z"
    },
    {
      "fixed": true,
      "line": null,
      "path": "",
      "phase": "full-repo",
      "reason": "full-repo gate skeleton is present but not yet enforcement-ready",
      "runId": "noesis-20260616-190457Z"
    }
  ],
  "readinessKind": "focused_merge_ready",
  "reason": "",
  "runId": "noesis-20260617-080052Z",
  "schema": "noesis.merge_readiness.v2",
  "scope": "noesis-core",
  "scopeDescription": "Focused NOESIS/Suite/action-layer changes only.",
  "scopeWarning": "Focused NOESIS-core gate; not whole repository readiness.",
  "status": "merge_ready",
  "summary": {
    "auditIssues": 0,
    "changedFiles": 242,
    "fullRepoBlockingChecks": [],
    "fullRepoEnforcementReady": false,
    "fullRepoMode": "not-requested",
    "previousRejections": 17,
    "readinessKind": "focused_merge_ready",
    "scope": "noesis-core",
    "testsFailed": 0,
    "testsPassed": 3,
    "wholeRepositoryReady": false
  },
  "utc": "2026-06-17T08:01:08Z",
  "wholeRepositoryReady": false,
  "workspace": "C:\\Users\\HUAWEI\\Documents\\TakeSomeDevSuite\\.noesis\\workspaces\\testDevRepo-noesis-20260617-080052Z\\repo"
}
```
