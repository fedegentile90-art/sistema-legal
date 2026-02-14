param(
    [string]$ShortcutName = "SistemaLegal ERP",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Desktop = [Environment]::GetFolderPath("Desktop")
if ([string]::IsNullOrWhiteSpace($Desktop)) {
    throw "No se pudo resolver la carpeta de Escritorio."
}

$ShortcutPath = Join-Path $Desktop ("{0}.lnk" -f $ShortcutName)
if ((Test-Path $ShortcutPath) -and (-not $Force)) {
    Write-Output ("EXISTS::{0}" -f $ShortcutPath)
    exit 0
}

$TargetPath = Join-Path $RepoDir "RUN_ERP.cmd"
if (-not (Test-Path $TargetPath)) {
    throw ("No existe RUN_ERP.cmd en: {0}" -f $RepoDir)
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $RepoDir
$Shortcut.Arguments = ""
$Shortcut.WindowStyle = 1
$Shortcut.Description = "Abrir SistemaLegal ERP"
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,44"
$Shortcut.Save()

Write-Output ("CREATED::{0}" -f $ShortcutPath)
