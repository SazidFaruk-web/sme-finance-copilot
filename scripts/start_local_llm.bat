@echo off
rem Starts the local LLM (llama.cpp server, Vulkan) for the app's local profiles.
rem   scripts\start_local_llm.bat            Gemma 4 12B  (default; profile local-llamacpp)
rem   scripts\start_local_llm.bat qwen14b    Qwen3-14B    (backup;  profile local-qwen14b)
rem Settings were benchmarked on an AMD RX 9060 XT 16 GB: see benchmarks/results/local_models.md.
rem Override paths without editing this file, e.g.  set LLAMA_DIR=C:\tools\llama-vulkan
setlocal
if not defined LLAMA_DIR set "LLAMA_DIR=D:\llama-vulkan"
if not defined MODELS_DIR set "MODELS_DIR=%LLAMA_DIR%\models"
if not defined LLM_PORT set "LLM_PORT=8080"
set "CHOICE=%~1"
if "%CHOICE%"=="" set "CHOICE=gemma"

rem Common: every layer on the GPU (nothing spills to system RAM), 16k context (system prompt + tools +
rem conversation), no hidden thinking tokens, host-RAM prompt cache capped at 2 GB (default 8 GB is half
rem of a 16 GB PC).
set "COMMON=--host 127.0.0.1 --port %LLM_PORT% -ngl 99 -c 16384 --reasoning off -cram 2048"

if /i "%CHOICE%"=="gemma" (
    set "LLM_MODEL=%MODELS_DIR%\gemma-4-12b-it-Q4_K_M.gguf"
    set "DRAFT=%MODELS_DIR%\mtp-gemma-4-12B-it-Q8_0.gguf"
    rem Gemma uses sliding-window attention: flash attention ON is required for prompt-cache reuse;
    rem the MTP draft head (speculative decoding) gives ~1.5-1.8x generation speed.
    set "FLAGS=-fa on -ctk q8_0 -ctv q8_0 --spec-type draft-mtp -ngld 99"
    set "PROFILE=local-llamacpp"
) else if /i "%CHOICE%"=="qwen14b" (
    set "LLM_MODEL=%MODELS_DIR%\Qwen3-14B-Q4_K_M.gguf"
    set "DRAFT="
    rem Flash attention made prompt processing ~3x slower for Qwen on this Vulkan build.
    set "FLAGS=-fa off"
    set "PROFILE=local-qwen14b"
) else (
    echo Unknown model "%CHOICE%". Use: gemma ^| qwen14b
    exit /b 1
)

if not exist "%LLAMA_DIR%\llama-server.exe" (
    echo llama-server.exe not found in %LLAMA_DIR%. Set LLAMA_DIR to your llama.cpp Vulkan build.
    pause
    exit /b 1
)
if not exist "%LLM_MODEL%" (
    echo Model not found: %LLM_MODEL%
    echo See README "Local model" for the download links, or set MODELS_DIR.
    pause
    exit /b 1
)
set "DRAFT_ARG="
if defined DRAFT (
    if not exist "%DRAFT%" (
        echo Draft model not found: %DRAFT%  - starting without speculative decoding.
        set "FLAGS=-fa on -ctk q8_0 -ctv q8_0"
    ) else (
        set "DRAFT_ARG=-md "%DRAFT%""
    )
)

rem Only one model fits on the GPU at a time: stop any llama-server that is already running.
taskkill /F /IM llama-server.exe >nul 2>&1

start "Local LLM (llama-server)" /min "%LLAMA_DIR%\llama-server.exe" -m "%LLM_MODEL%" %COMMON% %FLAGS% %DRAFT_ARG%

echo Loading %CHOICE%, this takes 10-30 seconds...
for /l %%i in (1,1,90) do (
    powershell -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%LLM_PORT%/health -TimeoutSec 2).StatusCode -eq 200) { exit 0 } } catch {} ; exit 1" >nul 2>&1
    if not errorlevel 1 (
        echo Local LLM ready on http://127.0.0.1:%LLM_PORT%  -  pick "%PROFILE%" in the app's Model menu
        echo or set LLM_PROFILE=%PROFILE% in .env.
        exit /b 0
    )
    ping -n 2 127.0.0.1 >nul
)
echo The server did not become ready in 90 s. Check the "Local LLM (llama-server)" window.
exit /b 1
