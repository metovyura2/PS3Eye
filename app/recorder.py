"""Таймлапс-рекордер: сохранение кадров по таймеру в отдельном потоке."""
from __future__ import annotations

import json
import os
import threading
import time

import cv2
from PyQt6.QtCore import QThread, pyqtSignal

FRAME_TEMPLATE = "frame_{:06d}.jpg"
FRAME_GLOB = "frame_*.jpg"


class TimelapseRecorder(QThread):
    """Каждые interval_sec сохраняет последний кадр камеры в JPEG."""

    frame_saved = pyqtSignal(int, str)        # номер кадра, путь
    status_message = pyqtSignal(str)          # сообщение для журнала
    recording_finished = pyqtSignal(dict)     # итоговая статистика

    def __init__(
        self,
        camera,
        session_dir: str,
        interval_sec: float,
        jpeg_quality: int,
        rotate: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.camera = camera
        self.session_dir = session_dir
        self.frames_dir = os.path.join(session_dir, "frames")
        self.interval_sec = float(interval_sec)
        self.jpeg_quality = int(jpeg_quality)
        self.rotate = int(rotate)

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._write_lock = threading.Lock()

        self.frames_saved = 0
        self.frames_skipped = 0
        self.first_frame = 0
        self.last_frame = 0
        self.started_at: float | None = None
        self.stopped_at: float | None = None

    # --- управление из GUI ---

    def stop(self) -> None:
        """Просит поток завершиться и ждёт его."""
        self._stop_event.set()
        self.wait(10000)

    def pause(self) -> None:
        """Приостанавливает съёмку (превью продолжает работать)."""
        self._pause_event.set()

    def resume(self) -> None:
        """Возобновляет съёмку."""
        self._pause_event.clear()

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    # --- внутренняя логика ---

    def _existing_frames(self) -> int:
        """Сколько кадров уже есть в папке сессии (для докачки)."""
        if not os.path.isdir(self.frames_dir):
            return 0
        return len([name for name in os.listdir(self.frames_dir) if name.startswith("frame_")])

    def _process(self, frame):
        """Поворот кадра согласно настройкам."""
        if self.rotate == 90:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        if self.rotate == 180:
            return cv2.rotate(frame, cv2.ROTATE_180)
        if self.rotate == 270:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _write_jpeg(self, frame, path: str) -> bool:
        """Записывает JPEG (cv2.imwrite не работает с юникод-путями)."""
        params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        ok, buffer = cv2.imencode(".jpg", frame, params)
        if not ok:
            return False
        with self._write_lock, open(path, "wb") as handle:
            handle.write(buffer.tobytes())
        return True

    def save_session_info(self, extra: dict | None = None) -> str:
        """Сохраняет session.json с параметрами и статистикой съёмки."""
        duration = 0.0
        if self.started_at:
            duration = (self.stopped_at or time.time()) - self.started_at
        data = {
            "session_dir": self.session_dir,
            "frames_dir": self.frames_dir,
            "frames_saved": self.frames_saved,
            "frames_skipped": self.frames_skipped,
            "first_frame": self.first_frame,
            "last_frame": self.last_frame,
            "interval_sec": self.interval_sec,
            "jpeg_quality": self.jpeg_quality,
            "rotate": self.rotate,
            "duration_sec": round(duration, 2),
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
        }
        if extra:
            data.update(extra)
        path = os.path.join(self.session_dir, "session.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return path

    def run(self) -> None:  # noqa: D102
        os.makedirs(self.frames_dir, exist_ok=True)
        self.frames_saved = self._existing_frames()
        self.started_at = time.time()
        self.status_message.emit(
            f"Съёмка начата: интервал {self.interval_sec:g} с, кадров уже {self.frames_saved}"
        )

        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                self._stop_event.wait(0.2)
                continue

            frame = self.camera.latest_frame() if self.camera else None
            if frame is None:
                self.frames_skipped += 1
                self.status_message.emit("Кадр не получен, пропуск")
            else:
                number = self.frames_saved + 1
                path = os.path.join(self.frames_dir, FRAME_TEMPLATE.format(number))
                if self._write_jpeg(self._process(frame), path):
                    self.frames_saved = number
                    if not self.first_frame:
                        self.first_frame = number
                    self.last_frame = number
                    self.frame_saved.emit(number, path)
                else:
                    self.frames_skipped += 1
                    self.status_message.emit("Не удалось сохранить кадр")

            self._stop_event.wait(self.interval_sec)

        self.stopped_at = time.time()
        self.status_message.emit(f"Съёмка остановлена, сохранено кадров: {self.frames_saved}")
        self.recording_finished.emit(
            {
                "frames": self.frames_saved,
                "skipped": self.frames_skipped,
                "session_dir": self.session_dir,
                "duration_sec": round((self.stopped_at - self.started_at), 2),
            }
        )
