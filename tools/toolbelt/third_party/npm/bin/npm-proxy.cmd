@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "DEVSUITE_ROOT=%SCRIPT_DIR%..\..\..\..\.."
for %%I in ("%DEVSUITE_ROOT%") do set "DEVSUITE_ROOT=%%~fI"
for %%I in ("%DEVSUITE_ROOT%\..") do set "DOCS_ROOT=%%~fI"

set "NPM_EXE="
if exist "%ProgramFiles%\nodejs\npm.cmd" set "NPM_EXE=%ProgramFiles%\nodejs\npm.cmd"
if not defined NPM_EXE if exist "%ProgramFiles(x86)%\nodejs\npm.cmd" set "NPM_EXE=%ProgramFiles(x86)%\nodejs\npm.cmd"
if not defined NPM_EXE for %%I in (npm.cmd) do set "NPM_EXE=%%~$PATH:I"
if not defined NPM_EXE (
  echo npm was not found. Install Node.js or expose npm.cmd on PATH. 1>&2
  exit /b 9009
)

if "%~1"=="--devsuite-resolve-workspace" (
  if defined TAKESOME_WORKSPACE_ROOT if exist "%TAKESOME_WORKSPACE_ROOT%\package.json" echo package	%TAKESOME_WORKSPACE_ROOT%
  if defined NORTHSTAR_WORKSPACE_ROOT if exist "%NORTHSTAR_WORKSPACE_ROOT%\package.json" echo package	%NORTHSTAR_WORKSPACE_ROOT%
  if exist "%DOCS_ROOT%\TakeSomeWebsite\package.json" echo package	%DOCS_ROOT%\TakeSomeWebsite
  if exist "%CD%\package.json" echo package	%CD%
  if not exist "%CD%\package.json" echo no-package	%CD%
  exit /b 0
)

set "WORKSPACE="
if defined TAKESOME_WORKSPACE_ROOT if exist "%TAKESOME_WORKSPACE_ROOT%\package.json" set "WORKSPACE=%TAKESOME_WORKSPACE_ROOT%"
if not defined WORKSPACE if defined NORTHSTAR_WORKSPACE_ROOT if exist "%NORTHSTAR_WORKSPACE_ROOT%\package.json" set "WORKSPACE=%NORTHSTAR_WORKSPACE_ROOT%"
if not defined WORKSPACE if exist "%DOCS_ROOT%\TakeSomeWebsite\package.json" set "WORKSPACE=%DOCS_ROOT%\TakeSomeWebsite"
if not defined WORKSPACE if exist "%CD%\package.json" set "WORKSPACE=%CD%"

set "CMD0=%~1"
set "SCRIPT0=%~2"
set "NEEDS_WORKSPACE=0"
set "BUILDLIKE=0"
if /I "%CMD0%"=="run" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="install" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="ci" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="audit" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="outdated" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="update" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="exec" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="test" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="start" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="publish" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="pack" set "NEEDS_WORKSPACE=1"
if /I "%CMD0%"=="rebuild" set "NEEDS_WORKSPACE=1"

if /I "%CMD0%"=="run" if /I "%SCRIPT0%"=="build" set "BUILDLIKE=1"
if /I "%CMD0%"=="run" if /I "%SCRIPT0%"=="typecheck" set "BUILDLIKE=1"
if /I "%CMD0%"=="run" if /I "%SCRIPT0%"=="lint" set "BUILDLIKE=1"
if /I "%CMD0%"=="run" if /I "%SCRIPT0%"=="test" set "BUILDLIKE=1"
if /I "%CMD0%"=="run" if /I "%SCRIPT0%"=="check" set "BUILDLIKE=1"

set "LOG=%TEMP%\takesome-npm-%RANDOM%-%RANDOM%.log"

if "%NEEDS_WORKSPACE%"=="1" (
  if not defined WORKSPACE (
    echo npm workspace was not found. Set TAKESOME_WORKSPACE_ROOT or NORTHSTAR_WORKSPACE_ROOT. 1>&2
    exit /b 2
  )
  pushd "%WORKSPACE%" || exit /b 2
  call "%NPM_EXE%" %* > "%LOG%" 2>&1
  set "CODE=%ERRORLEVEL%"
  popd
) else (
  call "%NPM_EXE%" %* > "%LOG%" 2>&1
  set "CODE=%ERRORLEVEL%"
)

if exist "%LOG%" type "%LOG%"

if exist "%LOG%" findstr /I /C:"npm error" /C:"npm ERR!" /C:"ENOENT" /C:"Could not read package.json" /C:"Missing script:" "%LOG%" >nul 2>nul
if not errorlevel 1 set "CODE=1"

if "%BUILDLIKE%"=="1" (
  if exist "%LOG%" findstr /I /R /C:"error TS[0-9][0-9]*" /C:"Failed to compile" /C:"SyntaxError" /C:"TypeError" /C:"Cannot find module" /C:"RollupError" "%LOG%" >nul 2>nul
  if not errorlevel 1 set "CODE=1"
)

if exist "%LOG%" del /f /q "%LOG%" >nul 2>nul
exit /b %CODE%
