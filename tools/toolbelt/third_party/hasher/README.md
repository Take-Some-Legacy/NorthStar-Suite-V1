# Hasher

Third-party execute-ready workspace utility for hashing name lists and optionally matching a supplied hash code.

This package is intentionally neutral: it is not bound to any specific game, engine domain, or project. It is a generic workspace/content-pipeline helper exposed through the North Star Toolbelt.

## Expected layout

```text
tools/toolbelt/third_party/hasher/
  tool.json
  README.md
  USAGE.txt
  bin/
    hasher.exe
```

The executable is intentionally stored inside this tool package so the Suite can discover the complete tool from `tool.json` recursively without hardcoding it.

## Input format

The input `filename` is a text file containing one name per line.

## Usage

```bat
hasher.exe [-stripext] [-literal] filename [hashcode]
```

Arguments/options:

```text
-stripext
    Strip file extensions from each input name before hashing.

-literal
    Treat input names literally.

filename
    Text file containing one name per line.

hashcode
    Optional hexadecimal hash code to match against the names.
```

## Examples

Hash every name in a list:

```bat
.\bin\hasher.exe names.txt
```

Hash names after stripping extensions:

```bat
.\bin\hasher.exe -stripext names.txt
```

Match a known hex hash:

```bat
.\bin\hasher.exe names.txt DEADBEEF
```

Literal mode:

```bat
.\bin\hasher.exe -literal names.txt
```

## Suite integration

The Suite should discover this package recursively through `tool.json`. It should not add a bespoke Python command for this tool unless a higher-level workflow needs additional validation or structured output.

Generic runner shape:

```bat
python tools\scripts\takesome.py tools run vendor.hasher -- names.txt
```

## Safety notes

- Treat as a third-party workspace/content-pipeline tool.
- Do not load it from engine runtime code.
- Do not add it as a plugin.
- Use explicit argument arrays; avoid shell expansion.
- Input is a text list; prefer generated lists under `.takesome/` or explicit diagnostics directories.
