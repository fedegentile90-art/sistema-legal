param(
    [switch]$DailyOps
)

$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = 8501
$Url = "http://localhost:$Port"
$PythonVenv = Join-Path $RepoDir ".venv\Scripts\python.exe"
$Python = if (Test-Path $PythonVenv) { $PythonVenv } else { "python" }
$LogDir = Join-Path $RepoDir "logs"
$LauncherLog = Join-Path $LogDir "launcher.log"
$OpsLog = Join-Path $LogDir ("ops_{0}.log" -f (Get-Date).ToString("yyyyMMdd"))
$StepTimeoutSec = 1200

$EXIT_OK = 0
$EXIT_LAUNCHER_FAIL = 10
$EXIT_NIGHTLY_FAIL = 20
$EXIT_GATE_FAIL = 30
$EXIT_RUNTIME_FAIL = 99

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-LauncherLog([string]$Msg) {
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss.fff")
    Add-Content -Path $LauncherLog -Value "[$stamp] $Msg"
}

function Write-OpsLog([string]$Msg) {
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss.fff")
    $line = "[$stamp] $Msg"
    Add-Content -Path $OpsLog -Value $line
    Write-Host $line
}

function Convert-ToObsValue([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "-"
    }
    $text = [string]$Value
    $text = $text.Replace("`r", " ").Replace("`n", " ")
    $text = ($text -replace "\s+", " ").Trim()
    $text = $text.Replace('"', "'")
    return ('"' + $text + '"')
}

function New-RunId {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
    $token = [Guid]::NewGuid().ToString("N").Substring(0, 8)
    return ("ops-{0}-{1}" -f $stamp, $token)
}

function Write-OpsObs(
    [string]$RunId,
    [string]$Stage,
    [string]$Suite,
    [string]$Status,
    [string]$Detail = ""
) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
    $line = "[OBS] ts={0} run_id={1} stage={2} suite={3} status={4} detail={5}" -f `
        (Convert-ToObsValue $ts), `
        (Convert-ToObsValue $RunId), `
        (Convert-ToObsValue $Stage), `
        (Convert-ToObsValue $Suite), `
        (Convert-ToObsValue $Status), `
        (Convert-ToObsValue $Detail)
    Write-OpsLog $line
}

function Get-PositiveIntEnv([string]$Name, [int]$DefaultValue) {
    $raw = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return [int]$DefaultValue
    }
    $parsed = 0
    if ([int]::TryParse($raw, [ref]$parsed) -and $parsed -gt 0) {
        return [int]$parsed
    }
    return [int]$DefaultValue
}

function Convert-ToCmdArg([string]$Value) {
    if ($null -eq $Value) {
        return '""'
    }
    $text = [string]$Value
    if ([string]::IsNullOrEmpty($text)) {
        return '""'
    }
    if ($text -match '[\s"&|<>^()]') {
        $escaped = $text.Replace('"', '\"')
        return '"' + $escaped + '"'
    }
    return $text
}

