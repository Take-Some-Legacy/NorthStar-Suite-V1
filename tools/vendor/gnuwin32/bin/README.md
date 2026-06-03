# GNUWin32 binary payload directory

This directory contains quarantined third-party GNUWin32 executables and DLLs used by Suite wrappers.

Current expected payload is listed in `../HASHES.sha256.txt`.

Run:

```bat
python tools\scripts\takesome.py vendor-gnuwin32-doctor
```

to validate file presence and SHA-256 hashes.
