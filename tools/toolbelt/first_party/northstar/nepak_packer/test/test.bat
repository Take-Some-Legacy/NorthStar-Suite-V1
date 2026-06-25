@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "TEST_DATA=%TOOL_ROOT%\testData"
set "OUT_DIR=%TEST_DIR%_out"
set "LOG=%OUT_DIR%\last-run.txt"
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%" >nul 2>nul
mkdir "%OUT_DIR%" >nul 2>nul
set "TOOL_ID=northstar.nepak_manager"
set "EXE=%TOOL_ROOT%\bin\northstar-nepak-manager.exe"
set "NEPAK_OUT=%OUT_DIR%\proof.nepak"
set "NEPAK_COPY=%OUT_DIR%\proof-copy.nepak"
set "EXTRACT_DIR=%OUT_DIR%\extract"
>"%LOG%" echo [BATTLE] %TOOL_ID%
if not exist "%EXE%" echo [FAIL] missing exe>>"%LOG%" & exit /b 1
if not exist "%TEST_DATA%\proof.txt" echo [FAIL] missing testData proof.txt>>"%LOG%" & exit /b 1
"%EXE%" version >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" accepted-inputs >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" doctor >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" pack --input "%TEST_DATA%" --output "%NEPAK_OUT%" >>"%LOG%" 2>>&1 || exit /b 1
if not exist "%NEPAK_OUT%" exit /b 1
copy /y "%NEPAK_OUT%" "%NEPAK_COPY%" >nul || exit /b 1
"%EXE%" inspect --input "%NEPAK_OUT%" >"%OUT_DIR%\inspect.json" 2>>"%LOG%" || exit /b 1
"%EXE%" manifest --input "%NEPAK_OUT%" >"%OUT_DIR%\manifest.json" 2>>"%LOG%" || exit /b 1
"%EXE%" list --input "%NEPAK_OUT%" >"%OUT_DIR%\entries.txt" 2>>"%LOG%" || exit /b 1
"%EXE%" mount-test --input "%NEPAK_OUT%" >"%OUT_DIR%\mount-test.json" 2>>"%LOG%" || exit /b 1
"%EXE%" diff --old "%NEPAK_OUT%" --new "%NEPAK_COPY%" >"%OUT_DIR%\diff.json" 2>>"%LOG%" || exit /b 1
"%EXE%" verify --input "%NEPAK_OUT%" >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" extract --input "%NEPAK_OUT%" --output "%EXTRACT_DIR%" --overwrite >>"%LOG%" 2>>&1 || exit /b 1
if not exist "%EXTRACT_DIR%\proof.txt" echo [FAIL] extracted proof.txt missing>>"%LOG%" & exit /b 1
>"%OUT_DIR%\proof-of-work.txt" echo tool=%TOOL_ID%
>>"%OUT_DIR%\proof-of-work.txt" echo runtime=%NEPAK_OUT%
>>"%OUT_DIR%\proof-of-work.txt" echo extracted=%EXTRACT_DIR%
>>"%OUT_DIR%\proof-of-work.txt" echo result=PASS
echo [OK] nepak_manager battle test passed
exit /b 0
