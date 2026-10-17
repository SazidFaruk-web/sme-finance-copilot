param(
    [string]$HostAddress = '0.0.0.0',
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [switch]$OpenBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$runtimeDir = Join-Path $projectRoot 'data'
$url = "http://127.0.0.1:$Port"
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Install the project virtual environment first; see README.' }
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2 } catch { $health = $null }
if ($null -eq $health) {
    $server = Start-Process -FilePath $pythonPath -ArgumentList '-m','sme_copilot.cli','serve','--host',$HostAddress,'--port',$Port `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeDir 'website.stdout.log') `
        -RedirectStandardError (Join-Path $runtimeDir 'website.stderr.log')
    $server.Id | Set-Content -LiteralPath (Join-Path $runtimeDir 'website.pid')
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try { $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2; break } catch { }
    }
    if ($null -eq $health) { throw 'Website did not start. See data/website.stderr.log.' }
}
Write-Output "Website ready: $url"
Write-Output "Other users on your network: http://<this-computer-IP>:$Port"
Write-Output 'The website uses the shared model endpoint from .env and does not start or stop Ollama.'
if ($OpenBrowser) { Start-Process $url }
