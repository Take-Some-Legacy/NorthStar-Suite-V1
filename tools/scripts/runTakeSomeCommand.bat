@echo off
rem Shared Take Some command launcher.
rem Usage:
rem   call tools\scripts\runTakeSomeCommand.bat "action" "summary" "details" -- <takesome command args...>
setlocal EnableExtensions
chcp 65001 >nul

set "NE_RUN_SCRIPT_DIR=%~dp0"
for %%I in ("%NE_RUN_SCRIPT_DIR%.") do set "NE_RUN_SCRIPT_DIR=%%~fI"
for %%I in ("%NE_RUN_SCRIPT_DIR%\..\..") do set "NE_RUN_REPO_ROOT=%%~fI"
set "NE_RUN_REQUIRE=%NE_RUN_SCRIPT_DIR%\requireScriptEnv.bat"
set "NE_RUN_FINISH=%NE_RUN_SCRIPT_DIR%\finishConsole.bat"

set "NE_RUN_ACTION=%~1"
set "NE_RUN_SUMMARY=%~2"
set "NE_RUN_DETAILS=%~3"
if not defined NE_RUN_ACTION set "NE_RUN_ACTION=Take Some command"
if not defined NE_RUN_SUMMARY set "NE_RUN_SUMMARY=Command finished."

shift
shift
shift
if "%~1"=="--" shift

set NE_RUN_ARGS=
:collect_args
if "%~1"=="" goto validate_shared_scripts
rem Do not caret-escape quotes into the collected argument string.
rem The previous form produced literal arguments such as ^menu on cmd.exe.
rem Each remaining argument is re-quoted once when it is appended, which keeps
rem paths with spaces intact without leaking caret characters to argparse.
set NE_RUN_ARGS=%NE_RUN_ARGS% "%~1"
shift
goto collect_args

:validate_shared_scripts
if not exist "%NE_RUN_REQUIRE%" (
  echo.
  echo [ERROR] Shared launcher is damaged: Script Env guard is missing.
  echo [PATH] Expected guard: %NE_RUN_REQUIRE%
  echo [PATH] Launcher dir: %NE_RUN_SCRIPT_DIR%
  echo [PATH] Workspace guess: %NE_RUN_REPO_ROOT%
  echo [RESULT] Command did not start.
  call :pause_before_exit
  exit /b 90
)

if not exist "%NE_RUN_FINISH%" (
  echo.
  echo [ERROR] Shared launcher is damaged: console footer is missing.
  echo [PATH] Expected footer: %NE_RUN_FINISH%
  echo [PATH] Launcher dir: %NE_RUN_SCRIPT_DIR%
  echo [PATH] Workspace guess: %NE_RUN_REPO_ROOT%
  echo [RESULT] Command did not start.
  call :pause_before_exit
  exit /b 91
)

set "NEWENGINE_CONSOLE_OWNS_PAUSE=1"
call "%NE_RUN_REQUIRE%"
set "NE_RUN_EXIT=%ERRORLEVEL%"
if not "%NE_RUN_EXIT%"=="0" (
  call "%NE_RUN_FINISH%" "%NE_RUN_ACTION%" "%NE_RUN_EXIT%" "Command did not start because Script Env is invalid." "Open suite.bat once; it initializes Script Env automatically, then retry."
  exit /b %NE_RUN_EXIT%
)

%NEWENGINE_PYTHON_CMD% "%NEWENGINE_SCRIPT_ROOT%\takesome.py" %NE_RUN_ARGS%
set "NE_RUN_EXIT=%ERRORLEVEL%"
call "%NE_RUN_FINISH%" "%NE_RUN_ACTION%" "%NE_RUN_EXIT%" "%NE_RUN_SUMMARY%" "%NE_RUN_DETAILS%"
exit /b %NE_RUN_EXIT%

:pause_before_exit
if defined CI exit /b 0
if "%NEWENGINE_NO_PAUSE%"=="1" exit /b 0
echo.
echo [EXIT] Press any key to close this console...
pause >nul
exit /b 0
