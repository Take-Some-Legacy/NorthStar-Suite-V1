@echo off
setlocal EnableExtensions
rem North Star / Take Some external Suite root hook.
rem The concrete path is owned by environment, not by this launcher.
if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"
if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"
if defined NEWENGINE_SUITE_ROOT if exist "%NEWENGINE_SUITE_ROOT%\script-env.cmd" call "%NEWENGINE_SUITE_ROOT%\script-env.cmd"
if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"
if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"
chcp 65001 >nul
color 0B >nul 2>nul
title Take Some Suite - North Star Engine

for %%I in ("%~dp0.") do set "NE_SUITE_REPO_ROOT=%%~fI"
set "NE_SUITE_SCRIPT=%NE_SUITE_REPO_ROOT%\tools\scripts\takesome.py"
set "NE_SUITE_PY="

where py >nul 2>nul
if not errorlevel 1 set "NE_SUITE_PY=py -3"
if not defined NE_SUITE_PY (
  where python >nul 2>nul
  if not errorlevel 1 set "NE_SUITE_PY=python"
)

if not defined NE_SUITE_PY (
  echo.
  echo [ERROR] Python was not found in PATH.
  echo [ERROR] Install Python or enable the Windows Python launcher, then open suite.bat again.
  echo.
  echo [EXIT] Press any key to close this console...
  pause >nul
  exit /b 10
)

if not exist "%NE_SUITE_SCRIPT%" (
  echo.
  echo [ERROR] Suite launcher is damaged: missing %NE_SUITE_SCRIPT%
  echo [PATH] Project root: %NE_SUITE_REPO_ROOT%
  echo.
  echo [EXIT] Press any key to close this console...
  pause >nul
  exit /b 11
)

set "NEWENGINE_PARENT_SUITE=1"
set "NEWENGINE_SUITE_PYTHON_CMD=%NE_SUITE_PY%"
%NE_SUITE_PY% "%NE_SUITE_SCRIPT%" suite %*
set "NE_SUITE_EXIT=%ERRORLEVEL%"

if not "%NE_SUITE_EXIT%"=="0" (
  echo.
  echo [ERROR] Take Some Suite exited with code %NE_SUITE_EXIT%.
  echo [EXIT] Press any key to close this console...
  pause >nul
)
exit /b %NE_SUITE_EXIT%
