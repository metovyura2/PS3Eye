"""Работа с DirectShow: список устройств и режимов через ffmpeg.

OpenCV не умеет читать имена устройств DirectShow, поэтому перечисление
выполняется внешним ffmpeg, а OpenCV получает имя или индекс устройства.
"""
from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys

from .config import DEFAULT_FFMPEG

# "PS3 Eye Universal" (video)
DEVICE_RE = re.compile(r'"([^"]+)"\s+\((video|audio)\)')

# Классы PnP с видеоустройствами. Media намеренно не опрашивается: в нём
# живут аудиокарты и микрофоны (AT2020USB+, Realtek, NVIDIA Audio), а не камеры.
CAMERA_CLASSES = "Camera,Image"
# Звуковые интерфейсы камер (MI_01 у PS Eye, usbaudio) — это не камера.
# По словам amp/audio разбирать имя нельзя: в «Webcam» тоже есть «cam».
AUDIO_RE = re.compile(
    r"(audio|mic|microphone|headset|speaker|sound|wave|hdmi|display audio|"
    r"аудио|микрофон|динамик|наушник)",
    re.IGNORECASE,
)
AUDIO_INTERFACE_RE = re.compile(r"&MI_(01|03|04)&", re.IGNORECASE)
# Служебные записи, которые камерой не являются и в списке только мешают
JUNK_RE = re.compile(r"(virtual|obs|droidcam|ndi|screen capture)", re.IGNORECASE)
# pixel_format=bgr0  min s=640x480 fps=2 max s=640x480 fps=60.0002
OPTION_RE = re.compile(
    r"pixel_format=(\S+)\s+min s=(\d+x\d+) fps=([\d.]+)\s+max s=(\d+x\d+) fps=([\d.]+)"
)


def _no_window_flag() -> int:
    """Флаг, чтобы не мигало консольное окно ffmpeg."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def find_ffmpeg(preferred: str | None = None) -> str:
    """Ищет ffmpeg: настройки, переменная FFMPEG, PATH, стандартная папка."""
    candidates = [preferred, os.environ.get("FFMPEG"), DEFAULT_FFMPEG, shutil.which("ffmpeg")]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return "ffmpeg"


def _ffmpeg_output(args: list[str]) -> str:
    """Запускает ffmpeg и возвращает вывод (ffmpeg пишет в stderr)."""
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_no_window_flag(),
        )
    except OSError as exc:
        return f"ffmpeg недоступен: {exc}"
    return proc.stdout.decode("utf-8", "replace")


def list_devices(ffmpeg: str = DEFAULT_FFMPEG, kind: str = "video") -> list[str]:
    """Список устройств DirectShow указанного типа в порядке перечисления."""
    output = _ffmpeg_output(
        [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
    )
    return [name for name, device_kind in DEVICE_RE.findall(output) if device_kind == kind]


# Перечисление камер по всей системе (Windows PnP), включая занятые другими
# приложениями: ffmpeg/DirectShow такие устройства не показывает вообще.
# -Class и -PresentOnly здесь не работают: при их использовании Get-PnpDevice
# молча отбрасывает Camera/Image-устройства. Класс и наличие определяем сами.
_PNP_SCRIPT = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
    f"$classes = '{CAMERA_CLASSES}' -split ','; "
    "Get-PnpDevice -ErrorAction SilentlyContinue | "
    "Where-Object { $_.Class -and ($classes -contains $_.Class) } | "
    "Sort-Object FriendlyName, InstanceId | "
    'ForEach-Object { "$($_.FriendlyName)`t$($_.Status)`t$($_.InstanceId)`t$($_.Class)`t$($_.Service)" }'
)
# CM_PROB_PHANTOM: устройство отсутствует (осталась только запись в реестре)
PROBLEM_PHANTOM = 24
# DN_PHANTOM в ConfigFlags: запись устройства в реестре без самого устройства
PHANTOM_FLAG = 0x80


def _is_video_instance(instance_id: str) -> bool:
    """По InstanceId отличает видеоинтерфейс камеры от звукового.

    Sony PS Eye — составное устройство: MI_00 — камера, MI_01 — микрофон.
    """
    upper = instance_id.upper()
    if "MI_00" in upper or "MI_02" in upper:
        return True
    if "&MI_" in upper:
        return False
    return True


# Запись Enumerate\<класс>\<id> в реестре остаётся после отключения устройства
ENUM_KEY = r"SYSTEM\CurrentControlSet\Enum\{device}"
# CFGPROP_INSTALL_STATE: DN_HAS_PROBLEM + CM_PROB_PHANTOM для отключённого
CONFIG_FLAGS = "ConfigFlags"


def devnode_is_phantom(instance_id: str) -> bool:
    """Устройство есть только в реестре (USB отключён), а не подключено.

    Нужно, потому что Get-PnpDevice на этой машине не работает как ожидается:
    -PresentOnly и -Class молча теряют подключённые камеры, а Status/Problem
    у оставшихся куцые. В реестре ConfigFlags хранит флаг DN_PHANTOM — он
    и показывает, осталась ли запись от выдернутого устройства.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg

        safe_id = instance_id.replace("\\", "#")
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, ENUM_KEY.format(device=safe_id)
        ) as key:
            flags = winreg.QueryValueEx(key, CONFIG_FLAGS)[0]
    except (ImportError, OSError):
        return False
    return bool(int(flags) & PHANTOM_FLAG)


