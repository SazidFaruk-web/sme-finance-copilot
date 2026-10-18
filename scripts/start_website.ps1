param(
    # Only this computer can open the website unless -Network is given (or another -HostAddress is chosen).
    [string]$HostAddress = '127.0.0.1',
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [switch]$Network,
    [switch]$OpenBrowser
)

$ErrorActionPreference = 'Stop'
if ($Network) { $HostAddress = '0.0.0.0' }
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
} else {
    Write-Output 'A website was already running on this port; it keeps its earlier network setting until it is restarted.'
}
Write-Output "Website ready: $url"
if ($HostAddress -in @('127.0.0.1', 'localhost', '::1')) {
    Write-Output 'Only this computer can open it. To let phones on the same Wi-Fi open it, use "Start SME Copilot (Wi-Fi).bat".'
} else {
    $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -ExpandProperty IPAddress
    foreach ($a in $addresses) { Write-Output "Other devices on your network: http://${a}:$Port" }
    Write-Output 'Anyone on this network can reach it. With APP_ENV=demo they also see the demo logins; use real passwords before sharing real data.'
}
Write-Output 'The website uses the shared model endpoint from .env and does not start or stop Ollama.'
if ($OpenBrowser) { Start-Process $url }
