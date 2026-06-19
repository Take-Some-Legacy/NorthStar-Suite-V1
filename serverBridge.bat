@echo off
setlocal EnableExtensions
chcp 65001 >nul
title NOESIS Suite - Operator Bridge
for %%I in ("%~dp0.") do set "NOESIS_ROOT=%%~fI"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NOESIS_RUNTIME_CONFIG=%NOESIS_ROOT%\config\noesis\runtime.v1.json"
rem Keep the NOESIS package importable for supervisor subprocesses that run from the workspace root.
if defined PYTHONPATH (
  set "PYTHONPATH=%NOESIS_ROOT%;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%NOESIS_ROOT%"
)
where py >nul 2>nul
if not errorlevel 1 (
  set "NOESIS_PY=py -3"
) else (
  set "NOESIS_PY=python"
)
pushd "%NOESIS_ROOT%" >nul
%NOESIS_PY% -m noesis supervisor --workspace-config "%NOESIS_RUNTIME_CONFIG%" --prefer-named %*
set "NOESIS_EXIT=%ERRORLEVEL%"
popd >nul
exit /b %NOESIS_EXIT%
