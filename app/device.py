"""Восстановление USB-устройства камеры Sony PS Eye (лечение кода 10).

Камера PS Eye — составное USB-устройство: родитель (usbccgp) и видеоинтерфейс
MI_00 (WinUSB). WinUSB открывается монопольно, поэтому если процесс с камерой
завершить принудительно, родительское устройство «залипает» и остаётся с кодом 10
(CM_PROB_FAILED_START) — тогда MI_00 не запускается и кадры не приходят.

Модуль находит такие устройства и перезапускает их через pnputil. pnputil требует
прав администратора, поэтому перезапуск выполняется отдельным процессом PowerShell
с повышением прав (UAC).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from .config import project_root

# Идентификатор камеры Sony PS Eye (PS3): USB 1415:2000
VID_PID = "VID_1415&PID_2000"
# Код 10 (CM_PROB_FAILED_START) — «устройство не запущено»
PROBLEM_FAILED_START = 10
# Пауза после перезапуска: интерфейсы должны успеть пересоздаться
RESTART_WAIT_SEC = 6
# Файлы восстановления (временные, лежат в temp/)
SCRIPT_PATH = os.path.join(project_root(), "temp", "device_repair.ps1")
LOG_PATH = os.path.join(project_root(), "temp", "device_repair.log")
# Ожидание UAC + перезапуска устройства
REPAIR_TIMEOUT_SEC = 180.0


def _no_window_flag() -> int:
    """Флаг, чтобы у служебных процессов не мигало консольное окно."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _powershell(script: str, timeout: float = 30.0) -> str:
    """Выполняет PowerShell-скрипт и возвращает объединённый вывод (stdout+stderr)."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_no_window_flag(),
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"__ERROR__ {exc}"
    return proc.stdout.decode("utf-8", "replace")


# Опрос состояния: каждая строка — "статус<TAB>instanceId" (кириллица не нужна)
_QUERY_SCRIPT = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
    "Get-PnpDevice -ErrorAction SilentlyContinue | "
    f"Where-Object {{ $_.InstanceId -match '{VID_PID}' }} | "
    "ForEach-Object { \"$($_.Status)`t$($_.InstanceId)\" }"
)


def camera_nodes() -> list[tuple[str, str]]:
    """Узлы камеры в системе: список пар (статус, instanceId)."""
    nodes: list[tuple[str, str]] = []
    for line in _powershell(_QUERY_SCRIPT).splitlines():
        if "\t" not in line:
            continue
        status, instance_id = line.split("\t", 1)
        status, instance_id = status.strip(), instance_id.strip()
        if instance_id:
            nodes.append((status, instance_id))
    return nodes


def repair_needed(nodes: list[tuple[str, str]] | None = None) -> bool:
    """Нужен ли перезапуск устройства: сломан родитель или видеоинтерфейс MI_00.

    Учитываются только узлы в состоянии Error (код 10). «Призраки» отключённых
    устройств (статус Unknown) и аудиоинтерфейс MI_01 игнорируются — на видео они
    не влияют, а их постоянная ошибка приводила бы к запросу прав при каждом старте.
    """
    nodes = camera_nodes() if nodes is None else nodes
    for status, instance_id in nodes:
        if status != "Error":
            continue
        if "&MI_" not in instance_id or "MI_00" in instance_id:
            return True
    return False


# Скрипт перезапуска устройства (выполняется с правами администратора)
_RESTART_SCRIPT = """\
$ErrorActionPreference = 'Continue'
$log = '{log}'
"repair start $(Get-Date -Format o)" | Out-File -LiteralPath $log -Encoding utf8
$targets = @(Get-PnpDevice | Where-Object {{ $_.InstanceId -match '{vid_pid}' -and $_.InstanceId -notmatch '&MI_' }})
foreach ($dev in $targets) {{
    if ($dev.Status -eq 'OK') {{ continue }}
    $out = (pnputil /restart-device "$($dev.InstanceId)" 2>&1 | Out-String).Trim()
    "restart $($dev.InstanceId): $out" | Out-File -LiteralPath $log -Append -Encoding utf8
    Start-Sleep -Seconds 3
    $state = Get-PnpDevice -InstanceId $dev.InstanceId -ErrorAction SilentlyContinue
    if ($state -and $state.Status -ne 'OK') {{
        "fallback disable/enable $($dev.InstanceId)" | Out-File -LiteralPath $log -Append -Encoding utf8
        Disable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false -ErrorAction Continue
        Start-Sleep -Seconds 4
        Enable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false -ErrorAction Continue
        Start-Sleep -Seconds 6
    }}
}}
"repair done $(Get-Date -Format o)" | Out-File -LiteralPath $log -Append -Encoding utf8
"""


def _write_restart_script() -> str:
    """Пишет скрипт перезапуска в temp/ (UTF-8 с BOM — иначе PS 5.1 ломает разбор)."""
    os.makedirs(os.path.dirname(SCRIPT_PATH), exist_ok=True)
    content = _RESTART_SCRIPT.format(log=LOG_PATH, vid_pid=VID_PID)
    with open(SCRIPT_PATH, "w", encoding="utf-8-sig") as handle:
        handle.write(content)
    return SCRIPT_PATH


def _run_elevated(script_path: str) -> tuple[bool, str]:
    """Запускает скрипт в PowerShell с повышением прав (UAC). Возвращает (успех, вывод)."""
    inner = (
        "Start-Process -FilePath powershell -Verb RunAs -Wait -WindowStyle Hidden "
        f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','{script_path}'"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", inner],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_no_window_flag(),
            timeout=REPAIR_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, "тайм-аут ожидания перезапуска устройства"
    except OSError as exc:
        return False, f"не удалось запустить PowerShell: {exc}"
    text = proc.stdout.decode("utf-8", "replace").strip()
    return proc.returncode == 0, text


def restart_camera() -> tuple[bool, str]:
    """Перезапускает устройство камеры (лечит код 10). Возвращает (успех, сообщение)."""
    if sys.platform != "win32":
        return False, "Восстановление устройства доступно только в Windows"
    script = _write_restart_script()
    ok, output = _run_elevated(script)
    if not ok:
        return False, (
            "Не удалось перезапустить устройство камеры: запрос прав администратора "
            f"отклонён или не выполнен ({output or 'без вывода'})"
        )
    time.sleep(RESTART_WAIT_SEC)
    if repair_needed():
        return False, (
            "Перезапуск устройства не помог. Отключите камеру от USB и подключите снова "
            "(порт USB 2.0 без хаба); если не поможет — перезагрузите ПК"
        )
    return True, "Устройство камеры перезапущено (код 10 устранён)"


def ensure_camera_ready(log=None) -> str:
    """Лечит камеру при старте приложения: при ошибке перезапускает устройство.

    Возвращает сообщение для журнала (пустая строка — вмешательство не требовалось).
    """
    if not repair_needed():
        return ""
    if log is not None:
        log("Камера в состоянии ошибки (код 10) — перезапускаю USB-устройство...")
    _ok, message = restart_camera()
    if log is not None:
        log(message)
    return message
