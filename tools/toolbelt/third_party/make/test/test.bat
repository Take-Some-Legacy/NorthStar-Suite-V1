@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\make.exe"
set "DATA=%TOOL_ROOT%\test\testData"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.make smokeTest
echo [INFO] root=%TOOL_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
echo [CMD] "%EXE%" -f "%DATA%\Makefile" smoke
"%EXE%" -f "%DATA%\Makefile" smoke
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
echo [PASS] vendor.gnuwin32.make smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