function Test-Port([int]$PortNumber, [int]$TimeoutMs = 350) {
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

function Invoke-PythonStep([string]$StepName, [string[]]$StepArgs, [int]$TimeoutSec, [string]$RunId = "") {
    Write-OpsLog ("[RUN] {0}: {1} {2}" -f $StepName, $Python, ($StepArgs -join " "))
    Write-OpsObs -RunId $RunId -Stage "step_start" -Suite $StepName -Status "RUN" -Detail ("timeout_sec={0}" -f $TimeoutSec)
    $token = [Guid]::NewGuid().ToString("N")
    $tmpOut = Join-Path $env:TEMP ("vg_ops_{0}_{1}.out" -f $StepName, $token)
    $tmpErr = Join-Path $env:TEMP ("vg_ops_{0}_{1}.err" -f $StepName, $token)
    $timedOut = $false
    $code = -1
    $capturedLines = New-Object System.Collections.Generic.List[string]
    $previousRunId = [Environment]::GetEnvironmentVariable("VG_RUN_ID", "Process")

    try {
        if (-not [string]::IsNullOrWhiteSpace($RunId)) {
            [Environment]::SetEnvironmentVariable("VG_RUN_ID", $RunId, "Process")
        }

        $cmdParts = @('"' + $Python + '"')
        foreach ($arg in $StepArgs) {
            $cmdParts += (Convert-ToCmdArg -Value $arg)
        }
        $cmdLine = ($cmdParts -join " ")

        $proc = Start-Process `
            -FilePath "cmd.exe" `
            -ArgumentList @("/d", "/s", "/c", $cmdLine) `
            -WorkingDirectory $RepoDir `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $tmpOut `
            -RedirectStandardError $tmpErr

        $waitMs = [int]([Math]::Max(1, $TimeoutSec) * 1000)
        $finished = $proc.WaitForExit($waitMs)
        if (-not $finished) {
            $timedOut = $true
            Write-OpsLog ("[TIMEOUT] {0} excedio {1}s. Terminando proceso PID={2}." -f $StepName, $TimeoutSec, $proc.Id)
            try {
                Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            } catch {
                Write-OpsLog ("[WARN] No se pudo terminar PID={0}: {1}" -f $proc.Id, $_.Exception.Message)
            }
            try {
                $null = $proc.WaitForExit(5000)
            } catch {
            }
        } else {
            # Con stdout/stderr redirigidos, asegurar fin completo antes de leer ExitCode.
            try {
                $null = $proc.WaitForExit()
            } catch {
            }
        }

        if (Test-Path $tmpOut) {
            Get-Content $tmpOut | ForEach-Object {
                $capturedLines.Add([string]$_) | Out-Null
                Add-Content -Path $OpsLog -Value $_
                Write-Host $_
            }
        }
        if (Test-Path $tmpErr) {
            Get-Content $tmpErr | ForEach-Object {
                $capturedLines.Add([string]$_) | Out-Null
                Add-Content -Path $OpsLog -Value $_
                Write-Host $_
            }
        }
        if ($timedOut) {
            $code = 124
        } else {
            try {
                $proc.Refresh()
            } catch {
            }
            $code = [int]$proc.ExitCode
            if ($code -eq 0) {
                $combined = ($capturedLines -join "`n")
                if ($combined -match "\[FAIL\]" -or $combined -match "RELEASE QA GATE: FAIL" -or $combined -match "ENV CONTRACT: FAIL") {
                    Write-OpsLog ("[WARN] {0} reporto señales de fallo en output con exit=0. Se fuerza exit=1." -f $StepName)
                    $code = 1
                }
            }
        }
    } finally {
        [Environment]::SetEnvironmentVariable("VG_RUN_ID", $previousRunId, "Process")
        if (Test-Path $tmpOut) {
            Remove-Item $tmpOut -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path $tmpErr) {
            Remove-Item $tmpErr -Force -ErrorAction SilentlyContinue
        }
    }

    if ($timedOut) {
        Write-OpsLog ("[FAIL] {0} exit={1} reason=TIMEOUT>{2}s" -f $StepName, $code, $TimeoutSec)
        Write-OpsObs -RunId $RunId -Stage "step_end" -Suite $StepName -Status "TIMEOUT" -Detail ("exit={0}" -f $code)
    } elseif ($code -eq 0) {
        Write-OpsLog ("[PASS] {0} exit={1}" -f $StepName, $code)
        Write-OpsObs -RunId $RunId -Stage "step_end" -Suite $StepName -Status "PASS" -Detail ("exit={0}" -f $code)
    } else {
        Write-OpsLog ("[FAIL] {0} exit={1}" -f $StepName, $code)
        Write-OpsObs -RunId $RunId -Stage "step_end" -Suite $StepName -Status "FAIL" -Detail ("exit={0}" -f $code)
    }
    return [int]$code
}

