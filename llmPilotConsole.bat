@echo off
setlocal EnableExtensions
title NorthStar LLM Pilot - Heartbeat
rem North Star Suite Intelligence / LLM Pilot heartbeat window.
rem Shows operational status, not private chain-of-thought.

set "ROOT=%~dp0."
set "VIEWER=%ROOT%\tools\scripts\llm_pilot_console.py"

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

if not exist "%VIEWER%" (
  echo [ERROR] Missing tools\scripts\llm_pilot_console.py
  pause
  exit /b 2
)

echo [INFO] NorthStar LLM Pilot heartbeat console started.
echo [INFO] Root: %ROOT%
echo [INFO] Viewer: %VIEWER%
echo.
%PYTHON_EXE% %PYTHON_ARGS% "%VIEWER%" --root "%ROOT%" --interval 5
set "RC=%errorlevel%"
echo.
echo [INFO] LLM Pilot heartbeat console stopped with exit code %RC%.
echo [INFO] Press Enter to close this window...
pause >nul
exit /b %RC%
