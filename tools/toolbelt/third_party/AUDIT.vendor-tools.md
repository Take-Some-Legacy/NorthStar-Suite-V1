# Third-party Vendor Tool Audit

> [!INFO] INFO BLOCK — текущее положение дел
> **У нас сейчас:** `tools/toolbelt/third_party` содержит active third-party descriptors, включая legacy GNUWin32 family. Этот файл фиксирует текущий inventory перед заменой GNUWin32 provider family.
>
> **Technical details (EN):** generated_by=`third_party_vendor_inventory_lock`; audit_date=`2026-06-05`; scope=`tools/toolbelt/third_party/*/tool.json`.

> [!WARN] WARN BLOCK — legacy vendor family
> **У нас сейчас:** `vendor.gnuwin32.*` — legacy provider family. Бинарники слишком старые для build/tooling trust и должны быть заменены pinned MSYS2 UCRT64 package drop или self-built mingw-w64 artifacts.
>
> **Почему это важно:** случайный exe-drop ломает воспроизводимость, provenance, risk-tier reasoning и CI diagnostics.
>
> **Technical details (EN):** descriptor migration must use `VENDOR.lock.json`, exact binary SHA256, exact package/source SHA256, license files, and smoke validation commands.

## Replacement source policy

```text
preferred: pinned MSYS2 UCRT64 package artifacts
allowed:   self-built mingw-w64 artifacts with reproducible build notes
forbidden: mixed random exe drops without package/source lock
```

## Candidate source notes checked on 2026-06-05

- `diffutils`: MSYS2 UCRT64 mingw-w64-ucrt-x86_64-diffutils 3.12-1; package SHA256 f0033790863d3457681c32e081cf83269d9da8735721907912cab342d720708c
- `grep`: MSYS2 UCRT64 mingw-w64-ucrt-x86_64-grep 3.12-1; package SHA256 a075f567fac39fc3a88e2a744c4fe4d30b4882951c9d8f5fce8f680c9c157703
- `sed`: MSYS2 UCRT64 has sed 4.9-1, while external ecosystem tracks 4.10; treat as candidate review, not final lock.
- `make`: MSYS2 UCRT64 mingw-w64-ucrt-x86_64-make 4.4.1-4; package SHA256 f62658c065961207168416e1286c896980cd1001514b1c372b2c9cfe4b61fb9a

## Current inventory lock