function Run-Launcher {
    Set-Location $RepoDir

    if (Test-Port -PortNumber $Port) {
        Write-LauncherLog "Server ya activo, abriendo browser"
        Start-Process $Url | Out-Null
        return $EXIT_OK
    }

    Write-LauncherLog "Iniciando server streamlit..."
    $args = @(
        "-m", "streamlit", "run", "app.py",
        "--server.address=localhost",
        "--server.port=8501",
        "--logger.level=info"
    )

    Start-Process `
        -FilePath $Python `
        -ArgumentList $args `
        -WorkingDirectory $RepoDir `
        -WindowStyle Hidden | Out-Null

    for ($i = 0; $i -lt 24; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Port -PortNumber $Port) {
            Write-LauncherLog "Server arriba, abriendo browser"
            Start-Process $Url | Out-Null
            return $EXIT_OK
        }
    }

    Write-LauncherLog "Timeout esperando puerto"
    Start-Process "notepad.exe" -ArgumentList @($LauncherLog) | Out-Null
    return $EXIT_LAUNCHER_FAIL
}

function Run-DailyOps {
    Set-Location $RepoDir
    $StepTimeoutSec = Get-PositiveIntEnv -Name "VG_STEP_TIMEOUT_SEC" -DefaultValue 1200
    $runId = [Environment]::GetEnvironmentVariable("VG_RUN_ID", "Process")
    if ([string]::IsNullOrWhiteSpace($runId)) {
        $runId = New-RunId
    }
    [Environment]::SetEnvironmentVariable("VG_RUN_ID", $runId, "Process")
    Write-OpsLog "=== DAILY OPS START ==="
    Write-OpsLog ("RepoDir: {0}" -f $RepoDir)
    Write-OpsLog ("Run ID: {0} (env VG_RUN_ID)" -f $runId)
    Write-OpsLog ("Step timeout: {0}s (env VG_STEP_TIMEOUT_SEC)" -f $StepTimeoutSec)
    Write-OpsObs -RunId $runId -Stage "daily_ops_start" -Suite "daily_ops" -Status "RUN"

    $envCode = Invoke-PythonStep -StepName "env_contract_daily_ops" -StepArgs @("db/env_contract.py", "--profile", "daily_ops") -TimeoutSec $StepTimeoutSec -RunId $runId
    if ($envCode -eq 124) {
        Write-OpsLog "[CUT] env_contract_daily_ops timeout. Se corta flujo antes de nightly_audit."
        Write-OpsObs -RunId $runId -Stage "daily_ops_cut" -Suite "env_contract_daily_ops" -Status "TIMEOUT" -Detail "Se corta flujo antes de nightly_audit"
        Write-OpsObs -RunId $runId -Stage "daily_ops_end" -Suite "daily_ops" -Status "FAIL" -Detail ("exit={0}" -f $EXIT_NIGHTLY_FAIL)
        Write-OpsLog ("=== DAILY OPS END (FAIL:{0}) ===" -f $EXIT_NIGHTLY_FAIL)
        return $EXIT_NIGHTLY_FAIL
    }
    if ($envCode -ne 0) {
        Write-OpsLog "[CUT] env_contract_daily_ops fallido. Se corta flujo antes de nightly_audit."
        Write-OpsObs -RunId $runId -Stage "daily_ops_cut" -Suite "env_contract_daily_ops" -Status "FAIL" -Detail "Se corta flujo antes de nightly_audit"
        Write-OpsObs -RunId $runId -Stage "daily_ops_end" -Suite "daily_ops" -Status "FAIL" -Detail ("exit={0}" -f $EXIT_NIGHTLY_FAIL)
        Write-OpsLog ("=== DAILY OPS END (FAIL:{0}) ===" -f $EXIT_NIGHTLY_FAIL)
        return $EXIT_NIGHTLY_FAIL
    }

    $nightlyCode = Invoke-PythonStep -StepName "nightly_audit" -StepArgs @("db/nightly_audit.py") -TimeoutSec $StepTimeoutSec -RunId $runId
    if ($nightlyCode -eq 124) {
        Write-OpsLog "[CUT] nightly_audit timeout. Se corta flujo antes de release_gate."
        Write-OpsObs -RunId $runId -Stage "daily_ops_cut" -Suite "nightly_audit" -Status "TIMEOUT" -Detail "Se corta flujo antes de release_gate"
        Write-OpsObs -RunId $runId -Stage "daily_ops_end" -Suite "daily_ops" -Status "FAIL" -Detail ("exit={0}" -f $EXIT_NIGHTLY_FAIL)
        Write-OpsLog ("=== DAILY OPS END (FAIL:{0}) ===" -f $EXIT_NIGHTLY_FAIL)
        return $EXIT_NIGHTLY_FAIL
    }
    if ($nightlyCode -ne 0) {
        Write-OpsLog "[CUT] nightly_audit fallido. Se corta flujo antes de release_gate."
        Write-OpsObs -RunId $runId -Stage "daily_ops_cut" -Suite "nightly_audit" -Status "FAIL" -Detail "Se corta flujo antes de release_gate"
        Write-OpsObs -RunId $runId -Stage "daily_ops_end" -Suite "daily_ops" -Status "FAIL" -Detail ("exit={0}" -f $EXIT_NIGHTLY_FAIL)
        Write-OpsLog ("=== DAILY OPS END (FAIL:{0}) ===" -f $EXIT_NIGHTLY_FAIL)
        return $EXIT_NIGHTLY_FAIL
    }

    $gateCode = Invoke-PythonStep -StepName "release_gate" -StepArgs @("db/release_gate.py") -TimeoutSec $StepTimeoutSec -RunId $runId
    if ($gateCode -eq 124) {
        Write-OpsLog "[CUT] release_gate timeout."
        Write-OpsObs -RunId $runId -Stage "daily_ops_cut" -Suite "release_gate" -Status "TIMEOUT"
        Write-OpsObs -RunId $runId -Stage "daily_ops_end" -Suite "daily_ops" -Status "FAIL" -Detail ("exit={0}" -f $EXIT_GATE_FAIL)
        Write-OpsLog ("=== DAILY OPS END (FAIL:{0}) ===" -f $EXIT_GATE_FAIL)
        return $EXIT_GATE_FAIL
    }
    if ($gateCode -ne 0) {
        Write-OpsObs -RunId $runId -Stage "daily_ops_end" -Suite "daily_ops" -Status "FAIL" -Detail ("exit={0}" -f $EXIT_GATE_FAIL)
        Write-OpsLog ("=== DAILY OPS END (FAIL:{0}) ===" -f $EXIT_GATE_FAIL)
        return $EXIT_GATE_FAIL
    }

    Write-OpsObs -RunId $runId -Stage "daily_ops_end" -Suite "daily_ops" -Status "PASS" -Detail ("exit={0}" -f $EXIT_OK)
    Write-OpsLog ("=== DAILY OPS END (PASS:{0}) ===" -f $EXIT_OK)
    return $EXIT_OK
}

try {
    if ($DailyOps) {
        exit (Run-DailyOps)
    }
    exit (Run-Launcher)
} catch {
    if ($DailyOps) {
        $runId = [Environment]::GetEnvironmentVariable("VG_RUN_ID", "Process")
        Write-OpsLog ("[ERROR] " + $_.Exception.Message)
        Write-OpsObs -RunId $runId -Stage "daily_ops_end" -Suite "daily_ops" -Status "FAIL" -Detail ("runtime_error: {0}" -f $_.Exception.Message)
        Write-OpsLog ("=== DAILY OPS END (FAIL:{0}) ===" -f $EXIT_RUNTIME_FAIL)
    } else {
        Write-LauncherLog ("Error launcher: " + $_.Exception.Message)
        Start-Process "notepad.exe" -ArgumentList @($LauncherLog) | Out-Null
    }
    exit $EXIT_RUNTIME_FAIL
}
