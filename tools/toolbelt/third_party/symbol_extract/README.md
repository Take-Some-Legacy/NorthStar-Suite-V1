# Symbol Extract

Third-party execute-ready workspace tool for extracting or listing symbols from executable/debug-symbol inputs.

This package is intentionally neutral: it is not bound to any specific game, engine domain, or project. It is a generic workspace/debugging helper exposed through the North Star Toolbelt.

## Expected layout

```text
tools/toolbelt/third_party/symbol_extract/
  tool.json
  README.md
  USAGE.txt
  bin/
    SymbolExtract.exe
```

The executable is intentionally stored inside this tool package so the Suite can discover the complete tool from `tool.json` recursively without hardcoding it.

## Usage

```bat
SymbolExtract.exe [options]
```

Options:

```text
-in[:type] filename
    Specify an input file. The input may be an executable or debug-symbol file.

-out filename
    Write output to the specified file instead of stdout.

-exclude substring
    Exclude symbols containing the specified substring.

-searchpath path
    Specify the symbol search path when loading an executable.
```

## Examples

Print symbols to stdout:

```bat
.\bin\SymbolExtract.exe -in example.exe
```

Write symbols to a file:

```bat
.\bin\SymbolExtract.exe -in example.exe -out symbols.txt
```

Exclude noisy symbols:

```bat
.\bin\SymbolExtract.exe -in example.exe -exclude std:: -out symbols.filtered.txt
```

Use a symbol search path:

```bat
.\bin\SymbolExtract.exe -in example.exe -searchpath C:\Symbols -out symbols.txt
```

## Suite integration

The Suite should discover this package recursively through `tool.json`. It should not add a bespoke Python command for this tool unless a higher-level workflow needs additional validation or structured output.

Generic runner shape:

```bat
python tools\scripts\takesome.py tools run vendor.symbol_extract -- -in example.exe -out symbols.txt
```

## Safety notes

- Treat as a third-party workspace/debug tool.
- Do not load it from engine runtime code.
- Do not add it as a plugin.
- Use explicit argument arrays; avoid shell expansion.
- Prefer output files under `.takesome/` or an explicit diagnostics directory.
