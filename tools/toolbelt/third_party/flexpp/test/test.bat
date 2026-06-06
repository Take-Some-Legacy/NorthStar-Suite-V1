@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
set "M4=%TOOL_ROOT%\..\m4\bin\m4.exe"
set "RC=0"
set "EXE=%TOOL_ROOT%\bin\flex++.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "WORK=%TEMP%\nst_flexpp_smoke"
set "OUT=%WORK%\lexer.cpp"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.flexpp smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%M4%" echo [FAIL] missing m4 dependency: %M4%& set "RC=1"& goto :done
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" > nul 2> nul
copy /y "%DATA%\lexer.l" "%WORK%\lexer.l" > nul
pushd "%WORK%"
"%EXE%" -t lexer.l > "lexer.cpp"
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" goto :done
if not exist "%OUT%" echo [FAIL] generated file missing: %OUT%& set "RC=1"& goto :done
for %%A in ("%OUT%") do if %%~zA LEQ 0 echo [FAIL] generated file is empty: %OUT%& set "RC=1"& goto :done
echo [PASS] vendor.msys2.gnu.flexpp smokeTest passed
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
