@echo off
setlocal EnableExtensions
chcp 65001 >nul
call "%~dp0..\tools\scripts\runTakeSomeCommand.bat" "Importers\buildImporters.cmd" "Importer build command finished." ".takesome\logs\build\importers-latest.log" -- build-importers %*
exit /b %ERRORLEVEL%
