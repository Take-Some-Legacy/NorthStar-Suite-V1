@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\unxz.exe"
set "WORK=%TOOL_ROOT%\test\_out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.unxz functional smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" || exit /b 1
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
echo unxz-smoke> "%WORK%\input.txt"
"%TOOL_ROOT%\..\xz\bin\xz.exe" -k "%WORK%\input.txt"
if errorlevel 1 set "RC=1"& goto :done
copy /y "%WORK%\input.txt.xz" "%WORK%\decode-me.xz" > nul
"%EXE%" "%WORK%\decode-me.xz"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
if not exist "%WORK%\decode-me" echo [FAIL] unxz output missing& set "RC=1"& goto :done
findstr /x /c:"unxz-smoke" "%WORK%\decode-me" > nul || set "RC=1"
if not "%RC%"=="0" goto :done
echo [PASS] unxz decompressed xz payload

:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
