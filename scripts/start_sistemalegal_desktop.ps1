param()

$ErrorActionPreference = "Stop"
$RepoDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoDir

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path $Path)) {
        return
    }
    foreach ($lineRaw in Get-Content -Path $Path) {
        $line = [string]$lineRaw
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith("#")) {
            continue
        }
        $idx = $trimmed.IndexOf("=")
        if ($idx -le 0) {
            continue
        }
        $name = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            if ($value.Length -ge 2) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

Import-DotEnv -Path (Join-Path $RepoDir ".env")

[Environment]::SetEnvironmentVariable("VG_AUTH_REQUIRED", "1", "Process")
[Environment]::SetEnvironmentVariable("VG_RBAC_STRICT", "1", "Process")
[Environment]::SetEnvironmentVariable("VG_EXPORT_STRICT", "1", "Process")
[Environment]::SetEnvironmentVariable("VG_AUTO_SAVE_CHANGES", "1", "Process")
[Environment]::SetEnvironmentVariable("VG_RELEASE_GATE_MODE", "read_only", "Process")

$dsn = [Environment]::GetEnvironmentVariable("DATABASE_URL", "Process")
if ([string]::IsNullOrWhiteSpace($dsn)) {
    Write-Host "ERROR: DATABASE_URL no esta configurada (ni en .env ni en variables del sistema)." -ForegroundColor Red
    Write-Host "Configure DATABASE_URL y vuelva a ejecutar el acceso directo." -ForegroundColor Yellow
    Read-Host "Presione Enter para cerrar"
    exit 1
}

$runner = Join-Path $RepoDir "RUN_ERP.cmd"
if (-not (Test-Path $runner)) {
    Write-Host "ERROR: No se encontro RUN_ERP.cmd en el repositorio." -ForegroundColor Red
    Read-Host "Presione Enter para cerrar"
    exit 1
}

& $runner
exit $LASTEXITCODE
