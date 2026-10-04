# Step 5: check PS Eye state after driver cleanup/install
$ErrorActionPreference = 'Continue'
$temp = $PSScriptRoot
$log = "$temp\step4_check.log"

"=== DEVICES VID_1415 ===" | Out-File $log -Encoding utf8
(Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_1415' } |
    Select-Object Status, Class, FriendlyName, InstanceId | Format-List | Out-String) |
    Out-File $log -Append -Encoding utf8

"=== DRIVER PACKAGES for VID_1415 ===" | Out-File $log -Append -Encoding utf8
((pnputil /enum-drivers) | Select-String -Pattern 'VID_1415' -Context 6,6 | Out-String) |
    Out-File $log -Append -Encoding utf8

"=== PROBLEM CODE (if present) ===" | Out-File $log -Append -Encoding utf8
$dev = Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_1415&PID_2000\\' } | Select-Object -First 1
if ($dev) {
    (Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode','DEVPKEY_Device_DriverInfPath','DEVPKEY_Device_Service' |
        Select-Object KeyName, Data | Format-Table -AutoSize | Out-String) |
        Out-File $log -Append -Encoding utf8
} else {
    "Device not present (camera unplugged)" | Out-File $log -Append -Encoding utf8
}

"=== FILTER DLL ===" | Out-File $log -Append -Encoding utf8
(Get-ChildItem 'C:\Program Files*\PS3Eye*' -Recurse -ErrorAction SilentlyContinue |
    Select-Object FullName, Length, LastWriteTime | Format-Table -AutoSize | Out-String) |
    Out-File $log -Append -Encoding utf8

Write-Host 'STEP4_DONE'
