"""Снимок окна приложения для README (assets/preview.png).

Запуск: python tools/make_preview.py

Окно MainWindow рендерится реальным платформенным плагином Qt за пределами
рабочего стола, затем сохраняется снимок. Камеру открывать не обязательно:
если кадров нет, в превью будет надпись «Ожидание кадра...».
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.ui import MainWindow  # noqa: E402

OUT = os.path.join(ROOT, "assets", "preview.png")
WINDOW_SIZE = (1220, 780)
# Сколько ждать кадры камеры перед снимком
CAPTURE_WAIT_SEC = 10.0


def main() -> int:
    """Показывает окно вне экрана, ждёт кадры камеры и сохраняет снимок."""
    app = QApplication(sys.argv)
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
    pixmap.save(OUT)
    window.shutdown()
    print(f"Снимок сохранён: {OUT} ({pixmap.width()}x{pixmap.height()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
