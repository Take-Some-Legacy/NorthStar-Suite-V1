# NOESIS testDevRepo validation — noesis-20260616-190457Z

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
| runtime-boundaries | ok | - |
| forbidden | ok | - |
| audit | ok | - |
| tests | ok | - |
| build | ok | - |
| verify | ok | - |
| full-repo | skeleton | full-repo gate skeleton is present but not yet enforcement-ready |

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
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "full_repo_gate_not_implemented",
      "reason": "unknown_failed",
      "runId": "noesis-20260616-094623Z"
    },
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
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "full_repo_gate_not_implemented",
      "reason": "unknown_failed",
      "runId": "noesis-20260616-133649Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "workspace",
      "reason": "git worktree add failed",
      "runId": "noesis-20260616-154517Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "workspace",
      "reason": "git worktree add failed",
      "runId": "noesis-20260616-154524Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "workspace",
      "reason": "git worktree add failed",
      "runId": "noesis-20260616-154539Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "build",
      "reason": "git rev-parse --is-inside-work-tree",
      "runId": "noesis-20260616-154837Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "runtime-boundaries",
      "reason": "forbidden_runtime_roots_present",
      "runId": "noesis-20260616-182226Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "runtime-boundaries",
      "reason": "forbidden_runtime_roots_present",
      "runId": "noesis-20260616-184715Z"
    },
    {
      "fixed": false,
      "line": null,
      "path": "",
      "phase": "full-repo",
      "reason": "full-repo gate skeleton is present but not yet enforcement-ready",
      "runId": "noesis-20260616-190344Z"
    }
  ],
  "readinessKind": "global_merge_ready",
  "reason": "full_repo_gate_skeleton_not_enforcement_ready",
  "runId": "noesis-20260616-190457Z",
  "schema": "noesis.merge_readiness.v2",
  "scope": "full-repo",
  "scopeDescription": "Whole repository validation is requested, but readiness is denied until the full gate is implemented.",
  "scopeWarning": "Full repository gate is registered but intentionally rejects until full checks are implemented.",
  "status": "rejected",
  "summary": {
    "auditIssues": 0,
    "changedFiles": 242,
    "previousRejections": 16,
    "readinessKind": "global_merge_ready",
    "scope": "full-repo",
    "testsFailed": 0,
    "testsPassed": 2,
    "wholeRepositoryReady": false
  },
  "utc": "2026-06-16T19:05:10Z",
  "wholeRepositoryReady": false,
  "workspace": "C:\\Users\\HUAWEI\\Documents\\TakeSomeDevSuite\\.noesis\\workspaces\\testDevRepo-noesis-20260616-190457Z\\repo"
}
```
