@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\gawk.exe"
set "OUT=%TEMP%\northstar-gawk-smoke.out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.gawk smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
echo [CMD] tool-specific smoke
"%EXE%" "BEGIN { print "awk-ok" }" > "%OUT%"
set "RC=%ERRORLEVEL%"
type "%OUT%"
if not "%RC%"=="0" goto :done
for %%I in ("%OUT%") do if %%~zI LEQ 0 set "RC=1"
if not "%RC%"=="0" goto :done
echo [PASS] vendor.msys2.gnu.gawk smokeTest passed
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
