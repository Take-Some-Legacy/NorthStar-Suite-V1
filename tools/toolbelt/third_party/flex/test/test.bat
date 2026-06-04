@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\flex.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "WORK=%TEMP%\nst_flex_smoke"
set "OUT=%WORK%\lexer.c"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.flex smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" > nul 2> nul
copy /y "%DATA%\lexer.l" "%WORK%\lexer.l" > nul
pushd "%WORK%"
echo [CMD] "%EXE%" -t lexer.l ^> lexer.c
"%EXE%" -t lexer.l > "lexer.c"
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" goto :done
if not exist "%OUT%" echo [FAIL] generated file missing: %OUT%& set "RC=1"& goto :done
for %%A in ("%OUT%") do if %%~zA LEQ 0 echo [FAIL] generated file is empty: %OUT%& set "RC=1"& goto :done
echo [PASS] vendor.gnuwin32.flex smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
