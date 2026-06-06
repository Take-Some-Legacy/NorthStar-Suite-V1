@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\xargs.exe"
set "WORK=%TOOL_ROOT%\test\_out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.xargs functional smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" || exit /b 1
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
py -c "import os; from pathlib import Path; Path(os.environ['WORK'], 'items.txt').write_text('alpha\nbeta\n', newline='\n')"
type "%WORK%\items.txt" | "%EXE%" -n 1 "%TOOL_ROOT%\..\printf\bin\printf.exe" "item:%%s\n" > "%WORK%\out.txt"
set "RC=%ERRORLEVEL%"
type "%WORK%\out.txt"
if not "%RC%"=="0" goto :done
py -c "from pathlib import Path; data=Path(r'%WORK%\out.txt').read_text().replace('\r',''); raise SystemExit(0 if 'item:alpha\n' in data and 'item:beta\n' in data else 1)" || set "RC=1"
if not "%RC%"=="0" goto :done
echo [PASS] xargs invoked echo for each input item

:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
