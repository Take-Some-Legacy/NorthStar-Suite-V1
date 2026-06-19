# Suite Action Groups

Suite action descriptors are grouped by operational domain. Descriptors are discovered recursively; directory names are for storage and navigation, while `action_id` remains the stable API key.

Current top-level domains:

- `lang/` — language and runtime workspaces.
  - `lang/java/` — universal Java workspace actions (`java.*`) with Gradle/Maven auto-detection.
  - `lang/npm/` — npm workspace actions (`npm.*`).
  - `lang/rust/` — Rust/Cargo/build/editor actions.
- `NorthStarEngine/` — NorthStar engine asset/tooling actions.
  - `NorthStarEngine/firstParty/` — first-party tool smoke and DDS inspection actions.
  - `NorthStarEngine/metadata/` — YTYP metadata actions.
  - `NorthStarEngine/textures/` — YTD texture actions.
  - `NorthStarEngine/ui/` — UI dictionary actions.
- `system/` — system, operator, filesystem and workspace maintenance actions.
  - `system/diagnostics/` — Suite and NOESIS diagnostics.
  - `system/env/` — environment, compiler and toolchain discovery actions (`env.*`).
  - `system/fileSystem/` — read-only operator filesystem inspection actions (`fs.*`).
  - `system/runtime/` — runtime/game launch actions.
  - `system/source/` — source packaging actions.
  - `system/workspace/` — workspace cleanup and maintenance actions.
- `suite/` — Suite registry, bridge menu and intelligence loop actions.
- `tools/` — ToolRegistry inspection and validation actions.
- `vendor/` — vendored third-party command-line tools.

Repository-local operator context is defined by `reposRoot/repoDir/indexFile.v1.json` and defaults to:

```text
reposRoot/
  repoDir/
    indexFile.v1.json
  dataset/
  workspace/
```

Navigation contract:

```text
domain = first directory under tools/suite/actions
subdomain = second directory when present
action_id = stable public key; never rewrite it only to match directory names
```