def devnode_nodes(instance_id: str) -> list[str]:
    """Все узлы устройства: сам InstanceId и его родители (составное USB, хаб)."""
    nodes = [instance_id.replace("#", "\\")]
    current = nodes[0]
    while "\\" in current:
        current = current.rsplit("\\", 1)[0]
        nodes.append(current)
    return nodes


def device_status(instance_id: str) -> str:
    """Статус устройства для списка в окне.

    PnP-статус Get-PnpDevice здесь неинформативен («Unknown»), а код ошибки
    драйвера в реестре (ConfigFlags) — единственный надёжный признак:
    0x4 — отключено, 0x1 — драйвер не установлен/ошибка, иначе коды проблем.
    """
    if sys.platform != "win32":
        return ""
    flags = 0
    try:
        import winreg

        for node in devnode_nodes(instance_id):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, ENUM_KEY.format(device=node.replace("\\", "#"))
                ) as key:
                    flags |= int(winreg.QueryValueEx(key, CONFIG_FLAGS)[0])
            except OSError:
                continue
    except ImportError:
        return ""
    if flags & 0x80:
        return "Unknown"
    if flags & 0x4:
        return "Disabled"
    if flags & 0x1:
        return "Error"
    if flags & 0x2:
        return "Unknown"
    return "OK"


def list_system_cameras(timeout: float = 15.0) -> list[tuple[str, str]]:
    """Все камеры, подключённые к ПК: список пар (имя, статус).

    Используется PowerShell (Get-PnpDevice), потому что это единственный
    способ увидеть и те камеры, которые сейчас заняты другим приложением
    и поэтому не попадают в перечисление DirectShow.
    """
    if sys.platform != "win32":
        return []
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PNP_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_no_window_flag(),
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    cameras: list[tuple[str, str]] = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        parts = line.split("\t")
        name, status = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
        instance_id = parts[2].strip() if len(parts) > 2 else ""
        # PnP-статус на этой машине пустой/неверный: уточняем по реестру
        status = device_status(instance_id) or status
        if not name or name.lower() == "name":
            continue
        if JUNK_RE.search(name):
            continue
        # Звуковой интерфейс камеры: микрофон (MI_01) или audio-драйвер
        audio_service = len(parts) > 4 and parts[4].strip().lower() in ("usbaudio", "usbaudio2")
        if audio_service or AUDIO_INTERFACE_RE.search(instance_id):
            continue
        # Аудиокарты/микрофоны камерой не являются (по имени)
        if AUDIO_RE.search(name):
            continue
        if not _is_video_instance(instance_id):
            continue
        # Запись осталась после отключения USB (CM_PROB_PHANTOM) — в списке не нужна
        if devnode_is_phantom(instance_id):
            continue
        item = (name, status)
        if item not in cameras:
            cameras.append(item)
    return cameras


def device_status_label(status: str) -> str:
    """Статус PnP по-русски для списка камер."""
    mapping = {
        "OK": "работает",
        "Error": "ошибка (код 10)",
        "Unknown": "не подключено",
        "Degraded": "сбои в работе",
        "Disabled": "отключено",
        "Starting": "запускается",
    }
    return mapping.get(status, status or "неизвестно")


def resolve_index(ffmpeg: str, device_name: str) -> int:
    """Индекс устройства в порядке DirectShow (нужен для OpenCV)."""
    for index, name in enumerate(list_devices(ffmpeg)):
        if name == device_name:
            return index
    return -1


def list_modes(ffmpeg: str, device_name: str) -> list[tuple[str, int, int, float]]:
    """Режимы устройства: (пиксельный формат, ширина, высота, максимальный fps)."""
    output = _ffmpeg_output(
        [
            ffmpeg, "-hide_banner", "-list_options", "true",
            "-f", "dshow", "-i", f"video={device_name}",
        ]
    )
    modes: list[tuple[str, int, int, float]] = []
    for pixel_format, _min_res, _min_fps, max_res, max_fps in OPTION_RE.findall(output):
        width, height = max_res.split("x")
        mode = (pixel_format, int(width), int(height), float(max_fps))
        if mode not in modes:
            modes.append(mode)
    return modes
