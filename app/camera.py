"""Поток непрерывного захвата кадров с камеры (DirectShow).

Кадры читаются постоянно: если читать редко, буфер DirectShow
переполняется и кадры теряются. Таймлапс берёт последний кадр.
"""
from __future__ import annotations

import threading
import time

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from . import dshow

# Сколько неудачных чтений подряд считаем потерей камеры
MAX_READ_FAILURES = 30
# Каждый N-й кадр проверяется на "чёрный экран" (проблема драйвера PS Eye)
DARK_CHECK_EVERY = 10
# Сколько проверок подряд с чёрным кадром считать проблемой
DARK_WARN_SAMPLES = 30
# Кадр считается устаревшим, если он старше этого времени (камера потеряна)
FRAME_STALE_SEC = 1.0
# Как часто повторять сообщение о недоступности камеры (каждая N-я попытка)
RETRY_LOG_EVERY = 5


class CaptureThread(QThread):
    """Постоянный захват кадров с камеры."""

    frame_ready = pyqtSignal(object)          # numpy-кадр (BGR)
    fps_updated = pyqtSignal(float)           # фактический fps
    state_changed = pyqtSignal(str)           # текстовое состояние
    error_occurred = pyqtSignal(str)          # ошибка открытия/потери устройства
    capture_lost = pyqtSignal(str)            # камера недоступна: причина
    capture_restored = pyqtSignal(int, int)   # камера снова работает: ширина, высота

    def __init__(
        self,
        device_name: str,
        device_index: int,
        width: int,
        height: int,
        cam_fps: int,
        ffmpeg_path: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.device_name = device_name
        self.device_index = device_index
        self.width = width
        self.height = height
        self.cam_fps = cam_fps
        self.ffmpeg_path = ffmpeg_path

        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_time = 0.0
        self._running = False
        self._dark_samples = 0
        self.actual_fps = 0.0
        self.frames_total = 0
        self.frames_failed = 0

    # --- управление из GUI ---

    def stop(self) -> None:
        """Останавливает поток и освобождает камеру."""
        self._running = False
        self.wait(5000)

    def latest_frame(self) -> np.ndarray | None:
        """Копия последнего полученного кадра.

        Возвращает None, если кадра ещё не было или он устарел (камера потеряна):
        иначе таймлапс записал бы один и тот же замороженный кадр.
        """
        with self._lock:
            if self._frame is None or (time.time() - self._frame_time) > FRAME_STALE_SEC:
                return None
            return self._frame.copy()

    def _mark_lost(self) -> None:
        """Сбрасывает кадр и fps: превью не должно показывать старую картинку."""
        with self._lock:
            self._frame = None
            self._frame_time = 0.0
        if self.actual_fps != 0.0:
            self.actual_fps = 0.0
            self.fps_updated.emit(0.0)

    def _loss_reason(self) -> str:
        """Объясняет, почему камеру не удалось открыть: нет устройства или оно занято."""
        devices = dshow.list_devices(self.ffmpeg_path)
        if self.device_name and self.device_name not in devices:
            return (
                "камера не найдена в DirectShow (проверьте USB-порт/кабель; "
                "если у «Составное USB устройство» код 10 — переподключите камеру "
                "или запустите tools\\driver_fix\\05_restart_camera.ps1)"
            )
        return "устройство занято другим приложением (камера открывается монопольно)"

    # --- внутренняя логика ---

    def _wait(self, seconds: float) -> bool:
        """Пауза с проверкой остановки. False — запрошена остановка."""
        deadline = time.time() + seconds
        while self._running and time.time() < deadline:
            time.sleep(0.05)
        return self._running

    def _apply_settings(self, cap: cv2.VideoCapture) -> cv2.VideoCapture:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.cam_fps)
        return cap

    def _open_capture(self) -> cv2.VideoCapture:
        """Открывает камеру: сначала по индексу DirectShow, затем по имени.

        OpenCV 4.x (DSHOW) не умеет открывать устройство по имени,
        поэтому основной путь — индекс, вычисленный через ffmpeg.
        """
        attempts: list[str] = []
        index = self.device_index
        if index < 0:
            index = dshow.resolve_index(self.ffmpeg_path, self.device_name)
        if index >= 0:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if cap.isOpened():
                return self._apply_settings(cap)
            cap.release()
            attempts.append(f"по индексу {index}")

        if self.device_name:
            cap = cv2.VideoCapture(f"video={self.device_name}", cv2.CAP_DSHOW)
            if cap.isOpened():
                return self._apply_settings(cap)
            cap.release()
            attempts.append("по имени")

        raise RuntimeError(
            "не удалось открыть камеру (" + ", ".join(attempts or ["устройство не найдено"]) + ")"
        )

    def run(self) -> None:  # noqa: D102
        """Обёртка потока: гарантирует освобождение камеры при любом выходе."""
        try:
            self._capture_loop()
        finally:
            # Незакрытый WinUSB «залипает»: устройство получает код 10
            # (CM_PROB_FAILED_START) и перестаёт отдавать кадры
            if self._cap is not None:
                self._cap.release()
                self._cap = None
            self._mark_lost()
        self.state_changed.emit("Захват остановлен")

    def _capture_loop(self) -> None:
        """Основной цикл: открывает камеру и непрерывно читает кадры."""
        self._running = True
        attempt = 0
        while self._running:
            try:
                self._cap = self._open_capture()
            except RuntimeError as exc:
                attempt += 1
                self._mark_lost()
                reason = self._loss_reason()
                self.capture_lost.emit(reason)
                # Сообщение не спамим каждые 2 с: первая попытка и далее каждая N-я
                if attempt == 1 or attempt % RETRY_LOG_EVERY == 0:
                    self.error_occurred.emit(f"{exc}. Причина: {reason}")
                    self.state_changed.emit(
                        f"Камера недоступна ({attempt}-я попытка): {reason}"
                    )
                if not self._wait(2.0):
                    break
                continue

            attempt = 0
            real_width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            real_height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._dark_samples = 0
            self.capture_restored.emit(real_width, real_height)
            self.state_changed.emit(f"Камера открыта: {real_width}x{real_height}")

            failures = 0
            period_start = time.time()
            period_frames = 0

            while self._running:
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    failures += 1
                    self.frames_failed += 1
                    if failures >= MAX_READ_FAILURES:
                        self._mark_lost()
                        self.capture_lost.emit(
                            "потеря кадров: USB рвёт передачу "
                            "(порт USB 2.0 без хаба, кабель, драйвер)"
                        )
                        self.state_changed.emit("Потеря кадров, переподключение камеры")
                        break
                    time.sleep(0.01)
                    continue

                failures = 0
                self.frames_total += 1
                with self._lock:
                    self._frame = frame
                    self._frame_time = time.time()
                self.frame_ready.emit(frame)

                # Контроль чёрного кадра: типичная проблема драйвера PS Eye,
                # когда устройство открыто, но данные не приходят
                if self.frames_total % DARK_CHECK_EVERY == 0:
                    if float(frame.mean()) < 1.0:
                        self._dark_samples += 1
                        if self._dark_samples == DARK_WARN_SAMPLES:
                            # Типичная ситуация: устройство открыто, но USB-композит PS Eye
                            # не запущен (код 10) или занят другим приложением
                            self.state_changed.emit(
                                "Чёрный кадр: камера открыта, но данные не идут — "
                                "проверьте USB-кабель/порт (лучше USB 2.0 без хаба), "
                                "закройте OBS/браузер; если у «Составное USB устройство» "
                                "код 10 — переподключите камеру или запустите "
                                "tools\\driver_fix\\05_restart_camera.ps1"
                            )
                    else:
                        if self._dark_samples >= DARK_WARN_SAMPLES:
                            self.state_changed.emit("Изображение с камеры восстановлено")
                        self._dark_samples = 0

                period_frames += 1
                elapsed = time.time() - period_start
                if elapsed >= 1.0:
                    self.actual_fps = period_frames / elapsed
                    self.fps_updated.emit(self.actual_fps)
                    period_start = time.time()
                    period_frames = 0

            if self._cap is not None:
                self._cap.release()
                self._cap = None
            self._mark_lost()
            if self._running:
                self._wait(1.0)


def show_properties(
    device_name: str,
    device_index: int,
    ffmpeg_path: str,
    width: int,
    height: int,
    cam_fps: int,
) -> str:
    """Показывает системный диалог настроек камеры (экспозиция, усиление, баланс белого).

    Вызывать при остановленном CaptureThread: захват OpenCV не потокобезопасен.
    Возвращает текст результата для журнала.
    """
    probe = CaptureThread(device_name, device_index, width, height, cam_fps, ffmpeg_path)
    try:
        cap = probe._open_capture()  # noqa: SLF001 — общий код открытия устройства
    except RuntimeError as exc:
        return f"Настройки недоступны: {exc}"
    try:
        # CAP_PROP_SETTINGS показывает модальное окно драйвера и ждёт его закрытия
        cap.set(cv2.CAP_PROP_SETTINGS, 0)
        return "Диалог настроек камеры закрыт"
    finally:
        cap.release()
