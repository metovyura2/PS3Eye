# Шаг 5: перезапуск USB-устройства камеры PS Eye (лечит код 10 «устройство не запущено»)
# Применять, когда приложение запускается, но кадры чёрные, а в консоли идут
# ошибки libusb: "device is no longer connected" / "ReadPipe/WritePipe failed".
$ErrorActionPreference = 'Continue'
$log = "$PSScriptRoot\step5_restart.log"

# Без администратора PnP-операции запрещены — поднимаем права через UAC
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'NOT_ADMIN -> restarting elevated'
    Start-Process powershell -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath
    )
    exit
}

"Admin: True" | Out-File $log -Encoding utf8

# Все узлы камеры: составное устройство и его интерфейсы MI_00 (видео) / MI_01 (аудио)
$all = @(Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_1415&PID_2000' })
if ($all.Count -eq 0) {
    'DEVICE NOT FOUND: камера не найдена — проверьте кабель USB' |
        Out-File $log -Append -Encoding utf8
    Write-Host 'DEVICE_NOT_FOUND'
    exit
}

"=== BEFORE ===" | Out-File $log -Append -Encoding utf8
($all | Select-Object Status, Class, FriendlyName, InstanceId | Format-List | Out-String) |
    Out-File $log -Append -Encoding utf8

# Перезапускаем родительское составное устройство: дочерние интерфейсы пересоздаются сами
$parents = @($all | Where-Object { $_.InstanceId -notmatch '&MI_' })
foreach ($dev in $parents) {
    "RESTART $($dev.InstanceId)" | Out-File $log -Append -Encoding utf8
    $out = (pnputil /restart-device "$($dev.InstanceId)" 2>&1 | Out-String).Trim()
    "pnputil: $out" | Out-File $log -Append -Encoding utf8
    Start-Sleep -Seconds 3

    # Если рестарт не помог — полный цикл отключения и включения устройства
    $state = Get-PnpDevice -InstanceId $dev.InstanceId -ErrorAction SilentlyContinue
    if ($state -and $state.Status -ne 'OK') {
        'Disable/Enable' | Out-File $log -Append -Encoding utf8
        Disable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false -ErrorAction Continue
        Start-Sleep -Seconds 4
        Enable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false -ErrorAction Continue
        Start-Sleep -Seconds 6
    }
}

"=== AFTER ===" | Out-File $log -Append -Encoding utf8
(Get-PnpDevice | Where-Object { $_.InstanceId -match 'VID_1415&PID_2000' } |
    Select-Object Status, Class, FriendlyName, InstanceId | Format-List | Out-String) |
    Out-File $log -Append -Encoding utf8

Write-Host 'STEP5_DONE'
