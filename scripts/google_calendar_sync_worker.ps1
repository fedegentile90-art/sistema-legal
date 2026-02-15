Param(
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith("#")) { return }
        $parts = $line.Split("=", 2)
        if ($parts.Length -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }
}

$argsList = @("integrations/run_sync_worker.py")
if ($Json) { $argsList += "--json" }

python @argsList
exit $LASTEXITCODE

