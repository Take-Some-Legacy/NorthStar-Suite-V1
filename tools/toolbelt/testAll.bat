@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "TOOLBELT_ROOT=%~dp0"
set "TOOLBELT_ROOT=%TOOLBELT_ROOT:~0,-1%"
set "TOTAL=0"
set "PASS=0"
set "FAIL=0"
set "RESULT_DIR=%TOOLBELT_ROOT%\.testAll"
set "RESULT_FILE=%RESULT_DIR%\last-run.txt"

if not exist "%RESULT_DIR%" mkdir "%RESULT_DIR%" > nul 2> nul

> "%RESULT_FILE%" echo [TESTALL] Toolbelt smoke test run
>> "%RESULT_FILE%" echo [INFO] toolbelt_root=%TOOLBELT_ROOT%
>> "%RESULT_FILE%" echo [INFO] runner=single-console cmd.exe call mode
>> "%RESULT_FILE%" echo.

echo ============================================================
echo [TESTALL] Toolbelt smoke tests
echo [INFO] toolbelt_root=%TOOLBELT_ROOT%
echo [INFO] scope=first_party + third_party
echo [INFO] runner=single-console, no start, no child terminal windows
echo ============================================================
echo.

for %%G in (first_party third_party) do (
  set "GROUP=%%G"
  set "GROUP_RUNNER=%TOOLBELT_ROOT%\%%G\testAll.bat"
  set /a TOTAL+=1

  echo ------------------------------------------------------------
  echo [RUN] %%G: !GROUP_RUNNER!
  echo [RUN] %%G: !GROUP_RUNNER!>> "%RESULT_FILE%"

  if not exist "!GROUP_RUNNER!" (
    set /a FAIL+=1
    echo [FAIL] missing runner: !GROUP_RUNNER!
    echo [FAIL] missing runner: !GROUP_RUNNER!>> "%RESULT_FILE%"
    echo.>> "%RESULT_FILE%"
  ) else (
    rem Keep nested aggregate runners inside this same visible console.
    rem NORTHSTAR_TESTALL=1 suppresses nested pauses; this top-level runner pauses once at the end.
    cmd.exe /d /q /c "set NORTHSTAR_TESTALL=1&& call "!GROUP_RUNNER!""
    set "RC=!ERRORLEVEL!"
    if "!RC!"=="0" (
      set /a PASS+=1
      echo [PASS] %%G testAll
      echo [PASS] %%G testAll>> "%RESULT_FILE%"
    ) else (
      set /a FAIL+=1
      echo [FAIL] %%G testAll exit=!RC!
      echo [FAIL] %%G testAll exit=!RC!>> "%RESULT_FILE%"
    )
    echo.>> "%RESULT_FILE%"
  )
)

echo ============================================================
echo [SUMMARY] groups=%TOTAL% pass=%PASS% fail=%FAIL%
echo [RESULT] report=%RESULT_FILE%
if "%FAIL%"=="0" (
  if "%TOTAL%"=="0" (
    echo [FAIL] toolbelt testAll found no groups
    set "RC=1"
  ) else (
    echo [PASS] toolbelt testAll smokeTest passed
    set "RC=0"
  )
) else (
  echo [FAIL] toolbelt testAll smokeTest failed
  set "RC=1"
)
echo ============================================================
>> "%RESULT_FILE%" echo [SUMMARY] groups=%TOTAL% pass=%PASS% fail=%FAIL%
>> "%RESULT_FILE%" echo [RESULT] exit=%RC%
pause
exit /b %RC%
