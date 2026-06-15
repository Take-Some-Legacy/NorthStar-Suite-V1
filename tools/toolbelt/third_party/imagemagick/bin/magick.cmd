@echo off
setlocal

set "TOOL_DIR=%~dp0"
set "LOCAL_MAGICK=%TOOL_DIR%magick.exe"

if exist "%LOCAL_MAGICK%" (
  "%LOCAL_MAGICK%" %*
  exit /b %ERRORLEVEL%
)

where magick.exe >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  magick.exe %*
  exit /b %ERRORLEVEL%
)

for /d %%D in ("C:\Program Files\ImageMagick-*" "C:\Program Files (x86)\ImageMagick-*") do (
  if exist "%%~D\magick.exe" (
    "%%~D\magick.exe" %*
    exit /b %ERRORLEVEL%
  )
)

echo ImageMagick CLI was not found. Put magick.exe next to this launcher or install ImageMagick and expose magick.exe on PATH. 1>&2
exit /b 9009
