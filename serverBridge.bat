@echo off
setlocal EnableExtensions
rem North Star / Take Some external Suite root hook.
rem The concrete path is owned by environment, not by this launcher.
if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"
if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"
if defined NEWENGINE_SUITE_ROOT if exist "%NEWENGINE_SUITE_ROOT%\script-env.cmd" call "%NEWENGINE_SUITE_ROOT%\script-env.cmd"
if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"
if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%" EnableDelayedExpansion
set "ROOT=%~dp0."
set "SUPERVISOR=%ROOT%\tools\scripts\ai_bridge_supervisor.py"

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

if not exist "%SUPERVISOR%" (
  echo [ERROR] Missing tools\scripts\ai_bridge_supervisor.py
  pause
  exit /b 2
)

%PYTHON_EXE% %PYTHON_ARGS% "%SUPERVISOR%" --root "%ROOT%" --write --prefer-named --setup-named -sudo
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" echo [ERROR] serverBridge stopped with exit code %RC%.
echo [INFO] Press Enter to close this window...
pause >nul
exit /b %RC%