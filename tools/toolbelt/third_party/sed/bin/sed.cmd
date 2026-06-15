@echo off
setlocal

set "TOOL_EXE=sed.exe"
set "FALLBACK_EXE="
set "FALLBACK_PREFIX="

if /I "%TOOL_EXE%"=="fgrep.exe" (
  set "FALLBACK_EXE=grep.exe"
  set "FALLBACK_PREFIX=-F"
)

if /I "%TOOL_EXE%"=="egrep.exe" (
  set "FALLBACK_EXE=grep.exe"
  set "FALLBACK_PREFIX=-E"
)

if /I "%TOOL_EXE%"=="awk.exe" (
  set "FALLBACK_EXE=gawk.exe"
)

if /I "%TOOL_EXE%"=="unxz.exe" (
  set "FALLBACK_EXE=xz.exe"
  set "FALLBACK_PREFIX=-d"
)

if /I "%TOOL_EXE%"=="unzstd.exe" (
  set "FALLBACK_EXE=zstd.exe"
  set "FALLBACK_PREFIX=-d"
)

if not "%TAKESOME_GNU_BIN%"=="" (
  if exist "%TAKESOME_GNU_BIN%\%TOOL_EXE%" (
    "%TAKESOME_GNU_BIN%\%TOOL_EXE%" %*
    exit /b %ERRORLEVEL%
  )
  if not "%FALLBACK_EXE%"=="" (
    if exist "%TAKESOME_GNU_BIN%\%FALLBACK_EXE%" (
      "%TAKESOME_GNU_BIN%\%FALLBACK_EXE%" %FALLBACK_PREFIX% %*
      exit /b %ERRORLEVEL%
    )
  )
)

for %%D in ("%ProgramFiles%\Git\usr\bin" "%ProgramFiles(x86)%\Git\usr\bin" "%LOCALAPPDATA%\Programs\Git\usr\bin" "C:\msys64\usr\bin" "C:\msys64\mingw64\bin" "C:\msys2\usr\bin") do (
  if exist "%%~D\%TOOL_EXE%" (
    "%%~D\%TOOL_EXE%" %*
    exit /b %ERRORLEVEL%
  )
  if not "%FALLBACK_EXE%"=="" (
    if exist "%%~D\%FALLBACK_EXE%" (
      "%%~D\%FALLBACK_EXE%" %FALLBACK_PREFIX% %*
      exit /b %ERRORLEVEL%
    )
  )
)

where %TOOL_EXE% >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  %TOOL_EXE% %*
  exit /b %ERRORLEVEL%
)

if not "%FALLBACK_EXE%"=="" (
  where %FALLBACK_EXE% >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    %FALLBACK_EXE% %FALLBACK_PREFIX% %*
    exit /b %ERRORLEVEL%
  )
)

echo Backend executable %TOOL_EXE% was not found. Install Git for Windows/MSYS2 or set TAKESOME_GNU_BIN. 1>&2
exit /b 9009