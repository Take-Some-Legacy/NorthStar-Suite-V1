@echo off


setlocal EnableExtensions


set "TEST_DIR=%~dp0"


for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"


set "TEST_DATA=%TOOL_ROOT%\testData"


set "OUT_DIR=%TEST_DIR%_out"


set "LOG=%OUT_DIR%\last-run.txt"


if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%" >nul 2>nul


mkdir "%OUT_DIR%" >nul 2>nul


set "TOOL_ID=northstar.ydd_packer"

set "EXE=%TOOL_ROOT%\bin\northstar-ydd-packer.exe"

set "SRC=%TEST_DATA%"

set "YDD_OUT=%OUT_DIR%\proof.ydd"

>"%LOG%" echo [BATTLE] %TOOL_ID%

if not exist "%EXE%" echo [FAIL] missing exe>>"%LOG%" & exit /b 1

if not exist "%SRC%" echo [FAIL] missing source dir %SRC%>>"%LOG%" & exit /b 1

"%EXE%" pack --input "%SRC%" --output "%YDD_OUT%" >>"%LOG%" 2>>&1 || exit /b 1

if not exist "%YDD_OUT%" exit /b 1

"%EXE%" inspect --input "%YDD_OUT%" >"%OUT_DIR%\inspect.json" 2>>"%LOG%" || exit /b 1

"%EXE%" list --input "%YDD_OUT%" >"%OUT_DIR%\entries.txt" 2>>"%LOG%" || exit /b 1

"%EXE%" validate --input "%YDD_OUT%" >>"%LOG%" 2>>&1 || exit /b 1


>"%OUT_DIR%\proof-of-work.txt" echo tool=%TOOL_ID%

>>"%OUT_DIR%\proof-of-work.txt" echo runtime=%YDD_OUT%

>>"%OUT_DIR%\proof-of-work.txt" echo result=PASS

echo [OK] ydd_packer battle test passed

exit /b 0

