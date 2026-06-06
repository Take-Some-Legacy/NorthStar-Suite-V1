@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
set "RC=0"
set "EXE=%TOOL_ROOT%\bin\m4.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "OUT=%TEMP%\northstar-m4-smoke.out"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.m4 smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
"%EXE%" "%DATA%\input.m4" > "%OUT%"
set "RC=%ERRORLEVEL%"
type "%OUT%"
if not "%RC%"=="0" goto :done
findstr /c:"Hello NorthStar" "%OUT%" > nul || set "RC=1"
if not "%RC%"=="0" goto :done
echo [PASS] vendor.msys2.gnu.m4 smokeTest passed
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
