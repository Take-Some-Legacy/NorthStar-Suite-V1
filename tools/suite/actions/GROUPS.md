# Suite action groups

The Suite action registry is recursive. Action descriptors may be grouped by
directory without changing action ids.

Recommended layout:

```text
tools/suite/actions/
  npm/
  rust/
  fileSystem/
  vendor/
  diagnostics/
  workspace/
  ui/
  textures/
  source/
```

Rules:

- Keep `action_id` stable.
- Directory names are storage/navigation groups.
- `category` and `target_domain` remain semantic UI/search metadata.
- The loader should continue using recursive descriptor discovery.