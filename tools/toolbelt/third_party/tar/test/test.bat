@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\tar.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "WORK=%TEMP%\nst_tar_smoke"
set "OUT=%WORK%\tar.out"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.tar smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] mode=list-existing-tar-fixture
echo [INFO] work=%WORK%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%DATA%\payload.tar" echo [FAIL] missing fixture: %DATA%\payload.tar& set "RC=1"& goto :done
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" > nul 2> nul
copy /y "%EXE%" "%WORK%\tar.exe" > nul
copy /y "%TOOL_ROOT%\bin\libiconv-2.dll" "%WORK%\libiconv-2.dll" > nul 2> nul
copy /y "%TOOL_ROOT%\bin\libintl-2.dll" "%WORK%\libintl-2.dll" > nul 2> nul
copy /y "%DATA%\payload.tar" "%WORK%\payload.tar" > nul
pushd "%WORK%"
echo [CMD] tar.exe -tf payload.tar
tar.exe -tf payload.tar > "%OUT%" 2> nul
set "RC=%ERRORLEVEL%"
popd
type "%OUT%"
if not "%RC%"=="0" goto :done
findstr /c:"payload/a.txt" "%OUT%" > nul
if not "%ERRORLEVEL%"=="0" echo [FAIL] expected payload/a.txt missing& set "RC=1"& goto :done
findstr /c:"payload/b.txt" "%OUT%" > nul
if not "%ERRORLEVEL%"=="0" echo [FAIL] expected payload/b.txt missing& set "RC=1"& goto :done
echo [PASS] vendor.gnuwin32.tar smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
