# North Star DDS Info

First-party source-owned DDS metadata inspector built from `tools/toolsSrc/ddsinfo`.

`bin/ddsinfo.exe` is a real host executable. It does not hardcode the implementation path: pass `--library <path>` or set `NORTHSTAR_DDSINFO_LIBRARY`. The managed implementation `northstar.ddsinfo.dll` lives in shared `tools/toolbelt/libraries`.

This stability build parses DDS headers directly and does not require Tao.DevIl, RSN.Base, ILMerge, or native DevIL.dll at runtime.

