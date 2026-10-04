"""Снимок окна приложения для README (assets/preview.png).

Запуск: python tools/make_preview.py [--no-blur]

Окно MainWindow рендерится реальным платформенным плагином Qt за пределами
рабочего стола, затем сохраняется снимок. Камеру открывать не обязательно:
если кадров нет, в превью будет надпись «Ожидание кадра...».

Область видеопревью по умолчанию размывается: снимок попадает в публичный
README, а в кадре может быть видно рабочее место/оборудование. Отключить
размытие — флаг --no-blur.
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageFilter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.ui import MainWindow  # noqa: E402

OUT = os.path.join(ROOT, "assets", "preview.png")
RAW = os.path.join(ROOT, "temp", "preview_raw.png")
WINDOW_SIZE = (1220, 780)
# Сколько ждать кадры камеры перед снимком
CAPTURE_WAIT_SEC = 10.0
# Радиус размытия области превью (пикселей): полностью скрывает детали кадра
BLUR_RADIUS = 26


def preview_rect(window: MainWindow, scale: float) -> tuple[int, int, int, int]:
    """Прямоугольник области видеопревью в координатах снимка (left, top, right, bottom)."""
    label = window.video_label
    top_left = label.mapTo(window, label.rect().topLeft())
    left = int(top_left.x() * scale)
    top = int(top_left.y() * scale)
    right = int((top_left.x() + label.width()) * scale)
    bottom = int((top_left.y() + label.height()) * scale)
    return left, top, right, bottom


def blur_preview(path: str, rect: tuple[int, int, int, int]) -> None:
    """Размывает область видеопревью на сохранённом снимке."""
    image = Image.open(path).convert("RGB")
    region = image.crop(rect).filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))
    image.paste(region, rect)
    image.save(path)


def main(argv: list[str]) -> int:
    """Показывает окно вне экрана, ждёт кадры камеры и сохраняет снимок."""
    blur = "--no-blur" not in argv
    app = QApplication(argv[:1])
    window = MainWindow(AppConfig.load())
    window.resize(*WINDOW_SIZE)
    # Окно уводим далеко за пределы рабочего стола: снимок делается без показа пользователю
    window.move(-4000, -4000)
    window.show()

    deadline = time.time() + CAPTURE_WAIT_SEC
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)

    pixmap = window.grab()
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    pixmap.save(RAW)
    scale = pixmap.width() / max(window.width(), 1)
    rect = preview_rect(window, scale)
    window.shutdown()

    if blur:
        blur_preview(RAW, rect)
    os.replace(RAW, OUT)
    print(f"Снимок сохранён: {OUT} ({pixmap.width()}x{pixmap.height()}), размытие={blur}, область={rect}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

