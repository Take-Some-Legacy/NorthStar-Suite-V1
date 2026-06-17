# NOESIS Task Completion Rules

This file defines how the generic loop decides whether the current task is complete.
It does not define task types.
It only defines observable completion criteria.

```json
{
  "schema": "noesis.suite.task_completion_rules.v1",
  "stop_when_done": true,
  "done_markers": [
    "TASK_DONE:",
    "DONE:"
  ],
  "required_files": [
    ".takesome/intelligence/task-artifacts/current/repo-update-manifest.json",
    ".takesome/intelligence/task-artifacts/current/repo.patch",
    ".takesome/intelligence/task-artifacts/current/review-packet.json",
    ".takesome/intelligence/task-artifacts/current/review-request.md"
  ]
}
```

Proof chain:

```text
INTENT -> ACTION -> WRITE -> VERIFY -> TRACE
```

Rule:

```text
If there is no trace, there was no work.
If there is no verification, the trace is not trusted.
If the task is not done, the loop continues.
```
