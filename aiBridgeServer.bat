@echo off
setlocal EnableExtensions
rem North Star / Take Some external Suite root hook.
rem The concrete path is owned by environment, not by this launcher.
if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"
if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"
if defined NEWENGINE_SUITE_ROOT if exist "%NEWENGINE_SUITE_ROOT%\script-env.cmd" call "%NEWENGINE_SUITE_ROOT%\script-env.cmd"
if not defined NEWENGINE_SUITE_ROOT if defined TAKESOME_SUITE_ROOT set "NEWENGINE_SUITE_ROOT=%TAKESOME_SUITE_ROOT%"
if not defined TAKESOME_SUITE_ROOT if defined NEWENGINE_SUITE_ROOT set "TAKESOME_SUITE_ROOT=%NEWENGINE_SUITE_ROOT%"
set "ROOT=%~dp0."
call "%ROOT%\aiBridge.bat" stdio %*
exit /b %errorlevel%
