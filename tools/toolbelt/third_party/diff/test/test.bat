@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\diff.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "OUT=%TEMP%\northstar-diff-smoke.out"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.diff smokeTest
echo [INFO] root=%TOOL_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
echo [CMD] "%EXE%" -u "%DATA%\left.txt" "%DATA%\right.txt"
"%EXE%" -u "%DATA%\left.txt" "%DATA%\right.txt" > "%OUT%"
set "RC=%ERRORLEVEL%"
if "%RC%"=="1" set "RC=0"
type "%OUT%"
if not "%RC%"=="0" goto :done
echo [PASS] vendor.gnuwin32.diff smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
