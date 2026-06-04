@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\tail.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "OUT=%TEMP%\northstar-tail-smoke.out"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.tail smokeTest
echo [INFO] root=%TOOL_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
echo [CMD] "%EXE%" -n 3 "%DATA%\input.log"
"%EXE%" -n 3 "%DATA%\input.log" > "%OUT%"
set "RC=%ERRORLEVEL%"
type "%OUT%"
if not "%RC%"=="0" goto :done
fc "%OUT%" "%DATA%\expected-tail.txt" > nul
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
echo [PASS] vendor.gnuwin32.tail smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
