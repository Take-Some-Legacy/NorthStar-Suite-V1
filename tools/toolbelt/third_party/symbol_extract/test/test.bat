@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "TOOL_ID=vendor.symbol_extract"
set "TOOL_NAME=Symbol Extract"
set "EXE=%TOOL_ROOT%\bin\\SymbolExtract.exe"
set "SMOKE_ARGS="

echo ============================================================
echo [SMOKE] %TOOL_ID% smokeTest
echo [INFO] tool=%TOOL_NAME%
echo [INFO] root=%TOOL_ROOT%
echo ============================================================

if not exist "%EXE%" (
  echo [FAIL] missing executable: %EXE%
  set "RC=1"
  goto :done
)

echo [CMD] "%EXE%" %SMOKE_ARGS%
"%EXE%" %SMOKE_ARGS%
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done

echo [PASS] %TOOL_ID% smokeTest passed
goto :done

:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
