@echo off
rem Shared console completion footer for North Star / Take Some launchers.
rem User-facing launchers call this exactly once before returning so a
rem double-clicked console never disappears without a readable result summary.
setlocal EnableExtensions
chcp 65001 >nul

set "NE_DONE_ACTION=%~1"
set "NE_DONE_EXIT=%~2"
set "NE_DONE_RESULT=%~3"
set "NE_DONE_OUTPUT=%~4"
if not defined NE_DONE_ACTION set "NE_DONE_ACTION=command"
if not defined NE_DONE_EXIT set "NE_DONE_EXIT=0"

for %%I in ("%~dp0..\..") do set "NE_DONE_REPO_ROOT=%%~fI"

echo.
echo [DONE] %NE_DONE_ACTION%
if "%NE_DONE_EXIT%"=="0" (
  echo [OK] Completed successfully.
) else (
  echo [ERROR] Completed with exit code %NE_DONE_EXIT%.
)
echo [STATE] exit_code=%NE_DONE_EXIT%
if defined NEWENGINE_REPO_ROOT (
  echo [PATH] Workspace: %NEWENGINE_REPO_ROOT%
) else (
  echo [PATH] Workspace: %NE_DONE_REPO_ROOT%
)
if defined NEWENGINE_ROOT echo [PATH] Engine: %NEWENGINE_ROOT%
if defined NE_DONE_RESULT echo [RESULT] %NE_DONE_RESULT%
if defined NE_DONE_OUTPUT echo [RESULT] Details/output: %NE_DONE_OUTPUT%
echo [INFO] Full command output is above. Logs and artifacts are printed with [LOG], [PATH], [RESULT] or [OK] lines by the command itself.

if defined CI exit /b %NE_DONE_EXIT%
if "%NEWENGINE_NO_PAUSE%"=="1" exit /b %NE_DONE_EXIT%
if defined NEWENGINE_PARENT_SCRIPT exit /b %NE_DONE_EXIT%

echo.
echo [EXIT] Press any key to close this console...
pause >nul
exit /b %NE_DONE_EXIT%
