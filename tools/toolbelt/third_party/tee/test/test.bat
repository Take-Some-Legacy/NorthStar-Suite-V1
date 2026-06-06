@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\tee.exe"
set "WORK=%TOOL_ROOT%\test\_out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.tee functional smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" || exit /b 1
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
echo tee-smoke> "%WORK%\input.txt"
"%EXE%" "%WORK%\tee.out" < "%WORK%\input.txt" > "%WORK%\stdout.out"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
findstr /x /c:"tee-smoke" "%WORK%\tee.out" > nul || set "RC=1"
findstr /x /c:"tee-smoke" "%WORK%\stdout.out" > nul || set "RC=1"
if not "%RC%"=="0" goto :done
echo [PASS] tee wrote stdout and file

:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
