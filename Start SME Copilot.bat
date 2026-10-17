@echo off
rem Website only. Start the independent model service once with scripts\start_shared_llm.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_website.ps1" -OpenBrowser
if errorlevel 1 pause
