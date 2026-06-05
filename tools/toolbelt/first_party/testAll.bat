@echo off

setlocal EnableExtensions EnableDelayedExpansion



set "FIRST_PARTY_ROOT=%~dp0"

set "FIRST_PARTY_ROOT=%FIRST_PARTY_ROOT:~0,-1%"

set "NORTHSTAR_ROOT=%FIRST_PARTY_ROOT%\..\.."

set "RESULT_DIR=%FIRST_PARTY_ROOT%\.testAll"

set "RESULT_FILE=%RESULT_DIR%\last-run.txt"

set "TOTAL=0"

set "PASS=0"

set "FAIL=0"



if not exist "%RESULT_DIR%" mkdir "%RESULT_DIR%" > nul 2> nul



> "%RESULT_FILE%" echo [TESTALL] First-party North Star tool contract run

>> "%RESULT_FILE%" echo [INFO] first_party_root=%FIRST_PARTY_ROOT%

>> "%RESULT_FILE%" echo [INFO] checks=version accepted-inputs doctor local-test

>> "%RESULT_FILE%" echo.



echo ============================================================

echo [TESTALL] First-party North Star tool contract run

echo [INFO] first_party_root=%FIRST_PARTY_ROOT%

echo [INFO] checks=version accepted-inputs doctor local-test

echo ============================================================

echo.



for /d %%D in ("%FIRST_PARTY_ROOT%\northstar\*") do (

  set "PKG=%%~fD"

  set "NAME=%%~nxD"

  set "DESC=!PKG!\tool.json"
  set "DISABLED_DESC=!PKG!\tool.disabled.json"

  if not exist "!DESC!" if exist "!DISABLED_DESC!" (
    echo ------------------------------------------------------------
    echo [SKIP] !NAME! disabled
    echo [SKIP] !NAME! disabled>> "%RESULT_FILE%"
    echo.>> "%RESULT_FILE%"
    goto :ContinueTool
  )

  set "EXE="



  if exist "!PKG!\bin\northstar-!NAME!.exe" set "EXE=!PKG!\bin\northstar-!NAME!.exe"

  if not defined EXE if exist "!PKG!\bin\northstar-!NAME:_packer=-packer!.exe" set "EXE=!PKG!\bin\northstar-!NAME:_packer=-packer!.exe"



  rem Explicit fallback map for current tool names.

  if /i "!NAME!"=="hasher" set "EXE=!PKG!\bin\northstar-hasher.exe"

  if /i "!NAME!"=="neftd_packer" set "EXE=!PKG!\bin\northstar-neftd-packer.exe"

  if /i "!NAME!"=="nemat_packer" set "EXE=!PKG!\bin\northstar-nemat-packer.exe"

  if /i "!NAME!"=="nepak_packer" set "EXE=!PKG!\bin\northstar-nepak-packer.exe"

  if /i "!NAME!"=="neui_packer" set "EXE=!PKG!\bin\northstar-neui-packer.exe"

  if /i "!NAME!"=="ydd_packer" set "EXE=!PKG!\bin\northstar-ydd-packer.exe"

  if /i "!NAME!"=="ytd_packer" set "EXE=!PKG!\bin\northstar-ytd-packer.exe"

  if /i "!NAME!"=="ytyp_packer" set "EXE=!PKG!\bin\northstar-ytyp-packer.exe"
  if /i "!NAME!"=="symbol_extract" set "EXE=!PKG!\bin\northstar-symbol-extract.exe"
  if /i "!NAME!"=="log_reader" set "EXE=!PKG!\bin\northstar-log-reader.exe"



  echo ------------------------------------------------------------

  echo [TOOL] !NAME!

  echo [TOOL] !NAME!>> "%RESULT_FILE%"



  if not exist "!DESC!" (

    set /a FAIL+=1

    echo [FAIL] missing descriptor: !DESC!

    echo [FAIL] missing descriptor: !DESC!>> "%RESULT_FILE%"

  ) else if not exist "!EXE!" (

    set /a FAIL+=1

    echo [FAIL] missing executable: !EXE!

    echo [FAIL] missing executable: !EXE!>> "%RESULT_FILE%"

  ) else (

    call :RunCheck "!NAME!" "version" "!EXE!" version

    call :RunCheck "!NAME!" "accepted-inputs" "!EXE!" accepted-inputs

    call :RunCheck "!NAME!" "doctor" "!EXE!" doctor



    if exist "!PKG!\test\test.bat" (

      set /a TOTAL+=1

      echo [RUN] local-test !PKG!\test\test.bat

      echo [RUN] local-test !PKG!\test\test.bat>> "%RESULT_FILE%"

      cmd.exe /d /q /c "set NORTHSTAR_TESTALL=1&& call "!PKG!\test\test.bat""

      set "RC=!ERRORLEVEL!"

      if "!RC!"=="0" (

        set /a PASS+=1

        echo [PASS] !NAME! local-test

        echo [PASS] !NAME! local-test>> "%RESULT_FILE%"

      ) else (

        set /a FAIL+=1

        echo [FAIL] !NAME! local-test exit=!RC!

        echo [FAIL] !NAME! local-test exit=!RC!>> "%RESULT_FILE%"

      )

    ) else (

      echo [WARN] !NAME! has no local test\test.bat

      echo [WARN] !NAME! has no local test\test.bat>> "%RESULT_FILE%"

    )

  )

  echo.>> "%RESULT_FILE%"

)



echo ============================================================

echo [SUMMARY] checks=%TOTAL% pass=%PASS% fail=%FAIL%

echo [RESULT] report=%RESULT_FILE%

if "%FAIL%"=="0" (

  if "%TOTAL%"=="0" (

    echo [FAIL] first_party testAll found no checks

    set "RC=1"

  ) else (

    echo [PASS] first_party tool contract passed

    set "RC=0"

  )

) else (

  echo [FAIL] first_party tool contract failed

  set "RC=1"

)

echo ============================================================

>> "%RESULT_FILE%" echo [SUMMARY] checks=%TOTAL% pass=%PASS% fail=%FAIL%

>> "%RESULT_FILE%" echo [RESULT] exit=%RC%

if not "%NORTHSTAR_TESTALL%"=="1" pause

exit /b %RC%



:RunCheck

set "TOOL_NAME=%~1"

set "CHECK_NAME=%~2"

set "CHECK_EXE=%~3"

set "CHECK_ARG=%~4"

set /a TOTAL+=1

echo [RUN] %TOOL_NAME% %CHECK_NAME%

echo [RUN] %TOOL_NAME% %CHECK_NAME%>> "%RESULT_FILE%"

"%CHECK_EXE%" %CHECK_ARG% > "%RESULT_DIR%\%TOOL_NAME%-%CHECK_NAME%.txt" 2>&1

set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (

  set /a PASS+=1

  echo [PASS] %TOOL_NAME% %CHECK_NAME%

  echo [PASS] %TOOL_NAME% %CHECK_NAME%>> "%RESULT_FILE%"

  type "%RESULT_DIR%\%TOOL_NAME%-%CHECK_NAME%.txt"

) else (

  set /a FAIL+=1

  echo [FAIL] %TOOL_NAME% %CHECK_NAME% exit=%RC%

  echo [FAIL] %TOOL_NAME% %CHECK_NAME% exit=%RC%>> "%RESULT_FILE%"

  type "%RESULT_DIR%\%TOOL_NAME%-%CHECK_NAME%.txt"

)

exit /b 0

