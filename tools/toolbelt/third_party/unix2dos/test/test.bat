@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\unix2dos.exe"
set "WORK=%TOOL_ROOT%\test\_out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.gitforwindows.unix2dos functional smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" || exit /b 1
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
py -c "import os; from pathlib import Path; Path(os.environ['WORK'], 'lf.txt').write_bytes(b'a\nb\n')"
"%EXE%" "%WORK%\lf.txt" > "%WORK%\tool.out" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" type "%WORK%\tool.out"& goto :done
py -c "import os; from pathlib import Path; data=Path(os.environ['WORK'], 'lf.txt').read_bytes(); raise SystemExit(0 if b'\r\n' in data else 1)"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
echo [PASS] unix2dos converted LF to CRLF

:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
