@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\tar.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "WORK=%TEMP%\nst_msys2_tar_smoke"
set "OUT=%WORK%\tar.out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.tar smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] mode=list-existing-tar-fixture-relative-path
echo [INFO] work=%WORK%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
if not exist "%DATA%\payload.tar" echo [FAIL] missing fixture: %DATA%\payload.tar& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" > nul 2> nul
pushd "%DATA%"
echo [CMD] "%EXE%" -tf payload.tar
"%EXE%" -tf payload.tar > "%OUT%" 2> "%WORK%\tar.err"
set "RC=%ERRORLEVEL%"
popd
if exist "%OUT%" type "%OUT%"
if exist "%WORK%\tar.err" type "%WORK%\tar.err"
if not "%RC%"=="0" goto :done
findstr /c:"payload/a.txt" "%OUT%" > nul
if not "%ERRORLEVEL%"=="0" echo [FAIL] expected payload/a.txt missing& set "RC=1"& goto :done
findstr /c:"payload/b.txt" "%OUT%" > nul
if not "%ERRORLEVEL%"=="0" echo [FAIL] expected payload/b.txt missing& set "RC=1"& goto :done
echo [PASS] vendor.msys2.gnu.tar smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
