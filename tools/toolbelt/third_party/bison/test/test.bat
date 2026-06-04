@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\bison.exe"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.bison smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] mode=payload-version-smoke
echo [INFO] grammar generation requires share\bison data; this package currently validates executable payload only.
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
echo [CMD] "%EXE%" --version
"%EXE%" --version
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
echo [PASS] vendor.gnuwin32.bison smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
