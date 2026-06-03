# GNUWin32 Vendor Toolset

This directory is a quarantined vendor toolset for GNU/Linux-style command-line utilities used by the Suite/workspace layer.

It is **not** a first-party North Star executable directory. First-party tools stay in `tools/exe/` and sources stay in `tools/toolsSrc/`.

Current payload:

```text
tools/vendor/gnuwin32/bin/
  bison.exe
  diff.exe
  diff3.exe
  fgrep.exe
  flex++.exe
  flex.exe
  funzip.exe
  m4.exe
  make.exe
  sdiff.exe
  sed.exe
  tail.exe
  tar.exe
  touch.exe
  libintl3.dll
  libintl-2.dll
  libiconv2.dll
  libiconv-2.dll
  regex2.dll
```

Rules:

- Treat these files as third-party/vendor CLI tools.
- Do not load them from engine runtime code.
- Do not add them as plugins.
- Do not put them in `tools/exe/`.
- Suite wrappers must pass explicit arguments and avoid shell expansion.
- Keep hashes in `HASHES.sha256.txt` in sync with the binaries.
- Keep license/source notices under this directory before distributing binaries.

Wrapped commands:

- `vendor-gnuwin32-doctor` — verify payload hashes and presence.
- `diff-files`, `sdiff-files`, `diff3-files` — safe comparison wrappers.
- `sed-file` — controlled stream edit wrapper.
- `touch-file` — timestamp/create-file wrapper.
- `fgrep-files` — fixed-string search wrapper.
- `tail-file` — bounded last-lines reader.
- `tar-list`, `tar-extract`, `tar-create` — archive wrappers for Suite/workspace artifacts.

Unwrapped but tracked payload:

- `bison.exe`, `flex.exe`, `flex++.exe`, `m4.exe`, `make.exe`, `funzip.exe` are tracked and hash-checked, but should receive dedicated wrappers only when a concrete Suite workflow needs them.
