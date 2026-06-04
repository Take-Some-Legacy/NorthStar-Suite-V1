@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\funzip.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "OUT=%TEMP%\nst_funzip_smoke.out"
set "ERR=%TEMP%\nst_funzip_smoke.err"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.funzip smokeTest
echo [INFO] tool=GNUWin32 funzip
echo [INFO] root=%TOOL_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%DATA%\hello.gz" echo [FAIL] missing fixture: %DATA%\hello.gz& set "RC=1"& goto :done
echo [CMD] "%EXE%" "%DATA%\hello.gz"
"%EXE%" "%DATA%\hello.gz" > "%OUT%" 2> "%ERR%"
set "RC=%ERRORLEVEL%"
type "%OUT%"
for %%A in ("%ERR%") do if %%~zA GTR 0 (
  echo [STDERR]
  type "%ERR%"
  if "%RC%"=="0" set "RC=1"
)
if not "%RC%"=="0" goto :done
findstr /c:"hello" "%OUT%" > nul
if not "%ERRORLEVEL%"=="0" echo [FAIL] expected decompressed text missing& set "RC=1"& goto :done
echo [PASS] vendor.gnuwin32.funzip smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
