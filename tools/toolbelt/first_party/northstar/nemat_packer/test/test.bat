@echo off

setlocal EnableExtensions

set "TEST_DIR=%~dp0"

for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"

set "TEST_DATA=%TOOL_ROOT%\testData"

set "OUT_DIR=%TEST_DIR%_out"

set "LOG=%OUT_DIR%\last-run.txt"

if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%" >nul 2>nul

mkdir "%OUT_DIR%" >nul 2>nul

set "TOOL_ID=northstar.nemat_packer"
set "EXE=%TOOL_ROOT%\bin\northstar-nemat-packer.exe"
set "XML_OUT=%OUT_DIR%\proof_panel.nemat.xml"
set "NEMAT_OUT=%OUT_DIR%\proof_panel.nemat"
>"%LOG%" echo [BATTLE] %TOOL_ID%
if not exist "%EXE%" echo [FAIL] missing exe>>"%LOG%" & exit /b 1
"%EXE%" create-draft --material proof_panel --texture base_color=textures/proof.ytd@proof_bc --param roughness:float=0.5 --output "%XML_OUT%" >>"%LOG%" 2>>&1 || exit /b 1
if not exist "%XML_OUT%" exit /b 1
"%EXE%" validate --input "%XML_OUT%" >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" pack --input "%XML_OUT%" --output "%NEMAT_OUT%" >>"%LOG%" 2>>&1 || exit /b 1
if not exist "%NEMAT_OUT%" exit /b 1
"%EXE%" inspect --input "%NEMAT_OUT%" >"%OUT_DIR%\inspect.json" 2>>"%LOG%" || exit /b 1
"%EXE%" validate --input "%NEMAT_OUT%" >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" dump-xml --input "%NEMAT_OUT%" --output "%OUT_DIR%\dump.nemat.xml" >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" manifest --input "%NEMAT_OUT%" >"%OUT_DIR%\manifest.json" 2>>"%LOG%" || exit /b 1
"%EXE%" graph --input "%NEMAT_OUT%" >"%OUT_DIR%\graph.json" 2>>"%LOG%" || exit /b 1
>"%OUT_DIR%\proof-of-work.txt" echo tool=%TOOL_ID%
>>"%OUT_DIR%\proof-of-work.txt" echo runtime=%NEMAT_OUT%
>>"%OUT_DIR%\proof-of-work.txt" echo result=PASS
echo [OK] nemat_packer battle test passed
exit /b 0
