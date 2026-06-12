@echo off

setlocal EnableExtensions
title NorthStar serverBridge - Operator Session

rem North Star / Take Some external Suite root hook.

rem Operator foreground bridge launcher.

rem This mode intentionally enables write/sudo for a controlled operator session.

rem It also opens a separate LLM Pilot Heartbeat console window.



if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"

if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"

if defined NEWENGINE_SUITE_ROOT if exist "%NEWENGINE_SUITE_ROOT%\script-env.cmd" call "%NEWENGINE_SUITE_ROOT%\script-env.cmd"

if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"

if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"



set "ROOT=%~dp0."

set "SUPERVISOR=%ROOT%\tools\scripts\ai_bridge_supervisor.py"
set "WORKSPACE_CONFIG=%ROOT%\config\suite\workspace.v1.json"

set "LLM_PILOT_CONSOLE=%ROOT%\llmPilotConsole.bat"



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

rem Site/operator worker defaults are owned by config\suite\workspace.v1.json.
rem Operators may still override them through environment variables before launching.




if not exist "%SUPERVISOR%" (

  echo [ERROR] Missing tools\scripts\ai_bridge_supervisor.py

  pause

  exit /b 2

)



if exist "%LLM_PILOT_CONSOLE%" (
  echo [INFO] Opening LLM Pilot heartbeat console...
  start "NorthStar LLM Pilot - Heartbeat" /D "%ROOT%" "%LLM_PILOT_CONSOLE%"
) else (
  echo [WARN] Missing llmPilotConsole.bat; heartbeat window skipped.
)

%PYTHON_EXE% %PYTHON_ARGS% "%SUPERVISOR%" --root ..\TakeSomeWebsite --workspace-config "%WORKSPACE_CONFIG%" --write --prefer-named --setup-named -sudo

set "RC=%errorlevel%"

echo.

if not "%RC%"=="0" echo [ERROR] serverBridge stopped with exit code %RC%.

echo [INFO] Press Enter to close this window...

pause >nul

exit /b %RC%

