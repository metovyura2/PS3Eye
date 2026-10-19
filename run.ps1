# PSEyes — запуск приложения (PowerShell).
# Использование:  .\run.ps1
# Если PowerShell блокирует скрипт:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Python {
    foreach ($name in @("py", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Host "[ОШИБКА] Python не найден. Установите Python 3.11+ с https://www.python.org/downloads/windows/" -ForegroundColor Red
    exit 1
}
Write-Host "Python: $python" -ForegroundColor DarkGray

# Зависимости
& $python -c "import PyQt6, cv2, numpy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Первый запуск: устанавливаю зависимости из requirements.txt..." -ForegroundColor Yellow
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ОШИБКА] Не удалось установить зависимости." -ForegroundColor Red
        exit 1
    }
}

# ffmpeg нужен только для сборки MP4
$ffmpeg = "C:\ffmpeg\bin\ffmpeg.exe"
if (-not (Test-Path $ffmpeg) -and -not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "[ВНИМАНИЕ] ffmpeg не найден: съёмка кадров будет работать, сборка MP4 — нет." -ForegroundColor Yellow
}

Write-Host "Запуск PSEyes..." -ForegroundColor Green
& $python main.py
exit $LASTEXITCODE
