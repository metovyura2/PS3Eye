"""Точка входа приложения PSEyes.

Запуск: python main.py   (или run.bat)   /   dist\\PSEyes.exe
"""
from __future__ import annotations

import os
import signal
import sys

# Корень проекта: для исходников — папка с main.py, для EXE (PyInstaller) — папка exe
if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.config import AppConfig, project_root  # noqa: E402
from app.ui import MainWindow  # noqa: E402

# Камера открывается монопольно (WinUSB), поэтому второй экземпляр бесполезен:
# он будет только писать «Камера недоступна» и портить журнал
LOCK_FILE = os.path.join(ROOT, "temp", "pseyes.lock")


def acquire_single_instance():
    """Захватывает блокировку единственного экземпляра.

    Возвращает открытый файл-дескриптор или None, если приложение уже запущено.
    """
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    handle = open(LOCK_FILE, "a+", encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def install_shutdown_handlers(window: MainWindow) -> None:
    """Освобождает камеру при аварийном выходе: сигнал или необработанное исключение.

    Незакрытый WinUSB «залипает» и устройство получает код 10 (CM_PROB_FAILED_START),
    поэтому поток захвата должен успеть отпустить камеру при любом завершении.
    """

    def _on_signal(_signum, _frame):
        window.shutdown()
        QApplication.quit()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass

    def _on_uncaught(exc_type, exc_value, exc_tb):
        window.shutdown()
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _on_uncaught


def main() -> int:
    """Создаёт приложение и показывает главное окно."""
    lock = acquire_single_instance()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    if lock is None:
        QMessageBox.warning(
            None,
            "PSEyes уже запущен",
            "Приложение уже работает.\n\n"
            "Камера PS Eye открывается монопольно: второй экземпляр получит\n"
            "«Камера недоступна». Закройте первое окно и запустите снова.",
        )
        return 1

    config = AppConfig.load()
    window = MainWindow(config)
    install_shutdown_handlers(window)
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    code = app.exec()
    lock.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
