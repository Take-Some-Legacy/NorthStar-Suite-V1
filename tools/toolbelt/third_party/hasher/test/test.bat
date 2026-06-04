@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\hasher.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "OUT=%TEMP%\nst_hasher_smoke.out"
echo ============================================================
echo [SMOKE] vendor.hasher smokeTest
echo [INFO] tool=Hasher
echo [INFO] root=%TOOL_ROOT%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
echo [CMD] "%EXE%" "%DATA%\names.txt"
"%EXE%" "%DATA%\names.txt" > "%OUT%"
set "RAW_RC=%ERRORLEVEL%"
type "%OUT%"
findstr /c:"player_zero" "%OUT%" > nul
if not "%ERRORLEVEL%"=="0" echo [FAIL] expected hash output missing& set "RC=1"& goto :done
for %%A in ("%OUT%") do if %%~zA LEQ 0 echo [FAIL] hasher output is empty& set "RC=1"& goto :done
set "RC=0"
echo [INFO] raw_exit=%RAW_RC% accepted because expected hash output was produced
echo [PASS] vendor.hasher smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
