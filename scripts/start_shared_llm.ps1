param(
    [string]$BaseModel = 'gemma4:12b',
    [string]$ModelName = 'sme-copilot',
    [ValidateRange(1, 65535)][int]$Port = 11434,
    [ValidateRange(4096, 65536)][int]$ContextLength = 16384,
    [switch]$Restart,
    [switch]$AllowCpu
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot 'data'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$serverUrl = "http://127.0.0.1:$Port"
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaPath = if ($ollamaCommand) { $ollamaCommand.Source } else {
    Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
}
if (-not (Test-Path -LiteralPath $ollamaPath)) {
    throw 'Ollama is not installed. Install Ollama, pull gemma4:12b, then run this script again.'
}

# Initialize and probe CUDA before starting Ollama. A daemon keeps its GPU discovery result
# for its lifetime; a CPU-only daemon must be restarted after repairing its GPU environment.
$ollamaLib = Join-Path (Split-Path -Parent $ollamaPath) 'lib\ollama'
$cudaReady = $false
$nvidiaCommand = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaCommand) {
    $gpuNames = & $nvidiaCommand.Source --query-gpu=name --format=csv,noheader
    if ($LASTEXITCODE -eq 0 -and $gpuNames) {
        $originalPath = $env:PATH
        foreach ($backend in @('cuda_v13', 'cuda_v12')) {
            $cudaDir = Join-Path $ollamaLib $backend
            $cudaDll = Join-Path $cudaDir 'ggml-cuda.dll'
            if (-not (Test-Path -LiteralPath $cudaDll)) { continue }
            $env:PATH = "$ollamaLib;$cudaDir;$originalPath"
            $env:GGML_BACKEND_PATH = $cudaDll
            $env:GGML_CUDA_INIT = '1'
            $probeOutput = & (Join-Path $ollamaLib 'llama-server.exe') --list-devices --offline
            if ($LASTEXITCODE -eq 0 -and ($probeOutput -match 'CUDA\d+:')) {
                $cudaReady = $true
                $env:OLLAMA_VULKAN = '0' # use the verified CUDA backend on NVIDIA laptops
                Write-Output "GPU probe passed ($backend): $($probeOutput -join ' ')"
                break
            }
        }
        if (-not $cudaReady) {
            $env:PATH = $originalPath
            Remove-Item Env:GGML_BACKEND_PATH,Env:GGML_CUDA_INIT -ErrorAction SilentlyContinue
            if (-not $AllowCpu) { throw 'CUDA initialization failed. Check the NVIDIA driver and Microsoft VC++ x64 runtime. Use -AllowCpu only for an intentional CPU fallback.' }
        }
    }
}

if ($Restart) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $daemon = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        if ($daemon.ExecutablePath -ne $ollamaPath) { throw "Port $Port belongs to another application; refusing to stop it." }
        $stopId = $daemon.ProcessId
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($daemon.ParentProcessId)"
        if ($parent -and $parent.ExecutablePath -eq (Join-Path (Split-Path -Parent $ollamaPath) 'ollama app.exe')) {
            $stopId = $parent.ProcessId # tray app otherwise restarts its daemon with the old environment
        }
        & taskkill /PID $stopId /T /F
        if ($LASTEXITCODE -ne 0) { throw 'Could not restart the shared Ollama service.' }
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            try { Invoke-RestMethod "$serverUrl/api/version" -TimeoutSec 1 | Out-Null } catch { break }
            Start-Sleep -Milliseconds 500
        }
    }
}

# Reuse a healthy central daemon. The website is never stopped by this script.
try { $tags = Invoke-RestMethod "$serverUrl/api/tags" -TimeoutSec 3 } catch { $tags = $null }
if ($null -eq $tags) {
    $env:OLLAMA_HOST = "127.0.0.1:$Port"
    $env:OLLAMA_NUM_PARALLEL = '1' # requests queue at one shared model instead of copying it for every user
    $env:OLLAMA_MAX_QUEUE = '64'
    $env:OLLAMA_KEEP_ALIVE = '-1'
    $env:OLLAMA_FLASH_ATTENTION = 'true'
    $env:OLLAMA_KV_CACHE_TYPE = 'q8_0' # keep the 16K context within laptop VRAM
    Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $projectRoot `
        -RedirectStandardOutput (Join-Path $runtimeDir 'llm.stdout.log') `
        -RedirectStandardError (Join-Path $runtimeDir 'llm.stderr.log') | Out-Null
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try { $tags = Invoke-RestMethod "$serverUrl/api/tags" -TimeoutSec 2; break } catch { }
    }
    if ($null -eq $tags) { throw 'Ollama did not start. See data/llm.stderr.log.' }
}

if ($BaseModel -notin @($tags.models.name)) {
    throw "Model '$BaseModel' is not installed. Run: ollama pull $BaseModel"
}

# An alias reuses the installed model blobs. It sets context for the OpenAI-compatible API,
# which does not accept a per-request num_ctx. No second model download is needed.
$modelFile = Join-Path $runtimeDir 'shared-llm.Modelfile'
@("FROM $BaseModel", "PARAMETER num_ctx $ContextLength", 'PARAMETER temperature 0.2') |
    Set-Content -LiteralPath $modelFile -Encoding utf8
$env:OLLAMA_HOST = "127.0.0.1:$Port"
& $ollamaPath create $ModelName -f $modelFile
if ($LASTEXITCODE -ne 0) { throw 'Could not configure the shared model.' }

Write-Output "Loading shared model '$ModelName' ($BaseModel, $ContextLength context)..."
$warmup = @{model=$ModelName; prompt=''; stream=$false; think=$false; keep_alive=-1} | ConvertTo-Json
Invoke-RestMethod "$serverUrl/api/generate" -Method Post -ContentType 'application/json' -Body $warmup -TimeoutSec 180 | Out-Null
$loaded = Invoke-RestMethod "$serverUrl/api/ps" -TimeoutSec 5
$modelTag = if ($ModelName.Contains(':')) { $ModelName } else { "${ModelName}:latest" }
$running = $loaded.models | Where-Object { $_.name -eq $modelTag } | Select-Object -First 1
if ($null -eq $running) { throw "Ollama did not keep '$ModelName' loaded." }
if ([long]$running.size_vram -le 0 -and -not $AllowCpu) {
    throw 'The shared model is running on CPU. Run this script with -Restart to refresh GPU discovery; use -AllowCpu only for an intentional CPU fallback.'
}
Write-Output ("GPU acceleration verified (Ollama reports {0:N0} MiB on GPU)." -f ($running.size_vram / 1MB))
if ($cudaReady) {
    # Speculative-model accounting can omit the main model in /api/ps; show the device reading too.
    & $nvidiaCommand.Source --query-gpu=name,memory.used,memory.total --format=csv,noheader
}
Write-Output "Shared LLM ready: $serverUrl/v1 (model: $ModelName)"
Write-Output 'It runs independently. Starting, stopping or restarting the website does not stop this service.'
