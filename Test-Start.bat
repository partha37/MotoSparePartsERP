@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
start "Testing ERP Server " cmd /k python qa/qa_server.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:5099/qa-auto-login
