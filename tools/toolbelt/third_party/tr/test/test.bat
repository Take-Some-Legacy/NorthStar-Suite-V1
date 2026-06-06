@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\tr.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "OUT=%TEMP%\northstar-msys2-tr-smoke.out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.tr smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
echo [CMD] "%EXE%" --version
"%EXE%" --version > "%TEMP%\northstar-msys2-tr-version.out"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
type "%TEMP%\northstar-msys2-tr-version.out" | findstr /c:"GNU coreutils" > nul
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
echo [CMD] tool-specific smoke
"%EXE%" a-z A-Z < "%DATA%\input.txt" > "%OUT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
type "%OUT%"
fc "%OUT%" "%DATA%\expected-tr.txt" > nul
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
echo [PASS] vendor.msys2.gnu.tr smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
