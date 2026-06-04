@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\touch.exe"
set "OUT=%TOOL_ROOT%\test\_out"
set "TARGET=%OUT%\touched.txt"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.touch smokeTest
echo [INFO] root=%TOOL_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%OUT%" mkdir "%OUT%"
if exist "%TARGET%" del /q "%TARGET%"
echo [CMD] "%EXE%" "%TARGET%"
"%EXE%" "%TARGET%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
if not exist "%TARGET%" echo [FAIL] touch did not create target& set "RC=1"& goto :done
echo [PASS] vendor.gnuwin32.touch smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
