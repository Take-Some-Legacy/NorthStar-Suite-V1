# North Star Symbol Extract

First-party North Star workspace diagnostics tool for listing PE export symbols and COFF symbol-table names.

This replaces the vendor-provisional `SymbolExtract.exe` package with a Rust CLI that follows the first-party tool contract:

```text
--help
version
accepted-inputs
doctor
```

## Layout

```text
tools/toolbelt/first_party/northstar/symbol_extract/
  tool.json
  README.md
  USAGE.txt
  bin/
    northstar-symbol-extract.exe
  test/
    test.bat
  testData/
```

Source of truth:

```text
tools/toolsSrc/symbol_extract
```

## Usage

```bat
northstar-symbol-extract -in file.exe
northstar-symbol-extract -in file.dll -exclude std:: -out .takesome\symbols.txt
northstar-symbol-extract -in:exe file.exe -searchpath C:\Symbols -out symbols.txt
```

## Payload output

Extraction output is raw payload stdout and is safe to redirect:

```text
<name> 0x<RVA_HEX8> <source>
```

Example:

```text
CreateToolhelp32Snapshot 0x00001230 export
```

Payload output must not contain ANSI escapes or status tags.

## Status output

`accepted-inputs` and `doctor` use `northstar_cli::ansi` status helpers.

## Notes

The uploaded vendor executable was a .NET/DIA-based utility. The first-party version intentionally avoids bundling or invoking the vendor binary. Current implemented extraction covers PE exports and COFF symbol tables. `-searchpath` is accepted for CLI compatibility and reserved for a future PDB/DIA provider pass.
