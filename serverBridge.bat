@echo off
setlocal EnableExtensions
title NorthStar serverBridge - Operator Session
rem North Star / Take Some external Suite root hook.
rem Operator foreground bridge launcher.
rem This mode intentionally enables write/sudo for a controlled operator session.
rem It also opens a separate LLM Pilot Heartbeat console window.
rem
rem IMPORTANT: UAC/elevated Windows consoles often start in C:\Windows\System32.
rem Never derive Suite/tool roots from %CD%. Anchor them to this launcher file.

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
for %%I in ("%ROOT%\..\TakeSomeWebsite") do set "WORKSPACE_ROOT=%%~fI"
set "SUPERVISOR=%ROOT%\tools\scripts\ai_bridge_supervisor.py"
set "WORKSPACE_CONFIG=%ROOT%\config\suite\workspace.v1.json"
set "LLM_PILOT_CONSOLE=%ROOT%\llmPilotConsole.bat"

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

if exist "%ROOT%\script-env.cmd" call "%ROOT%\script-env.cmd"
if exist "%ROOT%\.takesome\script-env.cmd" call "%ROOT%\.takesome\script-env.cmd"

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
set "NORTHSTAR_BRIDGE_EXPOSURE_MODE=operator"
set "NOESIS_SUITE_WRITE_ENABLED=1"

if not exist "%SUPERVISOR%" (
  echo [ERROR] Missing tools\scripts\ai_bridge_supervisor.py
  echo [PATH] ROOT=%ROOT%
  echo [PATH] SUPERVISOR=%SUPERVISOR%
  pause
  exit /b 2
)

pushd "%ROOT%" >nul
if errorlevel 1 (
  echo [ERROR] Failed to enter Suite root: %ROOT%
  pause
  exit /b 2
)

if exist "%LLM_PILOT_CONSOLE%" (
  echo [INFO] Opening LLM Pilot heartbeat console...
  start "NorthStar LLM Pilot - Heartbeat" /D "%ROOT%" "%LLM_PILOT_CONSOLE%"
) else (
  echo [WARN] Missing llmPilotConsole.bat; heartbeat window skipped.
)

%PYTHON_EXE% %PYTHON_ARGS% "%SUPERVISOR%" --root "%WORKSPACE_ROOT%" --workspace-config "%WORKSPACE_CONFIG%" --write --prefer-named --setup-named -sudo
set "RC=%errorlevel%"
popd >nul

echo.
if not "%RC%"=="0" echo [ERROR] serverBridge stopped with exit code %RC%.
echo [INFO] Press Enter to close this window...
pause >nul
exit /b %RC%
