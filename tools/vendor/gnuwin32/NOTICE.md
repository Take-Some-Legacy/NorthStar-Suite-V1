# Vendor Notice

This directory is reserved for GNUWin32-compatible third-party command-line tools used by the Suite/workspace layer.

The uploaded candidate binaries are expected to be GNU/GnuWin32-era builds of GNU diffutils and GNU sed with their runtime DLL dependencies. Before distributing these binaries with the repository, keep the matching license/source notices here.

Current expected payload hashes are recorded in `HASHES.sha256.txt`.

Packaging policy:

- These tools are vendor binaries, not North Star first-party tools.
- They must stay under `tools/vendor/gnuwin32/bin/`.
- First-party tools must stay under `tools/exe/`.
- Engine runtime must not depend on this vendor toolset.
