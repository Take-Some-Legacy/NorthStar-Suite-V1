@echo off
setlocal EnableExtensions
title NorthStar LLM Pilot - Heartbeat
rem North Star Suite Intelligence / LLM Pilot heartbeat window.
rem Shows operational status, not private chain-of-thought.
rem Anchored to this launcher so elevated consoles cannot fall back to System32.

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
for %%I in ("%ROOT%\..\TakeSomeWebsite") do set "WORKSPACE_ROOT=%%~fI"
set "VIEWER=%ROOT%\tools\scripts\llm_pilot_console.py"
set "WORKSPACE_CONFIG=%ROOT%\config\suite\workspace.v1.json"

set "NEWENGINE_SUITE_ROOT=%ROOT%"
set "TAKESOME_SUITE_ROOT=%ROOT%"
set "NORTHSTAR_SUITE_ROOT=%ROOT%"
set "NORTHSTAR_TOOL_ROOT=%ROOT%"
set "NORTHSTAR_SUITE_TOOL_ROOT=%ROOT%"
set "TAKESOME_TOOL_ROOT=%ROOT%"
set "NORTHSTAR_WORKSPACE_ROOT=%WORKSPACE_ROOT%"
set "NORTHSTAR_SUITE_WORKSPACE_ROOT=%WORKSPACE_ROOT%"
set "TAKESOME_WORKSPACE_ROOT=%WORKSPACE_ROOT%"
set "NORTHSTAR_SUITE_WORKSPACE_CONFIG=%WORKSPACE_CONFIG%"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3"
  goto :python_found
)

where python >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_EXE=python"
  set "PYTHON_ARGS="
  goto :python_found
)

echo [ERROR] Python was not found. Install Python or enable the Windows Python Launcher.
pause
exit /b 2

:python_found
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NORTHSTAR_SUITE_STDIO_ENCODING=utf-8"
set "NORTHSTAR_SUITE_STDIO_ERRORS=replace"
set "NOESIS_SUITE_WRITE_ENABLED=1"

if not exist "%VIEWER%" (
  echo [ERROR] Missing tools\scripts\llm_pilot_console.py
  echo [PATH] ROOT=%ROOT%
  echo [PATH] VIEWER=%VIEWER%
  pause
  exit /b 2
)

pushd "%ROOT%" >nul
if errorlevel 1 (
  echo [ERROR] Failed to enter Suite root: %ROOT%
  pause
  exit /b 2
)

echo [INFO] NorthStar LLM Pilot heartbeat console started.
echo [INFO] Root: %ROOT%
echo [INFO] Workspace: %WORKSPACE_ROOT%
echo [INFO] Viewer: %VIEWER%
echo.
%PYTHON_EXE% %PYTHON_ARGS% "%VIEWER%" --root "%WORKSPACE_ROOT%" --workspace-config "%WORKSPACE_CONFIG%" --interval 5
set "RC=%errorlevel%"
popd >nul

echo.
echo [INFO] LLM Pilot heartbeat console stopped with exit code %RC%.
echo [INFO] Press Enter to close this window...
pause >nul
exit /b %RC%
