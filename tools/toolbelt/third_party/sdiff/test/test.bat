@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
set "RC=0"
set "EXE=%TOOL_ROOT%\bin\sdiff.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "WORK=%TEMP%\nst_sdiff_smoke"
set "OUT=%WORK%\sdiff.out"
set "ERR=%WORK%\sdiff.err"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.sdiff smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" > nul 2> nul
copy /y "%DATA%\left.txt" "%WORK%\left.txt" > nul
copy /y "%DATA%\right.txt" "%WORK%\right.txt" > nul
pushd "%WORK%"
"%EXE%" left.txt right.txt > "%OUT%" 2> "%ERR%"
set "RAW_RC=%ERRORLEVEL%"
popd
if "%RAW_RC%"=="1" (set "RC=0") else (set "RC=%RAW_RC%")
type "%OUT%"
for %%A in ("%ERR%") do if %%~zA GTR 0 (echo [STDERR]& type "%ERR%")
if not "%RC%"=="0" goto :done
echo [PASS] vendor.msys2.gnu.sdiff smokeTest passed
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
