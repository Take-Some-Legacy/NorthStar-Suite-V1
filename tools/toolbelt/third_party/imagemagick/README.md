# ImageMagick CLI

Descriptor package for ImageMagick `magick` CLI inside TakeSomeDevSuite.

## Location

```text
tools/toolbelt/third_party/imagemagick/
```

## Executable resolution

The descriptor runs:

```text
tools/toolbelt/third_party/imagemagick/bin/magick.cmd
```

The launcher resolves ImageMagick in this order:

1. `tools/toolbelt/third_party/imagemagick/bin/magick.exe`
2. `magick.exe` from `PATH`
3. `C:\Program Files\ImageMagick-*\magick.exe`
4. `C:\Program Files (x86)\ImageMagick-*\magick.exe`

## Vendored layout

```text
tools/toolbelt/third_party/imagemagick/
  tool.json
  README.md
  USAGE.txt
  bin/
    magick.cmd
    magick.exe
```

`magick.exe` is not committed by this adapter. Drop the vendor executable into `bin/` or install ImageMagick globally.

## Suite commands

- `image-identify`
- `image-identify-verbose`
- `image-convert`
- `image-strip-convert`
- `image-resize-fit`
- `image-thumbnail`

## Safety

This descriptor does not expose raw shell execution. Arguments are passed through the Suite descriptor runner as argv tokens.

Keep `safe_to_auto_run` disabled for arbitrary user-provided image files unless a higher-level image wrapper adds extension, pixel-count, file-size and timeout limits.
