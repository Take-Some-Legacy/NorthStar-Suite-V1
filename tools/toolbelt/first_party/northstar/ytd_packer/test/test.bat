@echo off
setlocal EnableExtensions
set "TEST_DIR=%~dp0"
for %%I in ("%TEST_DIR%..") do set "TOOL_ROOT=%%~fI"
set "TOOL_ID=northstar.ytd_packer"
set "TOOL_NAME=North Star YTD Packer"
set "EXE=%TOOL_ROOT%\bin\northstar-ytd-packer.exe"
set "TEST_DATA=%TOOL_ROOT%\testData"
set "OUT_DIR=%TEST_DIR%_out"
set "LOG=%OUT_DIR%\last-run.txt"
set "HELP_OUT=%OUT_DIR%\help.txt"
set "YTD_OUT=%OUT_DIR%\proof.ytd"
set "INSPECT_OUT=%OUT_DIR%\inspect.json"
set "EXTRACT_DIR=%OUT_DIR%\extracted"
set "PROOF=%OUT_DIR%\proof-of-work.txt"
set "RC=0"

if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%" >nul 2>nul
mkdir "%OUT_DIR%" >nul 2>nul

>"%LOG%" echo [SMOKE] %TOOL_ID% data-driven proof-of-work
>>"%LOG%" echo [INFO] tool=%TOOL_NAME%
>>"%LOG%" echo [INFO] root=%TOOL_ROOT%
>>"%LOG%" echo [INFO] testData=%TEST_DATA%

echo ============================================================
echo [SMOKE] %TOOL_ID% data-driven proof-of-work
echo [INFO] root=%TOOL_ROOT%
echo ============================================================

if not exist "%TOOL_ROOT%\tool.json" (
  echo [FAIL] missing tool.json>>"%LOG%"
  set "RC=1"
  goto :done
)
if not exist "%TOOL_ROOT%\README.md" (
  echo [FAIL] missing README.md>>"%LOG%"
  set "RC=1"
  goto :done
)
if not exist "%TEST_DATA%" (
  echo [FAIL] missing testData directory>>"%LOG%"
  set "RC=1"
  goto :done
)
if not exist "%EXE%" (
  echo [FAIL] missing executable: %EXE%>>"%LOG%"
  set "RC=1"
  goto :done
)

echo [CMD] "%EXE%" --help ^<nul>>"%LOG%"
"%EXE%" --help >"%HELP_OUT%" 2>&1 <nul
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done

echo [CMD] "%EXE%" pack --input-dir "%TEST_DATA%" --output "%YTD_OUT%">>"%LOG%"
"%EXE%" pack --input-dir "%TEST_DATA%" --output "%YTD_OUT%" >>"%LOG%" 2>>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done
if not exist "%YTD_OUT%" (
  echo [FAIL] pack did not create %YTD_OUT%>>"%LOG%"
  set "RC=1"
  goto :done
)

echo [CMD] "%EXE%" inspect --input "%YTD_OUT%">>"%LOG%"
"%EXE%" inspect --input "%YTD_OUT%" >"%INSPECT_OUT%" 2>>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done

echo [CMD] "%EXE%" validate --input "%YTD_OUT%">>"%LOG%"
"%EXE%" validate --input "%YTD_OUT%" >>"%LOG%" 2>>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done

echo [CMD] "%EXE%" extract --input "%YTD_OUT%" --output "%EXTRACT_DIR%">>"%LOG%"
"%EXE%" extract --input "%YTD_OUT%" --output "%EXTRACT_DIR%" >>"%LOG%" 2>>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :done

>"%PROOF%" echo tool=%TOOL_ID%
>>"%PROOF%" echo exe=%EXE%
>>"%PROOF%" echo testData=%TEST_DATA%
>>"%PROOF%" echo ytd=%YTD_OUT%
>>"%PROOF%" echo inspect=%INSPECT_OUT%
>>"%PROOF%" echo extracted=%EXTRACT_DIR%
>>"%PROOF%" echo result=PASS

echo [PASS] %TOOL_ID% data-driven proof-of-work passed
>>"%LOG%" echo [PASS] %TOOL_ID% data-driven proof-of-work passed

:done
echo [RESULT] smokeTest exit=%RC%>>"%LOG%"
echo [RESULT] smokeTest exit=%RC%
echo ============================================================
if not "%NORTHSTAR_TESTALL%"=="1" pause
exit /b %RC%
