@echo off
rem Like "Start SME Copilot.bat", but phones and computers on the same Wi-Fi can open the website too.
rem Stop any website started by the other launcher first: it keeps its own network setting until restarted.
rem The window stays open so you can read the address to type on the phone.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_website.ps1" -Network -OpenBrowser
pause
