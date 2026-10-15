@echo off
rem One-click launcher: starts the SME Finance Copilot server (if it isn't
rem already running) and opens the app in your default browser.
rem To stop the server, close the "SME Copilot server" window.
setlocal
cd /d "%~dp0"
set "APP_ENV=demo"
set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%"

call :is_up
if not errorlevel 1 goto open

if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Run these once in this folder first:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements-dev.txt
    pause
    exit /b 1
)

rem Loads demo data only if the database is empty; never wipes existing data.
".venv\Scripts\python.exe" -m sme_copilot.cli seed >nul 2>&1

start "SME Copilot server" /min ".venv\Scripts\python.exe" -m sme_copilot.cli serve --port %PORT%

echo Starting SME Finance Copilot...
for /l %%i in (1,1,30) do (
    call :is_up
    if not errorlevel 1 goto open
    timeout /t 1 /nobreak >nul
)
echo The server did not start within 30 seconds. Check the "SME Copilot server" window for errors.
pause
exit /b 1

:open
rem A fresh query string makes the browser fetch the page again instead of reusing a cached old version.
start "" "%URL%/?t=%RANDOM%%RANDOM%"
exit /b 0

:is_up
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1', %PORT%); exit 0 } catch { exit 1 }"
exit /b %errorlevel%
