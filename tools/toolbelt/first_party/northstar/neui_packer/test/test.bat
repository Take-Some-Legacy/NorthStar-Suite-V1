@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "TEST_DATA=%TOOL_ROOT%\testData"
set "OUT_DIR=%TEST_DIR%_out"
set "LOG=%OUT_DIR%\last-run.txt"
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%" >nul 2>nul
mkdir "%OUT_DIR%" >nul 2>nul
set "TOOL_ID=northstar.neui_packer"
set "EXE=%TOOL_ROOT%\bin\northstar-neui-packer.exe"
set "SRC=%TEST_DATA%\buttons.neui.xml"
set "NEUI_OUT=%OUT_DIR%\buttons.neui"
>"%LOG%" echo [BATTLE] %TOOL_ID%
if not exist "%EXE%" echo [FAIL] missing exe>>"%LOG%" & exit /b 1
if not exist "%SRC%" echo [FAIL] missing source %SRC%>>"%LOG%" & exit /b 1
"%EXE%" pack --input "%SRC%" --output "%NEUI_OUT%" --logical-path assets/ui/buttons.neui >>"%LOG%" 2>>&1 || exit /b 1
if not exist "%NEUI_OUT%" exit /b 1
"%EXE%" inspect --input "%NEUI_OUT%" >"%OUT_DIR%\inspect.json" 2>>"%LOG%" || exit /b 1
"%EXE%" validate --input "%NEUI_OUT%" >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" manifest --input "%NEUI_OUT%" >"%OUT_DIR%\manifest.json" 2>>"%LOG%" || exit /b 1
"%EXE%" dump-xmlcentral --input "%NEUI_OUT%" --output "%OUT_DIR%\dump.neui.xml" >>"%LOG%" 2>>&1 || exit /b 1
"%EXE%" dump-compiled-document --input "%NEUI_OUT%" >"%OUT_DIR%\compiled-document.json" 2>>"%LOG%" || exit /b 1
"%EXE%" dump-binding-plan --input "%NEUI_OUT%" >"%OUT_DIR%\binding-plan.json" 2>>"%LOG%" || exit /b 1
"%EXE%" dump-dependencies --input "%NEUI_OUT%" >"%OUT_DIR%\dependencies.json" 2>>"%LOG%" || exit /b 1
>"%OUT_DIR%\proof-of-work.txt" echo tool=%TOOL_ID%
>>"%OUT_DIR%\proof-of-work.txt" echo runtime=%NEUI_OUT%
>>"%OUT_DIR%\proof-of-work.txt" echo result=PASS
echo [OK] neui_packer battle test passed
exit /b 0
