# Step 2-3: remove PS Eye devices and delete libusb-win32 (Zadig) driver packages
$ErrorActionPreference = 'Continue'
$temp = $PSScriptRoot
$log = "$temp\step2_cleanup.log"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host 'NOT_ADMIN -> restarting elevated'
    Start-Process powershell -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath
    )
    exit
}

"Admin: True" | Out-File $log -Encoding utf8

$ids = @(
    'USB\VID_1415&PID_2000\5&389AB2C2&0&5',
    'USB\VID_1415&PID_2000\5&389AB2C2&0&6',
    'USB\VID_1415&PID_2000&MI_00\6&22516C2B&1&0000',
    'USB\VID_1415&PID_2000&MI_01\6&22516C2B&1&0001',
    'USB\VID_1415&PID_2000&MI_00\6&F97BB86&1&0000',
    'USB\VID_1415&PID_2000&MI_01\6&F97BB86&1&0001'
)
foreach ($id in $ids) {
    $out = (pnputil /remove-device "$id" 2>&1 | Out-String).Trim()
    "REMOVE $id => $out" | Out-File $log -Append -Encoding utf8
}

foreach ($inf in @('oem112.inf', 'oem95.inf')) {
    $out = (pnputil /delete-driver $inf /uninstall /force 2>&1 | Out-String).Trim()
    "DELETE $inf => $out" | Out-File $log -Append -Encoding utf8
}

"=== DEVICES VID_1415 (after) ===" | Out-File $log -Append -Encoding utf8
(Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_1415' } |
    Select-Object Status, Class, FriendlyName, InstanceId | Format-List | Out-String) |
    Out-File $log -Append -Encoding utf8

Write-Host 'STEP2_DONE'
