# NOESIS tools

Tool descriptors and source packages live under `tools/`, but runtime Python code does not.
Use the canonical command plane:

```bat
python -m noesis suite tools scan
python -m noesis suite tools validate
python -m noesis suite tools build --safe --validate-after-build
python -m noesis suite validate-build
```

`tools/scripts` is a forbidden runtime root and must not be recreated.
