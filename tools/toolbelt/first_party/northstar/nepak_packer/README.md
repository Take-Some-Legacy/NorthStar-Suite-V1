# North Star NEPAK Manager

Clean `.nepak` VFS package manager.

Commands:

```text
pack
inspect
manifest
list
verify
extract
mount-test
diff
version
accepted-inputs
doctor
```

Format rules:

```text
.nepak = VFS package only
NEF8/ListFile = semantic asset dictionaries
AssetManager = bytes/ranges/streams only
Domain gateways = meaning
Writer = explicit assets.container.nepak.writer capability
```
