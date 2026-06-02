@echo off
setlocal EnableExtensions
set "ROOT=%~dp0."
call "%ROOT%\aiBridge.bat" stdio %*
exit /b %errorlevel%
