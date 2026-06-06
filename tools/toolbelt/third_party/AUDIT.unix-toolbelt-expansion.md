# UNIX toolbelt expansion audit

> [!INFO] INFO BLOCK — текущее положение дел
> **У нас сейчас:** добавлен следующий слой UNIX/toolbelt third_party tools: expanded coreutils subset, findutils, awk, compression tools, file/libmagic, patch, dos2unix/unix2dos where local vendor sources existed.
>
> **Technical details (EN):** added_tools=19; missing_local_sources=`jq`, `rg`, `fd`; shared_runtime=`tools/toolbelt/libraries`.

| Tool | Descriptor id | Version | Size | SHA256 |
|---|---|---:|---:|---|
| `ls` | `vendor.msys2.gnu.ls` | `8.32-msys2-usr` | 149479 | `b45981580702029cfeeffc8ca69e2a4d1e9c68914009e94c31ffec9cbc544aa5` |
| `mkdir` | `vendor.msys2.gnu.mkdir` | `8.32-msys2-usr` | 71435 | `fc9b9e49fd6496cdddfc5681208d74bd649ac934818eafdfd50a9571bdcb4861` |
| `cp` | `vendor.msys2.gnu.cp` | `8.32-msys2-usr` | 114653 | `5f91e0b445edb4e4c17e9a660ac29239f6cac5a821a173a86d4332b9eaa8cea3` |
| `mv` | `vendor.msys2.gnu.mv` | `8.32-msys2-usr` | 122430 | `0e990f9314e17eaf2eed168561313e0b6e1d21daf8fb6400387026c6da7277a1` |
| `rm` | `vendor.msys2.gnu.rm` | `8.32-msys2-usr` | 63813 | `a845f7517a49b49726e056da8a8f65a6d9ce96fbe79c3664c082521eea0f80e7` |
| `find` | `vendor.msys2.gnu.find` | `4.10.0-msys2-usr` | 341437 | `e198602f4b8dadb8a6fa78899cb8ded460a63778bbedf7700985b24dd48031b4` |
| `xargs` | `vendor.msys2.gnu.xargs` | `4.10.0-msys2-usr` | 78321 | `cac1d603d48ece8d86301d9e0f9f3f3eb6a1a9864a39a9524fe76a3e5f5c76cb` |
| `gawk` | `vendor.msys2.gnu.gawk` | `5.3.2-msys2-usr` | 779620 | `4c134a5fb53875692c9422ab068380923e04ea6d4a767d3fbfd8c66cd747bb16` |
| `awk` | `vendor.msys2.gnu.awk` | `5.3.2-msys2-usr` | 779620 | `4c134a5fb53875692c9422ab068380923e04ea6d4a767d3fbfd8c66cd747bb16` |
| `gzip` | `vendor.msys2.gnu.gzip` | `1.14-msys2-usr` | 122010 | `b30df4d89223e1477df01f48e70739e9a13fae0e8f753c7b2a99a990de3514dc` |
| `bzip2` | `vendor.msys2.gnu.bzip2` | `1.0.8-msys2-usr` | 92176 | `ac027e648f7d4bb8172d13a1bc27ac71784d193109aa48e76eff703aeb0f520d` |
| `xz` | `vendor.msys2.gnu.xz` | `5.8.1-msys2-usr` | 88564 | `c0cf02bce8a9421fb673778154084c6786922fd4afff3d95abd329ad6c3a6ab0` |
| `unxz` | `vendor.msys2.gnu.unxz` | `5.8.1-msys2-usr` | 88564 | `c0cf02bce8a9421fb673778154084c6786922fd4afff3d95abd329ad6c3a6ab0` |
| `zstd` | `vendor.msys2.gnu.zstd` | `1.5.7-msys2-usr` | 183522 | `04c6eb1d476680ccab7107a8f9d1709de500346dbef3a217acd7ea98a825be0f` |
| `unzstd` | `vendor.msys2.gnu.unzstd` | `1.5.7-msys2-usr` | 183522 | `04c6eb1d476680ccab7107a8f9d1709de500346dbef3a217acd7ea98a825be0f` |
| `file` | `vendor.msys2.gnu.file` | `5.46-msys2-usr` | 24225 | `6e20e8a0a681a46ef2c6e87c67502754fa2df7dd6da907b4e4720623f7c4b163` |
| `patch` | `vendor.gitforwindows.gnu.patch` | `2.7.6-gitforwindows-usr` | 180553 | `5f02c3c167f715247a19007dac691cd90b5752b55d0269d7b82c6e5aa0ffee6f` |
| `dos2unix` | `vendor.gitforwindows.dos2unix` | `7.5.2-gitforwindows-usr` | 53862 | `6c99bf555cef6f00bf38fcb96932a4cebd20bdf057d79028a22d986a23b1212c` |
| `unix2dos` | `vendor.gitforwindows.unix2dos` | `7.5.2-gitforwindows-usr` | 53862 | `e2b5ada1f7434022e8e65a668ff831b564372f5c762a07c84c0ca23fd8dc4998` |

## Missing local vendor sources

```text
jq
rg
fd
```
