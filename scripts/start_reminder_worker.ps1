param([switch]$Once, [switch]$Report)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the project virtual environment and install requirements first.' }
Push-Location $projectRoot
try {
    $workerArgs = @('-m', 'sme_copilot.pilot.worker')
    if ($Once) { $workerArgs += '--once' }
    if ($Report) { $workerArgs += '--report' }
    & $pythonPath @workerArgs
    if ($LASTEXITCODE -ne 0) { throw "Reminder worker exited with code $LASTEXITCODE" }
} finally { Pop-Location }
