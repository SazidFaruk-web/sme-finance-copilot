@echo off
rem Starts the local CODING model (Gemma 4 26B-A4B, llama.cpp Vulkan) for VS Code's Continue extension.
rem It edits this project's files; it is not the model the Ascent Copilot app itself uses (that is start_local_llm.bat).
rem Only one model fits on the 16 GB GPU at a time, so this stops any running llama-server first.
setlocal
if not defined LLAMA_DIR set "LLAMA_DIR=D:\llama-vulkan"
if not defined MODELS_DIR set "MODELS_DIR=%LLAMA_DIR%\models"
set "PORT=8090"
set "MODEL=%MODELS_DIR%\gemma-4-26B-A4B-it-UD-IQ4_XS.gguf"
set "DRAFT=%MODELS_DIR%\mtp-gemma-4-26B-A4B-it.gguf"

rem 32k context fits next to the 13.6 GB model because Gemma's sliding-window layers keep the KV cache small.
rem Flash attention + q8 KV cache is required for Gemma's prompt-cache reuse; the MTP draft head speeds up writing.
rem -ub 1024 reads files ~2.7x faster than the default 512 (423 vs 153 tok/s on a 12k-token prompt, RX 9060 XT).
rem --reasoning on lets it think before acting; in tests it then fixed failing tests instead of claiming success.
set "ARGS=--host 127.0.0.1 --port %PORT% -ngl 99 -c 32768 -fa on -ctk q8_0 -ctv q8_0 -ub 1024 -b 2048 --jinja -cram 2048 --reasoning on"
set "ARGS=%ARGS% --spec-type draft-mtp -md "%DRAFT%" -ngld 99"

if not exist "%MODEL%" (
    echo Model not found: %MODEL%
    pause
    exit /b 1
)
taskkill /F /IM llama-server.exe >nul 2>&1
start "Local coder (llama-server)" /min "%LLAMA_DIR%\llama-server.exe" -m "%MODEL%" %ARGS%

echo Loading Gemma 4 26B coder, this takes 20-60 seconds...
for /l %%i in (1,1,120) do (
    powershell -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/health -TimeoutSec 2).StatusCode -eq 200) { exit 0 } } catch {} ; exit 1" >nul 2>&1
    if not errorlevel 1 (
        echo Coder ready on http://127.0.0.1:%PORT%  -  open the Continue panel in VS Code and pick "Gemma 4 26B (local coder)".
        exit /b 0
    )
    ping -n 2 127.0.0.1 >nul
)
echo The server did not become ready. Check the "Local coder (llama-server)" window.
exit /b 1
