# npm CLI adapter

This is a DevSuite-owned npm adapter.

It is not part of any specific website or application package. DevSuite owns this
tool and applies it to the active workspace.

## Resolution

The launcher resolves npm in this order:

1. `%ProgramFiles%\nodejs\npm.cmd`
2. `npm.cmd` from PATH

## Tool id

```text
vendor.npm
```

## Typical Suite actions

```text
npm.version
npm.list_scripts
npm.install
npm.ci
npm.build
npm.typecheck
npm.lint
npm.test
npm.dev
npm.preview
npm.audit
npm.outdated
```

## Workspace model

The active workspace is selected by the bridge/Suite runtime, not by this tool.
For example, TakeSomeWebsite can be a workspace target, but npm remains a
DevSuite foundational tool.