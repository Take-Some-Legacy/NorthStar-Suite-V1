@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\sdiff.exe"
set "DIFF=%TOOL_ROOT%\bin\diff.exe"
set "DATA=%TOOL_ROOT%\test\testData"
set "WORK=%TEMP%\nst_sdiff_smoke"
set "OUT=%WORK%\sdiff.out"
set "ERR=%WORK%\sdiff.err"
echo ============================================================
echo [SMOKE] vendor.gnuwin32.sdiff smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%DIFF%" echo [FAIL] missing dependency: %DIFF%& set "RC=1"& goto :done
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" > nul 2> nul
copy /y "%EXE%" "%WORK%\sdiff.exe" > nul
copy /y "%DIFF%" "%WORK%\diff.exe" > nul
copy /y "%TOOL_ROOT%\bin\libiconv2.dll" "%WORK%\libiconv2.dll" > nul 2> nul
copy /y "%TOOL_ROOT%\bin\libintl3.dll" "%WORK%\libintl3.dll" > nul 2> nul
copy /y "%DATA%\left.txt" "%WORK%\left.txt" > nul
copy /y "%DATA%\right.txt" "%WORK%\right.txt" > nul
pushd "%WORK%"
echo [CMD] sdiff.exe left.txt right.txt
sdiff.exe left.txt right.txt > "%OUT%" 2> "%ERR%"
set "RAW_RC=%ERRORLEVEL%"
popd
if "%RAW_RC%"=="1" (set "RC=0") else (set "RC=%RAW_RC%")
type "%OUT%"
for %%A in ("%ERR%") do if %%~zA GTR 0 (
  echo [STDERR]
  type "%ERR%"
)
if not "%RC%"=="0" goto :done
for %%A in ("%ERR%") do if %%~zA GTR 0 echo [FAIL] unexpected stderr from sdiff& set "RC=1"& goto :done
echo [PASS] vendor.gnuwin32.sdiff smokeTest passed
goto :done
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
