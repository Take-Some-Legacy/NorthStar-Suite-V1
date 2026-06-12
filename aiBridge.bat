@echo off

setlocal EnableExtensions
rem North Star / Take Some external Suite root hook.
rem The concrete path is owned by environment, not by this launcher.
if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"
if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"
if defined NEWENGINE_SUITE_ROOT if exist "%NEWENGINE_SUITE_ROOT%\script-env.cmd" call "%NEWENGINE_SUITE_ROOT%\script-env.cmd"
if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"
if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"

chcp 65001 >nul



set "ROOT=%~dp0."

set "BRIDGE=%ROOT%\tools\scripts\northstar_ai_bridge.py"
set "SUPERVISOR=%ROOT%\tools\scripts\ai_bridge_supervisor.py"
set "WORKSPACE_CONFIG=%ROOT%\config\suite\workspace.v1.json"

set "PYTHON_EXE="

set "PYTHON_ARGS="



where py >nul 2>nul

if not errorlevel 1 (

  set "PYTHON_EXE=py"

  set "PYTHON_ARGS=-3"

  goto :python_found

)



where python >nul 2>nul

if not errorlevel 1 (

  set "PYTHON_EXE=python"

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



rem Write policy is owned by config\suite\ai_bridge.v1.json forceWrite.
rem Explicit read mode remains the hard override: aiBridge.bat read status

if /I "%~1"=="read" (

  set "NORTHSTAR_AI_BRIDGE_READ_ONLY=1"

  set "NORTHSTAR_AI_BRIDGE_WRITE=0"

  shift

) else (

  set "NORTHSTAR_AI_BRIDGE_READ_ONLY="

  set "NORTHSTAR_AI_BRIDGE_WRITE="

)



if not exist "%BRIDGE%" (

  echo [ERROR] Missing tools\scripts\northstar_ai_bridge.py

  pause

  exit /b 2

)



if /I "%~1"=="tunnel" (
  if not exist "%SUPERVISOR%" (
    echo [ERROR] Missing tools\scripts\ai_bridge_supervisor.py
    pause
    exit /b 2
  )
  shift
  %PYTHON_EXE% %PYTHON_ARGS% "%SUPERVISOR%" --workspace-config "%WORKSPACE_CONFIG%" --write --prefer-named --setup-named %*
  exit /b %errorlevel%
)

if "%~1"=="" (

  %PYTHON_EXE% %PYTHON_ARGS% "%BRIDGE%" --workspace-config "%WORKSPACE_CONFIG%" --hello

  exit /b %errorlevel%

)



%PYTHON_EXE% %PYTHON_ARGS% "%BRIDGE%" --workspace-config "%WORKSPACE_CONFIG%" %*

exit /b %errorlevel%

