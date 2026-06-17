# NOESIS testDevRepo validation — noesis-20260616-083645Z

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
| audit | ok | - |
| tests | ok | - |
| build | failed | C:\Users\HUAWEI\AppData\Local\Python\pythoncore-3.14-64\python.exe -m py_compile tools/scripts/northstar_bridge/bridge_restart.py tools/scripts/northstar_bridge/memory_diagnostics.py tools/scripts/northstar_bridge/memory_schema.py tools/scripts/takesome/assistant_presence.py tools/scripts/takesome/commands/core_cli.py tools/scripts/takesome/noesis_task_artifact_writer.py tools/scripts/takesome/suite_intelligence_loop.py tools/scripts/takesome/workloop_trace.py tools/scripts/takesome/noesis_audit_log.py tools/scripts/takesome/noesis_task_completion.py tools/scripts/takesome/noesis_test_dev_repo.py |

## Merge readiness

```json
{
  "checks": {
    "artifactsVerified": false,
    "auditPassed": true,
    "buildPassed": false,
    "changesApplied": true,
    "testsPassed": true,
    "verified": false,
    "workspaceCreated": true
  },
  "reason": "build_failed",
  "runId": "noesis-20260616-083645Z",
  "schema": "noesis.merge_readiness.v1",
  "status": "rejected",
  "summary": {
    "auditIssues": 0,
    "changedFiles": 15,
    "testsFailed": 0,
    "testsPassed": 2
  },
  "utc": "2026-06-16T08:36:55Z",
  "workspace": "C:\\Users\\HUAWEI\\Documents\\TakeSomeDevSuite\\.noesis\\workspaces\\testDevRepo-noesis-20260616-083645Z\\repo"
}
```
