@echo off
rem Guard for Take Some / North Star Engine build/run scripts.
rem This file intentionally does not use setlocal: when it loads the repo-local
rem env cache, the caller script must see those variables.
chcp 65001 >nul

set "NE_REQUIRE_EXIT=0"
for %%I in ("%~dp0..\..") do set "NE_REQUIRE_REPO_ROOT=%%~fI"
set "NE_REQUIRE_SUITE_ROOT=%NE_REQUIRE_REPO_ROOT%\.takesome"
set "NE_REQUIRE_ENV_CMD=%NE_REQUIRE_SUITE_ROOT%\script-env.cmd"

rem If the current shell does not have the env, but the repo was initialized once,
rem hydrate this invocation from the repo-local generated env file.
if /I not "%NEWENGINE_SCRIPT_ENV%"=="1" if exist "%NE_REQUIRE_ENV_CMD%" call "%NE_REQUIRE_ENV_CMD%"
if not defined NEWENGINE_REPO_ROOT if exist "%NE_REQUIRE_ENV_CMD%" call "%NE_REQUIRE_ENV_CMD%"
if not defined NEWENGINE_ROOT if exist "%NE_REQUIRE_ENV_CMD%" call "%NE_REQUIRE_ENV_CMD%"
if not defined NEWENGINE_PLUGIN_DIR if exist "%NE_REQUIRE_ENV_CMD%" call "%NE_REQUIRE_ENV_CMD%"
if not defined NEWENGINE_PYTHON_CMD if exist "%NE_REQUIRE_ENV_CMD%" call "%NE_REQUIRE_ENV_CMD%"

if /I not "%NEWENGINE_SCRIPT_ENV%"=="1" set "NE_REQUIRE_EXIT=100"
if not defined NEWENGINE_REPO_ROOT set "NE_REQUIRE_EXIT=101"
if not defined NEWENGINE_ROOT set "NE_REQUIRE_EXIT=102"
if not defined NEWENGINE_PLUGIN_DIR set "NE_REQUIRE_EXIT=103"
if not defined NEWENGINE_SCRIPT_ROOT set "NE_REQUIRE_EXIT=104"
if not defined NEWENGINE_SUITE_ROOT set "NE_REQUIRE_EXIT=109"
if not defined NEWENGINE_PYTHON_CMD set "NE_REQUIRE_EXIT=105"

if "%NE_REQUIRE_EXIT%"=="0" if not exist "%NEWENGINE_ROOT%\Cargo.toml" set "NE_REQUIRE_EXIT=106"
if "%NE_REQUIRE_EXIT%"=="0" if not exist "%NEWENGINE_REPO_ROOT%\Plugins" set "NE_REQUIRE_EXIT=107"
if "%NE_REQUIRE_EXIT%"=="0" if not exist "%NEWENGINE_SCRIPT_ROOT%\takesome.py" set "NE_REQUIRE_EXIT=108"
if "%NE_REQUIRE_EXIT%"=="0" if /I not "%NEWENGINE_SUITE_ROOT%"=="%NE_REQUIRE_SUITE_ROOT%" set "NE_REQUIRE_EXIT=110"

if not "%NE_REQUIRE_EXIT%"=="0" (
  echo.
  echo [WARN] Take Some Script Env is not installed or is invalid.
  echo [WARN] Run this command in the repository root before using build/run scripts:
  echo [WARN]   suite.bat
  echo [WARN]
  echo [WARN] The init script creates a repo-local env cache and loads it into the current cmd.exe.
  echo [WARN] Build/run scripts can then restore that cache in future consoles.
  echo [WARN]
  echo [WARN] Current state:
  echo [WARN]   NEWENGINE_SCRIPT_ENV=%NEWENGINE_SCRIPT_ENV%
  echo [WARN]   NEWENGINE_REPO_ROOT=%NEWENGINE_REPO_ROOT%
  echo [WARN]   NEWENGINE_ROOT=%NEWENGINE_ROOT%
  echo [WARN]   NEWENGINE_PLUGIN_DIR=%NEWENGINE_PLUGIN_DIR%
  echo [WARN]   NEWENGINE_SCRIPT_ROOT=%NEWENGINE_SCRIPT_ROOT%
  echo [WARN]   NEWENGINE_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%
  echo [WARN]   NEWENGINE_PYTHON_CMD=%NEWENGINE_PYTHON_CMD%
  echo [WARN]   Env cache=%NE_REQUIRE_ENV_CMD%
  if not exist "%NE_REQUIRE_ENV_CMD%" echo [WARN]   Env cache status=missing
  if exist "%NE_REQUIRE_ENV_CMD%" echo [WARN]   Env cache status=present but invalid for this checkout
  if not defined NEWENGINE_CONSOLE_OWNS_PAUSE if not defined NEWENGINE_NO_PAUSE if not defined CI (
    echo.
    echo [WARN] Script stopped before doing work. Console is kept open for diagnostics.
    echo [EXIT] Press any key to close this console...
    pause >nul
  )
  set "NE_REQUIRE_REPO_ROOT="
  set "NE_REQUIRE_SUITE_ROOT="
  set "NE_REQUIRE_ENV_CMD="
  exit /b %NE_REQUIRE_EXIT%
)

rem One-shot cleanup migration. Safe when DELETE_FILES.txt is absent.
if not defined NEWENGINE_REQUIRE_SKIP_SYNC (
  %NEWENGINE_PYTHON_CMD% "%NEWENGINE_SCRIPT_ROOT%\takesome.py" apply-delete-list
  if errorlevel 1 exit /b %ERRORLEVEL%
)

set "NE_REQUIRE_EXIT="
set "NE_REQUIRE_REPO_ROOT="
set "NE_REQUIRE_SUITE_ROOT="
set "NE_REQUIRE_ENV_CMD="
exit /b 0
