# GNUWin32 diff

Third-party GNUWin32 `diff.exe` package.

This package is self-contained: executable payload and runtime DLL dependencies live inside this package's `bin/` directory.

```text
package root: tools/toolbelt/third_party/diff
bin:          tools/toolbelt/third_party/diff/bin/
entrypoint:   tools/toolbelt/third_party/diff/bin/diff.exe
```

## Rules

- Do not use a shared GNUWin32 bin directory.
- Do not add this executable to the global `PATH`.
- Do not call `diff.exe` directly from reusable engine/runtime code.
- Use Suite/script-plane wrappers for automated workspace workflows.
- Keep SHA-256 and byte size synchronized with `tool.json` when replacing the payload.

## Runtime files

```text
bin/diff.exe
bin/libiconv-2.dll
bin/libiconv2.dll
bin/libintl-2.dll
bin/libintl3.dll
bin/regex2.dll
```
