# Step 1: snapshot of devices/drivers + download of the WinUSB driver installer
$ErrorActionPreference = 'Continue'
$temp = $PSScriptRoot

"=== DEVICES VID_1415 (before) ===" | Out-File "$temp\pnp_backup.txt" -Encoding utf8
Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_1415' } |
    Select-Object Status, Class, FriendlyName, InstanceId |
    Format-List | Out-File "$temp\pnp_backup.txt" -Append -Encoding utf8

"=== DRIVERS (before) ===" | Out-File "$temp\drivers_backup.txt" -Encoding utf8
(pnputil /enum-drivers) | Out-File "$temp\drivers_backup.txt" -Append -Encoding utf8

$msi = "$temp\PS3EyeInstallerBeta2.msi"
$url = 'https://github.com/jkevin/PS3EyeDirectShow/releases/download/1.0b2/PS3EyeInstallerBeta2.msi'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
    Invoke-WebRequest -Uri $url -OutFile $msi -UseBasicParsing
    "Downloaded: $msi, size $((Get-Item $msi).Length) bytes" | Out-File "$temp\download.log" -Encoding utf8
} catch {
    "DOWNLOAD ERROR: $_" | Out-File "$temp\download.log" -Encoding utf8
}
Write-Host 'STEP1_DONE'
