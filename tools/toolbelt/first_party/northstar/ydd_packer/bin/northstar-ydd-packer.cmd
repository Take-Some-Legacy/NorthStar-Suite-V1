@echo off
setlocal

set "TOOL_ID=northstar.ydd_packer"
set "TOOL_EXE=northstar-ydd-packer.exe"
set "SELF_DIR=%~dp0"
set "ROOT=%SELF_DIR%..\..\..\..\..\.."

if exist "%SELF_DIR%%TOOL_EXE%" (
  "%SELF_DIR%%TOOL_EXE%" %*
  exit /b %ERRORLEVEL%
)

if exist "%ROOT%\target\release\%TOOL_EXE%" (
  "%ROOT%\target\release\%TOOL_EXE%" %*
  exit /b %ERRORLEVEL%
)

if exist "%ROOT%\tools\target\release\%TOOL_EXE%" (
  "%ROOT%\tools\target\release\%TOOL_EXE%" %*
  exit /b %ERRORLEVEL%
)

for /d %%D in ("%ROOT%\tools\toolsSrc\*") do (
  if exist "%%~D\target\release\%TOOL_EXE%" (
    "%%~D\target\release\%TOOL_EXE%" %*
    exit /b %ERRORLEVEL%
  )
)

echo First-party tool %TOOL_ID% has no built executable yet: %TOOL_EXE% 1^>^&2
echo Install Rust toolchain and build DevSuite first-party tools, then copy the executable to this bin directory. 1^>^&2
exit /b 9009
