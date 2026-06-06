@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\patch.exe"
set "WORK=%TOOL_ROOT%\test\_out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.gitforwindows.gnu.patch functional smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" || exit /b 1
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
py -c "import os; from pathlib import Path; w=Path(os.environ['WORK']); (w/'target.txt').write_text('before\n', newline='\n'); (w/'change.patch').write_text('--- target.txt\n+++ target.txt\n@@ -1 +1 @@\n-before\n+after\n', newline='\n')"
pushd "%WORK%"
"%EXE%" target.txt change.patch > patch.out 2> patch.err
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" type "%WORK%\patch.err"& goto :done
py -c "import os; from pathlib import Path; raise SystemExit(0 if Path(os.environ['WORK'], 'target.txt').read_text().strip()=='after' else 1)"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
echo [PASS] patch applied unified diff to temp file

:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
