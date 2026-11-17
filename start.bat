@echo off
cd /d "%~dp0"
set "CHROME_EXE="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME_EXE if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME_EXE if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined CHROME_EXE for /f "delims=" %%C in ('where chrome.exe 2^>nul') do if not defined CHROME_EXE set "CHROME_EXE=%%C"
if not defined CHROME_EXE (
  echo Google Chrome could not be found. Install Chrome or add chrome.exe to PATH, then try again.
  pause
  exit /b 1
)
call venv\Scripts\activate.bat
start "ERP Server " cmd /k python serve.py
timeout /t 2 /nobreak >nul
start "" "%CHROME_EXE%" --user-data-dir="%TEMP%\MotoSparePartsERP-Chrome" --new-window "http://127.0.0.1:5000"
