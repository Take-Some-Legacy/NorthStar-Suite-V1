@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
set "RC=0"
set "EXE=%TOOL_ROOT%\bin\fgrep.bat"
set "DATA=%TOOL_ROOT%\test\testData"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.fgrep smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing wrapper: %EXE%& set "RC=1"& goto :done
"%EXE%" -n needle "%DATA%\input.txt"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
echo [PASS] vendor.msys2.gnu.fgrep smokeTest passed
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
