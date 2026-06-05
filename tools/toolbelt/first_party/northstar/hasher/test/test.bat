@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0..
set TOOL=%ROOT%\bin\northstar-hasher.exe
set DATA=%ROOT%\testData\names.txt
set OUT=%ROOT%\test\_out

if not exist "%OUT%" mkdir "%OUT%"

if not exist "%TOOL%" (
  echo [ERROR] missing tool: %TOOL%
  pause
  exit /b 1
)

echo [INFO] Running northstar-hasher toolbelt smoke tests...
echo [INFO] Tool: %TOOL%
echo [INFO] Data: %DATA%
echo.

"%TOOL%" --help > "%OUT%\help.txt"
if errorlevel 1 goto fail
findstr /C:"Usage:" "%OUT%\help.txt" >nul || goto fail
findstr /C:"northstar-hasher" "%OUT%\help.txt" >nul || goto fail
echo [OK] help saved to %OUT%\help.txt

"%TOOL%" --version > "%OUT%\version.txt"
if errorlevel 1 goto fail
findstr /C:"northstar-hasher" "%OUT%\version.txt" >nul || goto fail
echo [OK] version output:
type "%OUT%\version.txt"
echo.

"%TOOL%" "%DATA%" > "%OUT%\default.txt"
if errorlevel 1 goto fail
echo [OK] default hashing output:
type "%OUT%\default.txt"
echo.

"%TOOL%" -literal "%DATA%" > "%OUT%\literal.txt"
if errorlevel 1 goto fail
echo [OK] literal hashing output:
type "%OUT%\literal.txt"
echo.

"%TOOL%" -stripext "%DATA%" > "%OUT%\stripext.txt"
if errorlevel 1 goto fail
echo [OK] extension stripping output:
type "%OUT%\stripext.txt"
echo.

"%TOOL%" "%DATA%" 0xb779a091 > "%OUT%\filtered.txt"
if errorlevel 1 goto fail
echo [OK] hash filtering output:
type "%OUT%\filtered.txt"
echo.

(
  echo [OK] northstar-hasher smoke tests passed
  echo tool=%TOOL%
  echo data=%DATA%
  echo output_dir=%OUT%
) > "%OUT%\last-run.txt"

echo.
type "%OUT%\last-run.txt"
echo.
echo [OK] All tests passed. Output files are in: %OUT%
pause
exit /b 0

:fail
echo.
echo [ERROR] northstar-hasher smoke tests failed.
echo [INFO] Output files are in: %OUT%
pause
exit /b 1
