"""Сборка MP4-таймлапса из папки кадров через ffmpeg."""
from __future__ import annotations

import glob
import os
import subprocess
import sys

from PyQt6.QtCore import QThread, pyqtSignal

FRAME_GLOB = "frame_*.jpg"
FRAME_PATTERN = "frame_%06d.jpg"

# Дополнительные аргументы кодировщиков
CODEC_ARGS: dict[str, list[str]] = {
    "libx264": ["-preset", "medium", "-crf", "18"],
    "libx265": ["-preset", "medium", "-crf", "20"],
    "h264_nvenc": ["-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0"],
    "h264_qsv": ["-global_quality", "20"],
    "h264_amf": ["-quality", "balanced", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20"],
}

AVAILABLE_CODECS = list(CODEC_ARGS.keys())

# Служебные ключи вывода "-progress pipe:1" (в журнал не пишем)
PROGRESS_KEYS = {
    "frame",
    "fps",
    "bitrate",
    "total_size",
    "out_time_us",
    "out_time_ms",
    "out_time",
    "dup_frames",
    "drop_frames",
    "speed",
    "progress",
}


def list_frames(frames_dir: str) -> list[str]:
    """Отсортированный список файлов кадров."""
    return sorted(glob.glob(os.path.join(frames_dir, FRAME_GLOB)))


def count_frames(frames_dir: str) -> int:
    """Количество кадров в папке."""
    return len(list_frames(frames_dir))


def first_frame_number(frames_dir: str) -> int:
    """Номер первого кадра (для -start_number)."""
    frames = list_frames(frames_dir)
    if not frames:
        return 1
    name = os.path.splitext(os.path.basename(frames[0]))[0]
    try:
        return int(name.split("_")[-1])
    except ValueError:
        return 1


def build_command(
    ffmpeg: str,
    frames_dir: str,
    out_path: str,
    fps: int,
    codec: str = "libx264",
    start_number: int = 1,
) -> list[str]:
    """Формирует команду ffmpeg для сборки видео."""
    args = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(fps),
        "-start_number", str(start_number),
        "-i", os.path.join(frames_dir, FRAME_PATTERN),
        "-c:v", codec,
    ]
    args += CODEC_ARGS.get(codec, [])
    args += [
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        out_path,
        "-progress", "pipe:1",
        "-nostats",
    ]
    return args


class TimelapseEncoder(QThread):
    """Собирает видео и сообщает о прогрессе."""

    progress = pyqtSignal(int, int)     # обработано кадров, всего кадров
    log_line = pyqtSignal(str)          # строка вывода ffmpeg
    finished_ok = pyqtSignal(str)       # путь к готовому файлу
    failed = pyqtSignal(str)            # текст ошибки
    cancelled = pyqtSignal()            # сборка отменена пользователем

    def __init__(
        self,
        ffmpeg: str,
        frames_dir: str,
        out_path: str,
        fps: int,
        codec: str = "libx264",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.ffmpeg = ffmpeg
        self.frames_dir = frames_dir
        self.out_path = out_path
        self.fps = int(fps)
        self.codec = codec

        self._proc: subprocess.Popen | None = None
        self._cancel_requested = False
        self.total_frames = count_frames(frames_dir)

    def cancel(self) -> None:
        """Прерывает сборку."""
        self._cancel_requested = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def run(self) -> None:  # noqa: D102
        if self.total_frames == 0:
            self.failed.emit("В папке нет кадров для сборки")
            return

        args = build_command(
            self.ffmpeg,
            self.frames_dir,
            self.out_path,
            self.fps,
            self.codec,
            first_frame_number(self.frames_dir),
        )
        self.log_line.emit("ffmpeg " + " ".join(args))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

        try:
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=flags,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            self.failed.emit(f"Не удалось запустить ffmpeg: {exc}")
            return

        for line in self._proc.stdout:  # type: ignore[union-attr]
            text = line.strip()
            if not text:
                continue
            key, _, value = text.partition("=")
            if key == "frame":
                try:
                    self.progress.emit(int(value), self.total_frames)
                except ValueError:
                    pass
                continue
            if key in PROGRESS_KEYS or key.startswith("stream_"):
                continue
            self.log_line.emit(text)

        code = self._proc.wait()
        self._proc = None

        if self._cancel_requested:
            self.cancelled.emit()
        elif code == 0 and os.path.isfile(self.out_path):
            self.finished_ok.emit(self.out_path)
        else:
            self.failed.emit(f"ffmpeg завершился с кодом {code}")
