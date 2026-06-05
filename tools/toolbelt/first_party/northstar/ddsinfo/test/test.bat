@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\ddsinfo.exe"
set "LIB=%LIB_ROOT%\northstar.ddsinfo.dll"
set "DATA=%TOOL_ROOT%\testData"
set "OUT=%TEST_DIR%_out"
set "RC=0"
echo ============================================================
echo [SMOKE] northstar.ddsinfo smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] library=%LIB%
echo [INFO] source=tools\toolsSrc\ddsinfo + tools\toolsSrc\ddsinfo_host
echo ============================================================
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%" || exit /b 1
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB%" echo [FAIL] missing managed library: %LIB%& set "RC=1"& goto :done
if not exist "%DATA%\test.dds" echo [FAIL] missing fixture: %DATA%\test.dds& set "RC=1"& goto :done
"%EXE%" --library "%LIB%" --version > "%OUT%\version.txt" 2>&1 || goto :fail
findstr /c:"ddsinfo Version: 1.2.0.0" "%OUT%\version.txt" >nul || goto :fail
"%EXE%" --library "%LIB%" --help > "%OUT%\help.txt" 2>&1 || goto :fail
findstr /c:"ddsinfo [options] <paths>" "%OUT%\help.txt" >nul || goto :fail
"%EXE%" --library "%LIB%" -c -d "%DATA%\test.dds" > "%OUT%\inspect.txt" 2>&1 || goto :fail
findstr /i /c:"test.dds" "%OUT%\inspect.txt" >nul || goto :fail
"%EXE%" --library "%LIB%" -r -c -d -f *.dds "%DATA%" > "%OUT%\scan.txt" 2>&1 || goto :fail
findstr /i /c:"test.dds" "%OUT%\scan.txt" >nul || goto :fail
(
  echo [PASS] northstar.ddsinfo smokeTest passed
  echo exe=%EXE%
  echo library=%LIB%
  echo data=%DATA%
  echo fixture=%DATA%\test.dds
) > "%OUT%\last-run.txt"
type "%OUT%\last-run.txt"
goto :done
:fail
echo [FAIL] northstar.ddsinfo smokeTest failed
if exist "%OUT%\version.txt" type "%OUT%\version.txt"
if exist "%OUT%\help.txt" type "%OUT%\help.txt"
if exist "%OUT%\inspect.txt" type "%OUT%\inspect.txt"
if exist "%OUT%\scan.txt" type "%OUT%\scan.txt"
set "RC=1"
:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
