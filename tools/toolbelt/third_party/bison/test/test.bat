@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
for %%I in ("%TOOL_ROOT%\..\..\libraries") do set "LIB_ROOT=%%~fI"
set "EXE=%TOOL_ROOT%\bin\bison.exe"
set "WORK=%TOOL_ROOT%\test\_out"
set "RC=0"
echo ============================================================
echo [SMOKE] vendor.msys2.gnu.bison functional smokeTest
echo [INFO] root=%TOOL_ROOT%
echo [INFO] libraries=%LIB_ROOT%
echo [INFO] work=%WORK%
echo ============================================================
if exist "%WORK%" rmdir /s /q "%WORK%" > nul 2> nul
mkdir "%WORK%" || exit /b 1
if not exist "%EXE%" echo [FAIL] missing executable: %EXE%& set "RC=1"& goto :done
if not exist "%LIB_ROOT%\msys-2.0.dll" echo [FAIL] missing shared library: %LIB_ROOT%\msys-2.0.dll& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\bin;%LIB_ROOT%;%PATH%"
set "M4=m4"
set "M4_EXE=%TOOL_ROOT%\..\m4\bin\m4.exe"
set "BISON_PKGDATADIR=%TOOL_ROOT%\share\bison"
if not exist "%M4_EXE%" echo [FAIL] missing m4 dependency: %M4_EXE%& set "RC=1"& goto :done
if not exist "%BISON_PKGDATADIR%\m4sugar\m4sugar.m4" echo [FAIL] missing bison pkgdata: %BISON_PKGDATADIR%& set "RC=1"& goto :done
set "PATH=%TOOL_ROOT%\..\m4\bin;%PATH%"
> "%WORK%\grammar.y" echo %%{
>> "%WORK%\grammar.y" echo int yylex(void); void yyerror(const char *s) { }
>> "%WORK%\grammar.y" echo %%}
>> "%WORK%\grammar.y" echo %%token NUM
>> "%WORK%\grammar.y" echo %%%% 
>> "%WORK%\grammar.y" echo input: NUM ;
>> "%WORK%\grammar.y" echo %%%% 
"%EXE%" -o "%WORK%\parser.c" "%WORK%\grammar.y" > "%WORK%\bison.out" 2> "%WORK%\bison.err"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" type "%WORK%\bison.err"& goto :done
if not exist "%WORK%\parser.c" echo [FAIL] parser.c was not generated& set "RC=1"& goto :done
findstr /c:"yyparse" "%WORK%\parser.c" > nul || set "RC=1"
if not "%RC%"=="0" goto :done
echo [PASS] bison generated parser from grammar fixture

:done
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
