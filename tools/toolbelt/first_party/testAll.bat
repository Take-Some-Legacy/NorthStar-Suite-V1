@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "FIRST_PARTY_ROOT=%~dp0"
set "FIRST_PARTY_ROOT=%FIRST_PARTY_ROOT:~0,-1%"
set "TOTAL=0"
set "PASS=0"
set "FAIL=0"
set "RESULT_DIR=%FIRST_PARTY_ROOT%\.testAll"
set "RESULT_FILE=%RESULT_DIR%\last-run.txt"

if not exist "%RESULT_DIR%" mkdir "%RESULT_DIR%" > nul 2> nul

> "%RESULT_FILE%" echo [TESTALL] First-party tool smoke test run
>> "%RESULT_FILE%" echo [INFO] first_party_root=%FIRST_PARTY_ROOT%
>> "%RESULT_FILE%" echo [INFO] runner=single-console cmd.exe call mode
>> "%RESULT_FILE%" echo.

echo ============================================================
echo [TESTALL] First-party recursive smoke tests
echo [INFO] first_party_root=%FIRST_PARTY_ROOT%
echo [INFO] discovery=for /r scan, selecting only *\test\test.bat
echo [INFO] runner=single-console, no start, no child terminal windows
echo ============================================================
echo.

for /r "%FIRST_PARTY_ROOT%" %%T in (test.bat) do (
  set "TEST=%%~fT"
  set "SKIP=1"
  echo !TEST! | findstr /i /c:"\test\test.bat" > nul && set "SKIP="
  echo !TEST! | findstr /i /c:"\.testAll\" > nul && set "SKIP=1"
  echo !TEST! | findstr /i /c:"\test\_out\" > nul && set "SKIP=1"
  if not defined SKIP (
    set /a TOTAL+=1
    echo ------------------------------------------------------------
    echo [RUN] !TEST!
    echo [RUN] !TEST!>> "%RESULT_FILE%"

    rem Keep every smoke test inside this same visible console.
    rem Do not use START. Do not invoke .bat through file association.
    cmd.exe /d /q /c "set NORTHSTAR_TESTALL=1&& call "!TEST!""
    set "RC=!ERRORLEVEL!"

    if "!RC!"=="0" (
      set /a PASS+=1
      echo [PASS] !TEST!
      echo [PASS] !TEST!>> "%RESULT_FILE%"
    ) else (
      set /a FAIL+=1
      echo [FAIL] !TEST! exit=!RC!
      echo [FAIL] !TEST! exit=!RC!>> "%RESULT_FILE%"
    )
    echo.>> "%RESULT_FILE%"
  )
)

echo ============================================================
echo [SUMMARY] total=%TOTAL% pass=%PASS% fail=%FAIL%
echo [RESULT] report=%RESULT_FILE%
if "%FAIL%"=="0" (
  if "%TOTAL%"=="0" (
    echo [FAIL] first_party testAll found no tests
    set "RC=1"
  ) else (
    echo [PASS] first_party testAll smokeTest passed
    set "RC=0"
  )
) else (
  echo [FAIL] first_party testAll smokeTest failed
  set "RC=1"
)
echo ============================================================
>> "%RESULT_FILE%" echo [SUMMARY] total=%TOTAL% pass=%PASS% fail=%FAIL%
>> "%RESULT_FILE%" echo [RESULT] exit=%RC%
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
