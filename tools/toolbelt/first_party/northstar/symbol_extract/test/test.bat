@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0..
set TOOL=%ROOT%\bin\northstar-symbol-extract.exe
set DATA=%ROOT%\testData\sample-empty-pe.exe
set OUT=%ROOT%\test\_out

if not exist "%OUT%" mkdir "%OUT%"

if not exist "%TOOL%" (
  echo [ERROR] missing tool: %TOOL%
  if not "%NORTHSTAR_TESTALL%"=="1" pause
  exit /b 1
)

echo [INFO] Running northstar-symbol-extract toolbelt smoke tests...
echo [INFO] Tool: %TOOL%
echo [INFO] Data: %DATA%
echo.

"%TOOL%" --help > "%OUT%\help.txt"
if errorlevel 1 goto fail
findstr /C:"Usage:" "%OUT%\help.txt" >nul || goto fail
findstr /C:"northstar-symbol-extract" "%OUT%\help.txt" >nul || goto fail
echo [OK] help saved to %OUT%\help.txt

"%TOOL%" version > "%OUT%\version.txt"
if errorlevel 1 goto fail
findstr /C:"northstar-symbol-extract" "%OUT%\version.txt" >nul || goto fail
echo [OK] version output:
type "%OUT%\version.txt"
echo.

"%TOOL%" accepted-inputs > "%OUT%\accepted-inputs.txt"
if errorlevel 1 goto fail
findstr /C:"accepted input files" "%OUT%\accepted-inputs.txt" >nul || goto fail
echo [OK] accepted-inputs output:
type "%OUT%\accepted-inputs.txt"
echo.

"%TOOL%" doctor > "%OUT%\doctor.txt"
if errorlevel 1 goto fail
findstr /C:"doctor passed" "%OUT%\doctor.txt" >nul || goto fail
echo [OK] doctor output:
type "%OUT%\doctor.txt"
echo.

"%TOOL%" -in "%DATA%" > "%OUT%\symbols.txt"
if errorlevel 1 goto fail
findstr /C:"[INFO]" "%OUT%\symbols.txt" >nul && goto fail
findstr /C:"[OK]" "%OUT%\symbols.txt" >nul && goto fail
echo [OK] extract payload stayed clean: %OUT%\symbols.txt

"%TOOL%" -in "%DATA%" -out "%OUT%\symbols-file.txt"
if errorlevel 1 goto fail
if not exist "%OUT%\symbols-file.txt" goto fail
echo [OK] -out wrote payload file

(
  echo [OK] northstar-symbol-extract smoke tests passed
  echo tool=%TOOL%
  echo data=%DATA%
  echo output_dir=%OUT%
) > "%OUT%\last-run.txt"

echo.
type "%OUT%\last-run.txt"
echo.
echo [OK] All tests passed. Output files are in: %OUT%
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b 0

:fail
echo.
echo [ERROR] northstar-symbol-extract smoke tests failed.
echo [INFO] Output files are in: %OUT%
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b 1
