# MSYS2 GNU coreutils toolbelt slice

> [!INFO] INFO BLOCK — текущее положение дел
> **У нас сейчас:** добавлен POSIX-core набор GNU coreutils как active third_party descriptors, pinned из локального `C:/msys64/usr/bin` и подключён к shared runtime `vendor.msys2.runtime.usr`.
>
> **Technical details (EN):** tools=12; version=8.32-msys2-usr; layout=`tools/toolbelt/third_party/<tool>/bin/<tool>.exe`.

| Tool | Version probe | Size | SHA256 |
|---|---|---:|---|
| `cat` | `cat (GNU coreutils) 8.32` | 38719 | `f1b37048ee5c70fdc31dde509e562261c9b2d102d94c903393f55b45e883ef90` |
| `head` | `head (GNU coreutils) 8.32` | 45413 | `c82ae2ef72235a34db7007580628cd5183cb350878a10fcc98b6ef26b92a3537` |
| `wc` | `wc (GNU coreutils) 8.32` | 47366 | `3ab05efc4703295f0d36fd48da17f2021219494fb932a062a535ae17ea9f45b3` |
| `sort` | `sort (GNU coreutils) 8.32` | 109591 | `7c5df851d821e23988641f35442a06652ce834ed724456511798ce60314cab9a` |
| `uniq` | `uniq (GNU coreutils) 8.32` | 45019 | `07e78095a79870b52ac988989faa5ff8446e1a8cdc861165d7eb93904fff5211` |
| `cut` | `cut (GNU coreutils) 8.32` | 45102 | `63fcfb76c80d57538312a9637429d5a4b99ac83e8b00d95684609b4c045471e9` |
| `tr` | `tr (GNU coreutils) 8.32` | 49460 | `7cf90be63820ba9ec66a10c0c4af84f0a2e3ec90a722ea6904219ec0b93bf1c1` |
| `tee` | `tee (GNU coreutils) 8.32` | 38794 | `5b956ac9d6bb6d457665709bbcf71326ecd66bb5111b280c124a68405ce5da46` |
| `basename` | `basename (GNU coreutils) 8.32` | 34883 | `6fe2e201a956304503f808d0909a26d9b49e1a7e99f6ee6d93721ac4a76a7c6e` |
| `dirname` | `dirname (GNU coreutils) 8.32` | 34830 | `53896fda354605a1a1d1f5e6802daba5ba6c05961f3074b892194e068aa82772` |
| `realpath` | `realpath (GNU coreutils) 8.32` | 49576 | `e780c23d5d6bf60d7e80e073586be5f4d7f91faa0a0d1f07b3088b5d710f8395` |
| `printf` | `printf (GNU coreutils) 8.32` | 72003 | `dbc52ee41a9d2fc4cdad6d690e430c6b630ce5fb5837d66d6b47cf59ea63b198` |

## Runtime additions

`sort.exe` requires the C++ runtime side of the MSYS2 usr stack, so the shared runtime lock now also includes:

```text
msys-gcc_s-seh-1.dll
msys-stdc++-6.dll
```

## Smoke coverage

Each package contains `test/test.bat` and validates:

```text
--version probe
shared runtime presence
one tool-specific command path
```
