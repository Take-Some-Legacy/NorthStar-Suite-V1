@echo off
setlocal

set "PKG=%~dp0.."
set "EXE=%PKG%\bin\northstar-neftd-packer.exe"
set "DATA=%PKG%\testData"
set "OUT=%~dp0_out"
set "PKGFILE=%OUT%\tt_lakes_trial.neftd"
set "XOUT=%OUT%\extract"
set "ENTRY=tt_lakes_neue_trial_black"

if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%" || exit /b 1
mkdir "%XOUT%" || exit /b 1

if not exist "%EXE%" exit /b 1
if not exist "%DATA%\TT Lakes Neue Trial Black.woff" exit /b 1
if not exist "%DATA%\TT Lakes Neue Trial Bold.ttf" exit /b 1
if not exist "%DATA%\TT-Lakes-Neue-Trial-Bold.otf" exit /b 1

"%EXE%" --help > "%OUT%\help.txt" 2>&1 || goto :fail
"%EXE%" pack -i "%DATA%" -o "%PKGFILE%" --family "TT Lakes Neue Trial" > "%OUT%\pack.txt" 2>&1 || goto :fail
if not exist "%PKGFILE%" goto :fail

"%EXE%" list -i "%PKGFILE%" > "%OUT%\list.txt" 2>&1 || goto :fail
findstr /c:"@tt_lakes_neue_trial_black" "%OUT%\list.txt" >nul || goto :fail
findstr /c:"@tt_lakes_neue_trial_bold" "%OUT%\list.txt" >nul || goto :fail
findstr /c:"@tt-lakes-neue-trial-bold" "%OUT%\list.txt" >nul || goto :fail

"%EXE%" inspect -i "%PKGFILE%" > "%OUT%\inspect.json" 2>&1 || goto :fail
findstr /c:"font_dictionary" "%OUT%\inspect.json" >nul || goto :fail
findstr /c:"TT Lakes Neue Trial" "%OUT%\inspect.json" >nul || goto :fail
findstr /c:"woff" "%OUT%\inspect.json" >nul || goto :fail
findstr /c:"ttf" "%OUT%\inspect.json" >nul || goto :fail
findstr /c:"otf" "%OUT%\inspect.json" >nul || goto :fail

"%EXE%" validate -i "%PKGFILE%" > "%OUT%\validate.txt" 2>&1 || goto :fail
findstr /c:"[OK] validated NEFTD font dictionary" "%OUT%\validate.txt" >nul || goto :fail

"%EXE%" extract -i "%PKGFILE%" --entry %ENTRY% --out-dir "%XOUT%" --overwrite > "%OUT%\extract.txt" 2>&1 || goto :fail
if not exist "%XOUT%\%ENTRY%.fontbin" goto :fail

(
  echo [OK] neftd_packer battle test passed
  echo data=%DATA%
  echo output=%PKGFILE%
  echo extracted=%XOUT%\%ENTRY%.fontbin
) > "%OUT%\last-run.txt"

type "%OUT%\last-run.txt"
exit /b 0

:fail
echo [ERROR] neftd_packer battle test failed
if exist "%OUT%\pack.txt" type "%OUT%\pack.txt"
if exist "%OUT%\list.txt" type "%OUT%\list.txt"
if exist "%OUT%\inspect.json" type "%OUT%\inspect.json"
if exist "%OUT%\validate.txt" type "%OUT%\validate.txt"
if exist "%OUT%\extract.txt" type "%OUT%\extract.txt"
exit /b 1
