# Step 4: install the Universal PS3 Eye Driver (WinUSB + DirectShow filter)
$ErrorActionPreference = 'Continue'
$temp = $PSScriptRoot
$log = "$temp\step3_install.log"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host 'NOT_ADMIN -> restarting elevated'
    Start-Process powershell -Verb RunAs -Wait -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath
    )
    exit
}

$msi = "$temp\PS3EyeInstallerBeta2.msi"
"MSI: $msi exists=$([bool](Test-Path $msi))" | Out-File $log -Encoding utf8

$args = @('/i', $msi, '/qb', '/norestart', '/l*v', "$temp\msi_install_verbose.log")
$proc = Start-Process msiexec.exe -ArgumentList $args -Wait -PassThru
"msiexec exit code: $($proc.ExitCode)" | Out-File $log -Append -Encoding utf8

"=== DirectShow video devices (after) ===" | Out-File $log -Append -Encoding utf8
(& 'C:\ffmpeg\bin\ffmpeg.exe' -hide_banner -list_devices true -f dshow -i dummy 2>&1 |
    Select-String -Pattern 'video' | Out-String) | Out-File $log -Append -Encoding utf8

"=== PS3 Eye driver store entries ===" | Out-File $log -Append -Encoding utf8
((pnputil /enum-drivers) | Select-String -Pattern 'ps3|PS3' -Context 4,4 | Out-String) |
    Out-File $log -Append -Encoding utf8

Write-Host 'STEP3_DONE'
