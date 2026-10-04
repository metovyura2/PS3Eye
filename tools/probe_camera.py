"""Диагностика камеры PS Eye.

Запуск: python tools/probe_camera.py

Проверяет:
  * список видеоустройств DirectShow;
  * поддерживаемые режимы (разрешение/формат/fps);
  * реальный захват и яркость кадров (ловит "чёрный кадр");
  * скорость захвата на нескольких режимах.

Отчёт сохраняется в temp/probe_report.txt и печатается в консоль.
"""
from __future__ import annotations

import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import dshow  # noqa: E402
from app.config import AppConfig, project_root  # noqa: E402

TEMP_DIR = os.path.join(project_root(), "temp")
REPORT_PATH = os.path.join(TEMP_DIR, "probe_report.txt")

TEST_MODES = [(640, 480, 30), (640, 480, 60), (320, 240, 30)]


def capture_test(index: int, width: int, height: int, fps: int, frames: int = 60) -> str:
    """Захватывает кадры и возвращает отчёт по одному режиму."""
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        return f"  {width}x{height}@{fps}: НЕ ОТКРЫВАЕТСЯ"

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)

    ok_count = 0
    bright_count = 0
    max_mean = 0.0
    started = time.time()
    for _ in range(frames):
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        ok_count += 1
        mean = float(frame.mean())
        max_mean = max(max_mean, mean)
        if mean > 1.0:
            bright_count += 1
    elapsed = max(time.time() - started, 1e-6)

    real_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    return (
        f"  {width}x{height}@{fps}: кадров {ok_count}/{frames}, "
        f"непустых {bright_count}, макс. яркость {max_mean:.1f}, "
        f"скорость {ok_count / elapsed:.1f} fps, реальный размер {real_width}x{real_height}"
    )


def main() -> int:
    """Собирает отчёт и печатает его."""
    lines: list[str] = []
    config = AppConfig.load()
    ffmpeg = dshow.find_ffmpeg(config.ffmpeg_path)

    lines.append(f"ffmpeg: {ffmpeg}")
    lines.append(f"OpenCV: {cv2.__version__}")

    devices = dshow.list_devices(ffmpeg)
    lines.append("Видеоустройства DirectShow: " + (", ".join(devices) if devices else "не найдены"))

    target = config.device_name or (devices[0] if devices else "")
    lines.append(f"Проверяемое устройство: {target or 'не задано'}")

    if target:
        modes = dshow.list_modes(ffmpeg, target)
        lines.append("Режимы по данным ffmpeg:")
        for pixel_format, width, height, max_fps in modes:
            lines.append(f"  {width}x{height} {pixel_format} до {max_fps:g} fps")

    index = dshow.resolve_index(ffmpeg, target) if target else -1
    lines.append(f"Индекс устройства для OpenCV: {index}")

    if index >= 0:
        lines.append("Проверка захвата через OpenCV (DirectShow):")
        for width, height, fps in TEST_MODES:
            lines.append(capture_test(index, width, height, fps))

    lines.append("")
    lines.append("Если кадры идут, но яркость 0 — камера открыта, но данные не приходят:")
    lines.append("проверьте подключение USB и драйвер (PS3EyeInstallerBeta2.msi),")
    lines.append("а также закройте OBS и другие программы, которые держат камеру.")

    report = "\n".join(lines)
    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(report + "\n")

    try:
        print(report)
    except UnicodeEncodeError:  # консоль cp1251 не умеет «—»
        print(report.encode("ascii", "replace").decode("ascii"))
    print(f"\nОтчёт сохранён: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
