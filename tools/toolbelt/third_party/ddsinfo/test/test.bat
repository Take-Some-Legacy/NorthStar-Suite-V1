@echo off
setlocal
set "PKG=%~dp0.."
set "EXE=%PKG%\bin\ddsinfo.exe"
set "DATA=%PKG%\testData"
set "OUT=%~dp0_out"
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%" || exit /b 1
if not exist "%EXE%" exit /b 1
if not exist "%DATA%\test.dds" exit /b 1
"%EXE%" --help > "%OUT%\help.txt" 2>&1 || goto :fail
findstr /c:"ddsinfo [options] <paths>" "%OUT%\help.txt" >nul || goto :fail
"%EXE%" -c -d "%DATA%\test.dds" > "%OUT%\inspect.txt" 2>&1 || goto :fail
findstr /i /c:"test.dds" "%OUT%\inspect.txt" >nul || goto :fail
"%EXE%" -r -c -d -f *.dds "%DATA%" > "%OUT%\scan.txt" 2>&1 || goto :fail
findstr /i /c:"test.dds" "%OUT%\scan.txt" >nul || goto :fail
(
  echo [OK] ddsinfo battle test passed
  echo exe=%EXE%
  echo data=%DATA%
  echo fixture=%DATA%\test.dds
) > "%OUT%\last-run.txt"
type "%OUT%\last-run.txt"
exit /b 0
:fail
echo [ERROR] ddsinfo battle test failed
if exist "%OUT%\help.txt" type "%OUT%\help.txt"
if exist "%OUT%\inspect.txt" type "%OUT%\inspect.txt"
if exist "%OUT%\scan.txt" type "%OUT%\scan.txt"
exit /b 1
