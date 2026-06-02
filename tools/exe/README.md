# North Star Executable Tools

This directory stores built first-party executable tools that are launched by the Suite/script plane.

Rules:

- Source code remains in `tools/northstar/<tool>/`.
- `target/` build directories remain local compiler output.
- Only descriptor-owned first-party tools belong here.
- Legacy/reference binaries stay out of this directory.

Current tools:

- `northstar-neui-packer.exe` — XML-first `.neui.xml` <-> NEF8 `.neui` pack/inspect/validate utility.
