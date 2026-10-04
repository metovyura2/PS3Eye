"""Работа с DirectShow: список устройств и режимов через ffmpeg.

OpenCV не умеет читать имена устройств DirectShow, поэтому перечисление
выполняется внешним ffmpeg, а OpenCV получает имя или индекс устройства.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from .config import DEFAULT_FFMPEG

# "PS3 Eye Universal" (video)
DEVICE_RE = re.compile(r'"([^"]+)"\s+\((video|audio)\)')
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
