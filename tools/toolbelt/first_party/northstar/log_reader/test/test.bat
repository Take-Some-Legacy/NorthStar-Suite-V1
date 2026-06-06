@echo off
setlocal
set TOOL=%~dp0..\bin\northstar-log-reader.exe
set DATA=%~dp0..\testData\live_sample.ulog.jsonl
set OUT=%~dp0out
if not exist "%OUT%" mkdir "%OUT%"

"%TOOL%" version > "%OUT%\version.txt" || exit /b 1
"%TOOL%" accepted-inputs > "%OUT%\accepted-inputs.txt" || exit /b 1
"%TOOL%" doctor > "%OUT%\doctor.txt" || exit /b 1
"%TOOL%" read --url "%DATA%" --format jsonl > "%OUT%\read.jsonl" || exit /b 1
"%TOOL%" tail --url "%DATA%" --count 1 --format table > "%OUT%\tail.txt" || exit /b 1
"%TOOL%" live --url http://127.0.0.1:9/logs/live --max-events 1 > "%OUT%\live_unavailable.txt" 2> "%OUT%\live_unavailable.err"
"%TOOL%" html --no-open --out "%OUT%\log-reader-empty.html" > "%OUT%\html-empty.txt" || exit /b 1
"%TOOL%" html --no-open --url http://127.0.0.1:8765/logs --out "%OUT%\log-reader-prefilled.html" > "%OUT%\html-prefilled.txt" || exit /b 1

findstr /C:"source_url=http://127.0.0.1:8765/logs" "%OUT%\html-empty.txt" >nul || exit /b 1
findstr /C:"source_url=http://127.0.0.1:8765/logs" "%OUT%\html-prefilled.txt" >nul || exit /b 1

echo [OK] northstar-log-reader local test passed
exit /b 0
