"""Проверка окружения для запуска PSEyes: Python, пакеты, ffmpeg, камера.

Запуск:  python check_env.py
"""
from __future__ import annotations

import importlib
import os
import platform
import shutil
import sys

# Консоль Windows по умолчанию не в UTF-8: без этого русские сообщения выходят «крякозябрами»
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

OK = "[ OK ]"
BAD = "[FAIL]"
WARN = "[WARN]"


def check_python() -> bool:
    version = platform.python_version()
    good = sys.version_info >= (3, 11)
    print(f"{OK if good else BAD} Python {version}" + ("" if good else " (нужен 3.11+)"))
    return good


def check_packages() -> bool:
    result = True
    for module, package in (("PyQt6", "PyQt6"), ("cv2", "opencv-python"), ("numpy", "numpy")):
        try:
            mod = importlib.import_module(module)
            if module == "PyQt6":
                from PyQt6.QtCore import QT_VERSION_STR

                version = QT_VERSION_STR
            else:
                version = getattr(mod, "__version__", "?")
            print(f"{OK} {package} {version}")
        except Exception as exc:  # noqa: BLE001
            result = False
            print(f"{BAD} {package} не установлен ({exc})")
    return result


def check_ffmpeg() -> bool:
    candidates = [shutil.which("ffmpeg"), r"C:\ffmpeg\bin\ffmpeg.exe"]
    for path in candidates:
        if path and os.path.isfile(path):
            print(f"{OK} ffmpeg: {path}")
            return True
    print(f"{WARN} ffmpeg не найден — кадры сниматься будут, MP4 собрать не получится")
    return False


def check_camera() -> bool:
    try:
        from app.config import AppConfig
        from app import dshow
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} не удалось загрузить модули приложения: {exc}")
        return False

    config = AppConfig.load()
    ffmpeg = dshow.find_ffmpeg(config.ffmpeg_path)
    try:
        devices = dshow.list_devices(ffmpeg)
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} не удалось получить список камер: {exc}")
        return False

    if not devices:
        print(f"{BAD} DirectShow-камеры не найдены (подключена ли камера?)")
        return False

    print(f"{OK} камеры: {', '.join(devices)}")
    if config.device_name and config.device_name not in devices:
        print(f"{WARN} в config.json указана «{config.device_name}», её нет в списке")
    return True


def main() -> int:
    print("=== Проверка окружения PSEyes ===\n")
    results = [check_python(), check_packages(), check_ffmpeg(), check_camera()]
    print()
    if all(results[:2]):
        print("Можно запускать: run.bat  (или python main.py)")
        if not results[2]:
            print("Без ffmpeg будет доступна только съёмка кадров.")
        return 0
    print("Сначала устраните ошибки выше, затем запустите: pip install -r requirements.txt")
    return 1


if __name__ == "__main__":
    sys.exit(main())
