"""Диагностика «ряби» в кадрах PS Eye: шум, полосы, дубли, реальный fps.

Запуск: python tools/diagnose_frames.py [--frames 60] [--device "PS3 Eye Universal"]

Проверяет режимы 640x480@30 и 320x240@30, сохраняет 3 кадра в temp/diagnose/
для визуальной проверки и пишет отчёт в temp/diagnose_report.txt.

Как читать отчёт:
  * шум между кадрами — средний модуль разницы соседних кадров.
    > 8 при статичной сцене — сильный шум сенсора (слабый свет, большое усиление);
  * перепад строк — средняя разница соседних строк по яркости.
    > 3 — горизонтальные полосы (биение с LED-светом, flickerless нужно 50 Гц);
  * дрожание яркости — std средней яркости по кадрам. > 2 — автокоррекция
    экспозиции/усиления гуляет, её нужно зафиксировать в «Свойства камеры»;
  * дубли кадров — сколько пар одинаковых кадров подряд. Много дублей — USB
    не успевает (порт USB 3.0/хаб) или драйвер отдаёт кадры рывками;
  * резкость (дисперсия лапласиана) — < 20 значит картинка мыльная.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import dshow  # noqa: E402
from app.config import AppConfig, project_root  # noqa: E402

TEMP_DIR = os.path.join(project_root(), "temp")
OUT_DIR = os.path.join(TEMP_DIR, "diagnose")
REPORT_PATH = os.path.join(TEMP_DIR, "diagnose_report.txt")
MODES = [(640, 480, 30), (320, 240, 30)]


def measure(index: int, width: int, height: int, fps: int, frames: int) -> tuple[list[str], list[np.ndarray]]:
    """Снимает серию кадров и считает метрики шума. Возвращает строки отчёта и кадры."""
    lines: list[str] = [f"{width}x{height}@{fps}:"]
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        return [f"{width}x{height}@{fps}: НЕ ОТКРЫВАЕТСЯ"], []

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)

    # Прогрев: автокоррекции драйвера должны устаканиться
    for _ in range(15):
        cap.read()

    shots: list[np.ndarray] = []
    started = time.time()
    while len(shots) < frames:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        shots.append(frame)
    elapsed = max(time.time() - started, 1e-6)
    real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    if len(shots) < 2:
        return lines + [f"  кадров получено {len(shots)} — данных для оценки нет"], shots

    grays = [cv2.cvtColor(shot, cv2.COLOR_BGR2GRAY).astype(np.int16) for shot in shots]
    diffs = [float(np.abs(grays[i] - grays[i - 1]).mean()) for i in range(1, len(grays))]
    brightness = [float(gray.mean()) for gray in grays]
    row_steps = []
    for gray in grays[:10]:
        row_means = gray.mean(axis=1)
        row_steps.append(float(np.abs(np.diff(row_means)).mean()))
    sharpness = float(np.var(cv2.Laplacian(grays[-1].astype(np.uint8), cv2.CV_64F)))
    duplicates = sum(
        1 for i in range(1, len(grays)) if not np.any(grays[i] != grays[i - 1])
    )

    lines += [
        f"  кадров {len(shots)} за {elapsed:.2f} с -> {len(shots) / elapsed:.1f} fps, "
        f"реальный размер {real_w}x{real_h}",
        f"  яркость: средняя {np.mean(brightness):.1f}, дрожание {np.std(brightness):.2f}",
        f"  шум между кадрами: средний {np.mean(diffs):.2f}, медиана {np.median(diffs):.2f}",
        f"  перепад строк (полосы): {np.mean(row_steps):.2f}",
        f"  резкость (дисперсия лапласиана): {sharpness:.1f}",
        f"  дублей кадров подряд: {duplicates}",
    ]
    return lines, shots


def main() -> int:
    """Проверяет режимы и сохраняет отчёт."""
    parser = argparse.ArgumentParser(description="Диагностика качества кадров PS Eye")
    parser.add_argument("--frames", type=int, default=60, help="сколько кадров снимать в режиме")
    parser.add_argument("--device", default="", help="имя устройства DirectShow")
    args = parser.parse_args()

    config = AppConfig.load()
    device = args.device or config.device_name
    ffmpeg = dshow.find_ffmpeg(config.ffmpeg_path)
    index = dshow.resolve_index(ffmpeg, device)

    lines = [f"ffmpeg: {ffmpeg}", f"устройство: {device}", f"индекс для OpenCV: {index}"]
    if index < 0:
        lines.append("Устройство не найдено: проверьте USB и драйвер (tools/driver_fix/)")
    else:
        os.makedirs(OUT_DIR, exist_ok=True)
        for width, height, fps in MODES:
            mode_lines, shots = measure(index, width, height, fps, args.frames)
            lines += mode_lines
            for number, shot in enumerate(shots[:3], start=1):
                path = os.path.join(OUT_DIR, f"{width}x{height}_{number}.png")
                cv2.imwrite(path, shot)
            if shots:
                lines.append(f"  примеры кадров: {OUT_DIR}")
        lines.append("")
        lines.append("Примеры кадров можно открыть глазами: если видна мелкая рябь по всему полю —")
        lines.append("это шум сенсора при слабом свете (фиксируйте экспозицию/усиление в")
        lines.append("«Свойства камеры», добавьте света). Если полосы — выставьте flickerless 50 Гц.")

    report = "\n".join(lines)
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(report + "\n")
    try:
        print(report)
    except UnicodeEncodeError:  # консоль cp1251
        print(report.encode("ascii", "replace").decode("ascii"))
    print(f"\nОтчёт сохранён: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
