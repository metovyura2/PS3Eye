# Creates "PSEyes.lnk" on the Desktop pointing to dist\PSEyes.exe
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File tools\make_shortcut.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'dist\PSEyes.exe'
if (-not (Test-Path $exe)) {
    Write-Output "ERROR: exe not found: $exe"
    exit 1
}

$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'PSEyes.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnk)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = Split-Path -Parent $exe
$shortcut.IconLocation = "$exe,0"
$shortcut.Description = 'PSEyes - PS3 Eye timelapse recorder'
$shortcut.Save()

Write-Output "SHORTCUT: $lnk"
