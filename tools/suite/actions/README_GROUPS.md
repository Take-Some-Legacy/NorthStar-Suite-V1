# Suite action groups

Suite action descriptors are discovered recursively from `tools/suite/actions/**/*.json`.

Directory names are storage/navigation groups. They must not change `action_id` values.

Current groups:

- `build/` — build registry and build-system actions.
- `fileSystem/` — filesystem inspection actions (`fs.*`).
- `firstParty/` — first-party tool smoke and DDS inspection actions.
- `metadata/` — YTYP metadata actions.
- `npm/` — npm workspace actions (`npm.*`).
- `rust/` — Rust/Cargo/build/editor actions.
- `runtime/` — runtime/game launch actions.
- `source/` — source packaging actions.
- `suite/` — Suite registry, bridge menu and intelligence actions.
- `textures/` — YTD texture dictionary actions.
- `tools/` — ToolRegistry and descriptor hygiene actions.
- `ui/` — NEUI UI asset actions.
- `vendor/` — third-party/vendor/toolbelt smoke and GNU/MSYS2 helper actions.
- `workspace/` — workspace maintenance actions.

Rules:

1. Keep `action_id` stable.
2. Prefer one action domain per directory.
3. Keep `category`, `target_domain` and `chips` as semantic metadata.
4. Do not put generated run outputs in this tree.
5. Long-running and destructive actions must be explicit in `risk_level` and hints.