| Descriptor | Version field | Version probe | Exe | Size | SHA256 | Runtime files | Legacy |
|---|---:|---|---|---:|---|---|---|
| `vendor.gnuwin32.bison` | `2.4.1-gnuwin32` | `bison (GNU Bison) 2.4.1 / Written by Robert Corbett and Richard Stallman.` | `bin/bison.exe` | 279552 | `f9a7f0c61719ada0590792c3a7afd252888091e1a2e3fa98b096e24102f4cbfb` | bin/bison.exe<br/>bin/libiconv2.dll<br/>bin/libintl3.dll | YES |
| `vendor.ddsinfo` | `1.0.0` | `ddsinfo [options] <paths>` | `bin/ddsinfo.exe` | 122880 | `650673524142434da0d230a1c01c258affe4355c3de2e6dfc7a2270eb2f0cd47` | bin/DevIL.dll<br/>bin/ddsinfo.exe | no |
| `vendor.gnuwin32.diff3` | `2.8.7-gnuwin32` | `diff3 (GNU diffutils) 2.8.7 / Written by Randy Smith.` | `bin/diff3.exe` | 59392 | `d770ac96fa4fabc42a2da04f897febf07c6794e4a6d5e4c1b64f23b039916cf8` | bin/diff3.exe<br/>bin/libiconv2.dll<br/>bin/libintl3.dll | YES |
| `vendor.gnuwin32.diff` | `2.8.7-gnuwin32` | `diff (GNU diffutils) 2.8.7 / Written by Paul Eggert, Mike Haertel, David Hayes, / Richard Stallman, and Len Tower.` | `bin/diff.exe` | 150528 | `f449ce40db50dd35c45c3dfa54bc79b6a3a4d9dc5ab0ff4d0fe91a4c9fefa310` | bin/diff.exe<br/>bin/libiconv2.dll<br/>bin/libintl3.dll | YES |
| `vendor.gnuwin32.fgrep` | `2.5.4-gnuwin32` | `GNU grep 2.5.3 / Copyright (C) 1988, 1992-2002, 2004, 2005  Free Software Foundation, Inc.` | `bin/fgrep.exe` | 55296 | `a3936f34f15a7debcca2d02807bee120922de3169c42adf129c46bc29661e492` | bin/fgrep.exe<br/>bin/libiconv2.dll<br/>bin/libintl3.dll | YES |
| `vendor.gnuwin32.flex` | `2.5.4-gnuwin32` | `C:\Users\Aiden\Documents\Take Some\NorthStar-Engine\tools\toolbelt\third_party\flex\bin/flex.exe version 2.5.4` | `bin/flex.exe` | 170496 | `5f985f95c4c02e31aa130149d1b8174000de82d9739f26375fcbf6215b6c6af7` | bin/flex.exe | YES |
| `vendor.gnuwin32.flexpp` | `2.5.4-gnuwin32` | `C:\Users\Aiden\Documents\Take Some\NorthStar-Engine\tools\toolbelt\third_party\flexpp\bin/flex++.exe version 2.5.4` | `bin/flex++.exe` | 170496 | `5f985f95c4c02e31aa130149d1b8174000de82d9739f26375fcbf6215b6c6af7` | bin/flex++.exe | YES |
| `vendor.gnuwin32.funzip` | `5.51-gnuwin32` | `fUnZip (filter UnZip), version 3.94 of 17 February 2002 / usage: ... / funzip [-password] / ... / ... / funzip [-password] > outfile` | `bin/funzip.exe` | 24576 | `4cc730d499facea248ed155098a1ac0489ebb30e8d4904ed6e494f64bec2a15b` | bin/funzip.exe | YES |
| `vendor.gnuwin32.m4` | `1.4.13-gnuwin32` | `m4 (GNU M4) 1.4.13 / Copyright (C) 2009 Free Software Foundation, Inc. / License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.` | `bin/m4.exe` | 179200 | `f5caf93e4d101722a7d58f30b5e69acada6aea59fb639eee1173f341a3896645` | bin/m4.exe<br/>bin/regex2.dll | YES |
| `vendor.gnuwin32.make` | `3.81-gnuwin32` | `GNU Make 3.81 / Copyright (C) 2006  Free Software Foundation, Inc. / This is free software; see the source for copying conditions.` | `bin/make.exe` | 175104 | `19e41b7f9b99773b5c6f2b93426cc525f6b63c461cc034a17f6b6263d8d54557` | bin/libiconv2.dll<br/>bin/libintl3.dll<br/>bin/make.exe | YES |
| `vendor.gnuwin32.sdiff` | `2.8.7-gnuwin32` | `sdiff (GNU diffutils) 2.8.7 / Written by Thomas Lord.` | `bin/sdiff.exe` | 61952 | `e471e4063ac7771ab642483b8566d62a611d64dae53cd61782e10088a196a252` | bin/diff.exe<br/>bin/libiconv2.dll<br/>bin/libintl3.dll<br/>bin/sdiff.exe | YES |
| `vendor.gnuwin32.sed` | `4.2.1-gnuwin32` | `GNU sed version 4.2.1 / Copyright (C) 2009 Free Software Foundation, Inc. / This is free software; see the source for copying conditions.  There is NO` | `bin/sed.exe` | 77824 | `5c2e7c4e79b2af04f09ddec2b01bc68de99761a149e90a37319f515682843116` | bin/libiconv2.dll<br/>bin/libintl3.dll<br/>bin/regex2.dll<br/>bin/sed.exe | YES |
| `vendor.gnuwin32.tail` | `5.3.0-gnuwin32` | `tail (GNU coreutils) 5.3.0 / Written by Paul Rubin, David MacKenzie, Ian Lance Taylor, and Jim Meyering.` | `bin/tail.exe` | 88064 | `9d62a3482efe6e11de2878ba3002546eae690fe23985e8492c7f6895fb3a2984` | bin/libiconv2.dll<br/>bin/libintl3.dll<br/>bin/tail.exe | YES |
| `vendor.gnuwin32.tar` | `1.13-gnuwin32` | `tar (GNU tar) 1.13 / Copyright (C) 1988, 92,93,94,95,96,97,98, 1999 Free Software Foundation, Inc.` | `bin/tar.exe` | 167424 | `7384e3c6b76126358166f382e6790aefd55ab36eab781ce5b06b7f2d979b1095` | bin/libiconv-2.dll<br/>bin/libintl-2.dll<br/>bin/tar.exe | YES |
| `vendor.gnuwin32.touch` | `5.3.0-gnuwin32` | `touch (GNU coreutils) 5.3.0 / Written by Paul Rubin, Arnold Robbins, Jim Kingdon, David MacKenzie, and Randy Smith.` | `bin/touch.exe` | 78848 | `c6627232409107b3db5096eaf7dc11b27f34b2fc53df3a3a8394c5e1e093fc00` | bin/libiconv2.dll<br/>bin/libintl3.dll<br/>bin/touch.exe | YES |

