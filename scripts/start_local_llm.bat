@echo off
rem Starts the local LLM (llama.cpp server, Vulkan) used by the "local-llamacpp" profile.
rem Settings were benchmarked on an AMD RX 9060 XT 16 GB; see benchmarks/results/local_llm.md.
rem Override the paths without editing this file, e.g.:
rem     set LLAMA_DIR=C:\tools\llama-vulkan
rem     set LLM_MODEL=D:\models\Qwen3.5-9B-Q5_K_M.gguf
setlocal
if not defined LLAMA_DIR set "LLAMA_DIR=D:\llama-vulkan"
if not defined LLM_MODEL set "LLM_MODEL=%LLAMA_DIR%\models\Qwen3.5-9B-Q5_K_M.gguf"
if not defined LLM_PORT set "LLM_PORT=8080"

if not exist "%LLAMA_DIR%\llama-server.exe" (
    echo llama-server.exe not found in %LLAMA_DIR%. Set LLAMA_DIR to your llama.cpp Vulkan build.
    pause
    exit /b 1
)
if not exist "%LLM_MODEL%" (
    echo Model not found: %LLM_MODEL%
    echo Download it from https://huggingface.co/unsloth/Qwen3.5-9B-GGUF or set LLM_MODEL.
    pause
    exit /b 1
)

rem -ngl 99        every layer on the GPU (model + KV cache fit in VRAM, nothing spills to system RAM)
rem -fa off        flash attention made prompt processing ~3x slower on this Vulkan build (measured)
rem -c 16384       enough for system prompt + tool definitions + a long conversation
rem --reasoning off  no hidden "thinking" tokens; the app gets every number from tools anyway
rem -cram 2048     cap the host-RAM prompt cache (default 8 GB is half of a 16 GB PC)
start "Local LLM (llama-server)" /min "%LLAMA_DIR%\llama-server.exe" -m "%LLM_MODEL%" ^
    --host 127.0.0.1 --port %LLM_PORT% -ngl 99 -c 16384 -fa off --reasoning off -cram 2048

echo Loading model, this takes a few seconds...
for /l %%i in (1,1,60) do (
    powershell -NoProfile -Command "try { if ((Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%LLM_PORT%/health -TimeoutSec 2).StatusCode -eq 200) { exit 0 } } catch {} ; exit 1" >nul 2>&1
    if not errorlevel 1 (
        echo Local LLM ready on http://127.0.0.1:%LLM_PORT%
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)
echo The server did not become ready in 60 s. Check the "Local LLM (llama-server)" window.
exit /b 1
