# North Star Toolbelt

`tools/toolbelt/` is the registry-first home for Suite-visible tools.

The Suite must not hard-code every individual executable. Every tool package owns a descriptor and the Suite recursively scans descriptors.

## Descriptor-first rule

Each tool directory contains one `tool.json` with:

- identity and version
- ownership/source type
- installed executable path or build manifest
- commands with arguments and help text
- validation/smoke contract
- capabilities
- hashes for vendor payloads when applicable

## Layout

```text
tools/toolbelt/
  first_party/
    northstar/
      neui_packer/
      ytd_packer/
      ytyp_packer/
  third_party/
    bison/
    diff/
    sed/
    tar/
    touch/
    hasher/
    symbol_extract/
```

Each package should be self-contained:

```text
<tool-package>/
  tool.json
  README.md
  USAGE.txt          optional, but recommended for external tools
  bin/               execute-ready payload for this package
```

First-party source may remain in `tools/toolsSrc/<tool>/`, but the execute-ready binary and the descriptor live in the toolbelt package. Third-party binaries stay quarantined in their own package directories. GNUWin32 tools are split into `third_party/<tool>/bin/`, not collected under one shared GNUWin32 bin directory.

## Adding a new tool

1. Create a directory under `first_party/` or `third_party/`.
2. Add `tool.json`.
3. Add `README.md` describing exact usage and ownership.
4. Add `USAGE.txt` for external/vendor command-line tools.
5. Add vendor hashes or build metadata.
6. Run `takesome.py tools scan`.

No `takesome.py` code changes should be required for a descriptor-only tool.

## Safety

- No shell expansion in wrappers.
- Vendor payloads require SHA-256 hashes.
- Tools that mutate files should expose dry-run/check mode when possible.
- Engine runtime must not depend on third-party toolbelt binaries.