## Drift findings

- `vendor.gnuwin32.fgrep`: descriptor says `2.5.4-gnuwin32`, executable reports `GNU grep 2.5.3`.
- `vendor.ddsinfo`: descriptor says `1.0.0`, executable reports `ddsinfo Version: 1.1.0.176`.
- Before this slice, several GNUWin32 `runtime_files` entries listed non-existing DLL variants; descriptors now list only files present in their local `bin/` directories.

## Local MSYS2 probe

> [!NOTE] NOTE BLOCK — local candidate only
> **У нас сейчас:** на машине найден `C:\msys64`. Это можно использовать как источник кандидатов, но не как final active provider без package-level `VENDOR.lock.json`, package/source SHA256 и license/provenance notes.

| Tool | Path | Version probe | Size | SHA256 |
|---|---|---|---:|---|
| `grep` | `C:\msys64\usr\bin\grep.exe` | `grep (GNU grep) 3.0 / Copyright (C) 2017 Free Software Foundation, Inc. / License GPLv3+: GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.` | 213710 | `497202418334f8a48d9f34cd2e1b2c03c4f957e02304b613e10931c0457e8d4a` |
| `sed` | `C:\msys64\usr\bin\sed.exe` | `/usr/bin/sed (GNU sed) 4.9 / Copyright (C) 2022 Free Software Foundation, Inc. / License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.` | 178140 | `8d54e322dfc3faa60f0464691aba8634197406e53367aa8942409181c0808be8` |
| `tail` | `C:\msys64\usr\bin\tail.exe` | `tail (GNU coreutils) 8.32 / Copyright (C) 2020 Free Software Foundation, Inc. / License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.` | 56617 | `8608c4138642de6dca0806b266b3009c137dc373171978cf47418056a5e05c55` |
| `tar` | `C:\msys64\usr\bin\tar.exe` | `tar (GNU tar) 1.35 / Copyright (C) 2023 Free Software Foundation, Inc. / License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.` | 511486 | `df0582941d1f451a76337863ba1dc8d8986ad0faf44f0e5f5c34afeb43c36453` |
| `touch` | `C:\msys64\usr\bin\touch.exe` | `touch (GNU coreutils) 8.32 / Copyright (C) 2020 Free Software Foundation, Inc. / License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.` | 107463 | `1d895e0f77cbc8b77c3a38da009e8ad8d23a371afd398da5408bdeffcddf5fc0` |

## Migration acceptance

```text
P0C is complete only when:
  old vendor.gnuwin32.* descriptors are disabled or removed from active discovery
  new vendor.gnu.* or vendor.msys2.gnu.* descriptors are active
  every active vendor package has VENDOR.lock.json
  every --version/--help command is read-only and idempotent
  every executable hash/size matches descriptor
  smoke tests cover diff/grep/sed/tar/tail/touch
```
