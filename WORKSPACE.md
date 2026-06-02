# North Star Engine — Operator Workspace

> Purpose: keep the root workspace predictable for human work and AI-assisted maintenance.
>
> Rule: source belongs to the project; generated state belongs to `.takesome`; command logic belongs to Python/Suite; launchers only launch.

## Root surface

The root should stay short and operational:

```text
suite.bat          primary human Suite shell
aiBridge.bat       AI/MCP bridge launcher
aiBridgeServer.bat stdio MCP compatibility launcher
README.md
WORKSPACE.md
lastbuild-all.log / lastbuild.log if generated
last-incident.md / last-incident.json if generated
```

Avoid leaving temporary patches, run bundles, random logs, copied DLLs or helper scripts in root. Put reusable references in `.takesome/dataSet` and generated diagnostics under `.takesome`.

## AI bridge commands

```bat
aiBridge.bat              local status and usage
aiBridge.bat read         HTTP MCP bridge, read-only
aiBridge.bat write        HTTP MCP bridge, write-enabled
aiBridge.bat http         HTTP MCP bridge, preserves current env
aiBridge.bat stdio        silent stdio MCP server
aiBridge.bat tunnel       Cloudflare tunnel helper for 127.0.0.1:8765
serverBridge.bat          starts local MCP origin + stable Cloudflare named tunnel
aiBridge.bat --openai-login
aiBridge.bat --openai-forget
```

Recommended safe connection flow:

```text
1. serverBridge.bat
2. connect ChatGPT app to https://suite.kaylas-systems.ru/mcp
3. verify northstar.status, northstar.operator_snapshot, northstar.dataset_status
4. keep serverBridge.bat running while external clients are connected
```

Fallback/dev flow:

```text
1. aiBridge.bat read
2. aiBridge.bat tunnel
3. connect ChatGPT app to https://<trycloudflare-domain>/mcp
4. restart with aiBridge.bat write only when patch/build work is intended
```

## Stable Cloudflare tunnel

`serverBridge.bat` owns the one-window operator flow: it starts the local MCP origin on `127.0.0.1:8765`, then starts the declared named Cloudflare tunnel from `config/suite/ai_bridge.v1.json`.

Default source-level binding:

```text
tunnel: northstar-suite
hostname: suite.kaylas-systems.ru
public MCP endpoint: https://suite.kaylas-systems.ru/mcp
local origin: http://127.0.0.1:8765
transport policy: http2 primary, quic/auto fallback
```

Generated local state may still override this through `.takesome/ai-bridge/state/stable-tunnel.json`, and environment variables have highest priority:

```text
NORTHSTAR_CLOUDFLARE_TUNNEL
NORTHSTAR_PUBLIC_MCP_ENDPOINT
NORTHSTAR_CLOUDFLARED_PROTOCOL
NORTHSTAR_CLOUDFLARED_FALLBACK_PROTOCOLS
```

The default policy keeps restrictive-network stability first (`http2`) but does not remove QUIC: if HTTP/2 startup fails, supervisor retries with `quic`, then `auto`. Setting `NORTHSTAR_CLOUDFLARED_PROTOCOL=auto` delegates transport choice to cloudflared.

Origin self-healing rule: if `serverBridge.bat` finds an already-running local origin at startup, it may adopt it, but it keeps probing `/health`. If that adopted process disappears and Cloudflare would otherwise log `dial tcp 127.0.0.1:8765: connectex`, the supervisor starts an owned origin process and keeps the named tunnel alive.

## Dataset directory

Configured path:

```text
.takesome/dataSet
```

Put source snapshots, reference zips, run bundles and subsystem archives there. The bridge scans zip archives through explicit dataset tools, not by guessing random root files.

Suggested naming:

```text
NorthStar-Engine-source-YYYYMMDD-HHMMSS.zip
run-bundle-YYYYMMDD-HHMMSS.zip
framework.zip
scene.zip
streaming.zip
SaveLoad.zip
renderer.zip
text.zip
ai.zip
network.zip
```

When changing code, inspect the dataset first for ownership and architecture patterns. Use it as reference signal, not as copied implementation.

## Patch discipline

AI-assisted changes should follow this loop:

```text
observe -> analyze -> propose -> write/apply patch -> verify -> build/run if requested
```

Direct write tools and changed-files patch apply create backups under:

```text
.takesome/ai-bridge/patch-backups
```

Because this workspace may not be a git checkout, do not rely on git for rollback unless `northstar.git_status` confirms it.

## Logs and diagnostics

First places to inspect:

```text
.takesome/buildLog/plugin-sync-latest.log
.takesome/incidents/*/summary.md
last-incident.md
last-incident.json
.takesome/ai-bridge/logs/*.jsonl
```

A good diagnostic handoff includes:

```text
incident summary
latest plugin sync log
plugin status
workspace registry
operator snapshot
```

## Invariants

```text
One command plane: Suite.
One AI entry: aiBridge.bat.
One generated-state root: .takesome.
No arbitrary shell exposed to AI.
No absolute/parent-traversal file operations.
No root dumping ground.
Dataset is consulted before non-trivial engine code changes.
```


## Suite public bridge origin

Production Suite bridge URL is stable and must prefer the named Cloudflare Tunnel:

```text
https://suite.kaylas-systems.ru/mcp
```

Resolution order:

1. named Cloudflare Tunnel from `config/suite/bridge_public_origin.v1.json`;
2. configured public origin;
3. quick TryCloudflare tunnel only when `quick_tunnel_fallback=true`.

Quick Tunnel is fallback/dev-emergency mode only. It must not replace configured
`public_origin` in production status blocks.
