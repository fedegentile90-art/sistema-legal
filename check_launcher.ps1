$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = 8501
$VbsPath = Join-Path $RepoDir "RUN_ERP.vbs"
$LogDir = Join-Path $RepoDir "logs"
$Log = Join-Path $LogDir "launcher.log"

function Test-Port([int]$PortNumber, [int]$TimeoutMs = 400) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1", $PortNumber, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if (-not $ok) {
            return $false
        }
        $null = $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

if (-not (Test-Path $VbsPath)) {
    Write-Error "No existe RUN_ERP.vbs en $RepoDir"
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

Start-Process -FilePath "wscript.exe" -ArgumentList @("""$VbsPath""") -WindowStyle Hidden
Start-Sleep -Seconds 3

if (-not (Test-Port -PortNumber $Port)) {
    Write-Error "FAIL: localhost:$Port no responde tras ejecutar RUN_ERP.vbs"
}

Write-Host "OK: launcher activo, puerto $Port responde."
if (Test-Path $Log) {
    Write-Host "Log: $Log"
}
