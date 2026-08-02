@echo off
rem Stops the ERP server, whether it was started visibly (start.bat) or
rem silently/hidden (pythonw.exe, no console window to close). Finds whatever
rem process is listening on port 5000 and kills it.
set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
    set FOUND=1
)
if "%FOUND%"=="1" (
    echo Stopped.
) else (
    echo Nothing was running on port 5000.
)
pause
