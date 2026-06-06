@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..\libraries") do set "LIB_ROOT=%%~fI"
set "PATH=%SCRIPT_DIR%;%LIB_ROOT%;%PATH%"
"%SCRIPT_DIR%grep.exe" -F %*
exit /b %ERRORLEVEL%
