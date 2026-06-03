# North Star NEPAK Packer

First-party `.nepak` VFS package tool.

`.nepak` is a package/container layer for groups of runtime assets. It is intentionally separate from NEF8 ListFile assets such as `.ydd`, `.ytd`, `.ytyp`, `.nemat`, and `.neui`.

## Commands

```bat
northstar-nepak-packer pack -i assets/runtime -o builds/runtime.nepak
northstar-nepak-packer inspect -i builds/runtime.nepak
northstar-nepak-packer validate -i builds/runtime.nepak
northstar-nepak-packer extract -i builds/runtime.nepak -o .takesome/extract/nepak --overwrite
```

## Format slice

```text
magic       = NEPK
version     = 1
layout      = header + entry table + string table + payloads
payload     = raw or deflate
integrity   = BLAKE3 per unpacked entry
paths       = normalized VFS package paths
```
