@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "TEST_DATA=%TOOL_ROOT%\testData"
set "OUT_DIR=%TEST_DIR%_out"
set "LOG=%OUT_DIR%\last-run.txt"
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%" >nul 2>nul
mkdir "%OUT_DIR%" >nul 2>nul
set "TOOL_ID=northstar.ytyp_packer"
set "EXE=%TOOL_ROOT%\bin\northstar-ytyp-packer.exe"
set "SRC=%TEST_DATA%\proof.ytyp.xml"
set "YTYP_OUT=%OUT_DIR%\proof.ytyp"
>"%LOG%" echo [BATTLE] %TOOL_ID%
if not exist "%EXE%" echo [FAIL] missing exe>>"%LOG%" & exit /b 1
if not exist "%SRC%" echo [FAIL] missing source %SRC%>>"%LOG%" & exit /b 1
"%EXE%" pack --input "%SRC%" --output "%YTYP_OUT%" --logical-path assets/metadata/proof.ytyp >>"%LOG%" 2>>&1 || exit /b 1
if not exist "%YTYP_OUT%" exit /b 1
"%EXE%" inspect --input "%YTYP_OUT%" >"%OUT_DIR%\inspect.json" 2>>"%LOG%" || exit /b 1
"%EXE%" validate --input "%YTYP_OUT%" >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" manifest --input "%YTYP_OUT%" >"%OUT_DIR%\manifest.json" 2>>"%LOG%" || exit /b 1
"%EXE%" dump-xml --input "%YTYP_OUT%" --output "%OUT_DIR%\dump.ytyp.xml" >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" dump-metadata --input "%YTYP_OUT%" >"%OUT_DIR%\metadata.json" 2>>"%LOG%" || exit /b 1
"%EXE%" dump-dependencies --input "%YTYP_OUT%" >"%OUT_DIR%\dependencies.json" 2>>"%LOG%" || exit /b 1
>"%OUT_DIR%\proof-of-work.txt" echo tool=%TOOL_ID%
>>"%OUT_DIR%\proof-of-work.txt" echo runtime=%YTYP_OUT%
>>"%OUT_DIR%\proof-of-work.txt" echo result=PASS
echo [OK] ytyp_packer battle test passed
exit /b 0
