# North Star Workspace Contract — EngineRepository Ready

> [!IMPORTANT] DECISION BLOCK — EngineRepository + external Suite root
> **Decision:** North Star source tree and Take Some/Suite operational state are independent roots. The source root is `NEWENGINE_REPO_ROOT`; the suite/work-state root is `NEWENGINE_SUITE_ROOT` or `TAKESOME_SUITE_ROOT`.
>
> **Why:** The current repo root mixes engine sources, plugins, importers, tools, launchers, logs, incidents, generated state and dataset material. This creates operational noise and duplicate authority.
>
> **Applies to:** launchers, `init_script_env.py`, `takesome.paths`, build-state, logs, reports, dataset, incidents, status cache and future physical relocation.

## Doctrine

```text
Engine as Host.
Dataset as Truth Host.
Workspace as Contract.
Document as Contract.
Snapshot as Evidence.
Research as Context.
Roadmap as Action.
Diagnostics as Truth.
No legacy. No hidden fallback. No duplicate authority.
```

## Roots

| Root | ENV | Purpose | May live on another disk |
|---|---|---|---:|
| `EngineRepository` | `NEWENGINE_REPO_ROOT` | Source tree: `NewEngine`, `Plugins`, `Importers`, `tools`, docs. | yes |
| `Take Some / Suite root` | `NEWENGINE_SUITE_ROOT` / `TAKESOME_SUITE_ROOT` | Operational state: dataset, logs, build-state, incidents, reports, status cache. | yes |

Current source root:

```text
C:\Users\Aiden\Documents\Take Some\NorthStar-Engine
```

Current suite root:

```text
C:\Users\Aiden\Documents\Take Some\NorthStar-Engine\.takesome
```

## Target source layout

```text
EngineRepository/
  NewEngine/              # core engine source
  Plugins/                # provider implementations
  Importers/              # importer implementations
  tools/                  # script-plane and operator tooling source
  docs/                   # durable documentation
  config/                 # stable source-controlled config
  WORKSPACE.md            # workspace contract
```

## Target Suite/work-state layout

```text
<TAKESOME_SUITE_ROOT>/
  dataSet/                # Dataset as Truth Host
  build-state/            # plugin status, stamps, build registry
  buildLog/               # build logs with heartbeat
  incidents/              # incident bundles
  reports/                # human-readable reports
  suite/runs/             # Suite action results
  status-cache/           # generated status snapshots
  patch-backups/          # patch safety backups
  workspace/              # workspace metadata
  tools/                  # generated tool registry cache
  script-env.cmd          # generated environment contract
```

## Non-destructive relocation policy

This patch intentionally does **not** move live directories while the operator is running from inside the current repository. Physical relocation must be done only after all processes using `tools/` are stopped.

Safe first step:

```bat
py -3 tools\scripts\init_script_env.py --repo-root C:\Path\To\EngineRepository --suite-root D:\NorthStarSuite --emit-cmd D:\NorthStarSuite\script-env.cmd
```

Then launchers must call that generated env file before invoking Suite or build commands.

## Hard rules

- No script should assume `.takesome` is under the source root.
- No generated build state should be written beside `NewEngine`, `Plugins`, `Importers` or `tools`.
- `repo_root()` is source authority.
- `suite_root(repo_root)` is operational-state authority and may be external.
- If a path is derived from both repo and suite roots, the code must say which authority owns it.
- Stale logs in root are WARNs and should be moved into Suite reports/incidents.

## Acceptance checklist

```text
[ ] `init_script_env.py` accepts `--suite-root`.
[ ] `takesome.paths.suite_root()` respects `NEWENGINE_SUITE_ROOT` / `TAKESOME_SUITE_ROOT`.
[ ] `script-env.cmd` exports both source and suite roots.
[ ] Build reports write under suite root.
[ ] Dataset reports write under suite root.
[ ] Root no longer accumulates random buildERR/lastbuild files after migration.
[ ] Physical move is done only after bridge/tools are stopped.
```
