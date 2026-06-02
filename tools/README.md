# North Star Native Tools

`tools/` is a descriptor-driven DEV space. The build scripts do not keep manual tool lists and do not auto-run unknown binaries.

## Current model

```text
tools/
  scripts/                 # Python script-plane: discovery, cache, launchers, build validation
  northstar/devspace/      # native Rust CLI for workspace/build/source validation
  dataTool/                # native GUI/data workstation descriptor
  neassetchain/            # native asset-chain inspector descriptor
```

Every active tool declares `tool.json`:

```json
{
  "schema": "takesome.tool.v1",
  "id": "northstar.devspace",
  "kind": "rust-cli",
  "cargo_manifest": "Cargo.toml",
  "default_args": ["doctor", "--root", "$repo_root"],
  "validation_args": ["doctor", "--root", "$repo_root"],
  "capabilities": ["validation.build_surface"],
  "build_validation": true,
  "safe_for_build": true
}
```

## Commands

From the repository root after `initScriptEnv.bat`:

```bat
devTools.bat scan
devTools.bat list
devTools.bat doctor
devTools.bat build --safe --validate-after-build
devTools.bat build northstar.devspace --validate-after-build
devTools.bat run northstar.devspace -- doctor --root .
devTools.bat run northstar.devspace -- inspect-dds path\to\file.dds
```

Direct Python entrypoints:

```bat
python tools\scripts\takesome.py tools scan
python tools\scripts\takesome.py tools validate
python tools\scripts\takesome.py tools build --safe --validate-after-build
python tools\scripts\takesome.py validate-build
```

`devTools.bat collect-run` writes the diagnostic run bundle first and then removes `NewEngine/neocore2/cache`. If that cache cannot be removed because a process still owns files inside it, the command reports an error instead of silently keeping stale runtime state.

`buildPlugins.bat` runs native tool registry validation, builds every `safe_for_build` Rust tool, runs descriptor-declared validation commands, and only then starts plugin sync. This catches removed legacy identities before the build path accepts them again.

## Legacy policy

Deleted legacy tool identities:

```text
netexturetool
nepak
nematerialtool
nelistfile
nelisyfile
DDSCubemap
DDSHeaderViewer
NoiseGenerator
AssetAnalysisTool
```

The old C++ tools from the reference archives are not copied into the build path. Their useful jobs are represented as native capabilities in `northstar.devspace`, `dataTool`, and `neassetchain`.

```text
DDSHeaderViewer   -> northstar.devspace inspect-dds
DDSCubemap        -> northstar.devspace cubemap-layout + future texture pipeline converter
NoiseGenerator    -> northstar.devspace noise-smoke / procedural-noise crates
AssetAnalysisTool -> northstar.devspace asset-scan + neassetchain role checks
```

No `.exe` from legacy archives should be committed, installed into PATH, or run by build scripts.
