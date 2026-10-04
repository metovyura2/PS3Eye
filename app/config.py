"""Настройки приложения PSEyes.

Все параметры хранятся в config.json рядом с main.py,
относительные пути считаются от корня проекта.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields

# Путь к ffmpeg по умолчанию (используется, если в PATH его нет)
DEFAULT_FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"


def project_root() -> str:
    """Корень проекта: папка EXE (собранного приложения) или папка с main.py."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CONFIG_FILE = os.path.join(project_root(), "config.json")


@dataclass
class AppConfig:
    """Параметры захвата и сборки таймлапса."""

    device_name: str = "PS3 Eye Universal"
    device_index: int = -1            # -1 = определить автоматически по имени
    width: int = 640
    height: int = 480
    cam_fps: int = 30                 # частота, которую просим у камеры
    interval_sec: float = 10.0        # интервал съёмки кадров таймлапса
    out_fps: int = 30                 # частота кадров готового видео
    jpeg_quality: int = 95            # качество сохраняемых JPEG
    rotate: int = 0                   # поворот кадра: 0, 90, 180, 270
    sessions_dir: str = "sessions"
    auto_build: bool = True           # собирать MP4 сразу после остановки
    keep_frames: bool = True          # оставлять кадры после сборки
    preview_smooth: bool = False      # сглаживать превью (рябь PS Eye при слабом свете)
    codec: str = "libx264"
    ffmpeg_path: str = DEFAULT_FFMPEG

    @classmethod
    def load(cls, path: str | None = None) -> "AppConfig":
        """Читает config.json; при ошибке возвращает настройки по умолчанию."""
        path = path or CONFIG_FILE
        config = cls()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                known = {item.name for item in fields(cls)}
                for key, value in data.items():
                    if key in known:
                        setattr(config, key, value)
            except (OSError, ValueError):
                pass
        return config

    def save(self, path: str | None = None) -> None:
        """Сохраняет настройки в config.json."""
        path = path or CONFIG_FILE
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, ensure_ascii=False, indent=2)

    def sessions_path(self) -> str:
        """Абсолютный путь к папке сессий."""
        if os.path.isabs(self.sessions_dir):
            return self.sessions_dir
        return os.path.join(project_root(), self.sessions_dir)
