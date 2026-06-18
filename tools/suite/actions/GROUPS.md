# Suite Action Descriptor Groups

Recommended layout:

```text
tools/suite/actions/
  lang/
    java/
    npm/
    rust/

  NorthStarEngine/
    firstParty/
    metadata/
    textures/
    ui/

  system/
    diagnostics/
    env/
    fileSystem/
    runtime/
    source/
    workspace/

  suite/
  tools/
  vendor/
```

Rules:

- Keep action identifiers stable.
- Directory names are storage/navigation groups.
- Top-level directory is the action domain: `lang`, `NorthStarEngine`, `system`, `suite`, `tools`, or `vendor`.
- Nested directory is the action subdomain: for example `system/fileSystem` or `NorthStarEngine/textures`.
- Descriptor `group` can remain semantic/legacy metadata; UI should prefer descriptor path taxonomy for domain navigation.
- The loader must continue using recursive descriptor discovery.
- Repository-local execution context should be taken from repoDir/indexFile.v1.json when present.
