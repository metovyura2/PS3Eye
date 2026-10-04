"""Сборка MP4 из готовой папки кадров.

Примеры:
  python tools/build_from_frames.py sessions/2026-09-30_20-00-00
  python tools/build_from_frames.py sessions/2026-09-30_20-00-00 --fps 30 --codec h264_nvenc
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import encoder as enc_mod  # noqa: E402
from app import dshow  # noqa: E402
from app.config import AppConfig  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Сборка таймлапс-видео из папки кадров")
    parser.add_argument("session", help="папка сессии (или папка с кадрами)")
    parser.add_argument("--fps", type=int, default=None, help="частота кадров видео")
    parser.add_argument("--codec", default=None, choices=enc_mod.AVAILABLE_CODECS)
    parser.add_argument("--out", default=None, help="путь к mp4 (по умолчанию в папке сессии)")
    return parser.parse_args()


def main() -> int:
    """Запускает ffmpeg и возвращает код выхода."""
    args = parse_args()
    config = AppConfig.load()
    ffmpeg = dshow.find_ffmpeg(config.ffmpeg_path)

    session = os.path.abspath(args.session)
    frames_dir = session if os.path.basename(session) == "frames" else os.path.join(session, "frames")
    if not os.path.isdir(frames_dir):
        print(f"Папка с кадрами не найдена: {frames_dir}")
        return 2

    total = enc_mod.count_frames(frames_dir)
    if total == 0:
        print(f"В папке нет кадров: {frames_dir}")
        return 2

    fps = args.fps or config.out_fps
    codec = args.codec or config.codec
    out_path = args.out or os.path.join(os.path.dirname(frames_dir), "timelapse.mp4")

    command = enc_mod.build_command(
        ffmpeg, frames_dir, out_path, fps, codec, enc_mod.first_frame_number(frames_dir)
    )
    print(f"Кадров: {total}, fps: {fps}, кодек: {codec}")
    print("Команда:", " ".join(command))
    result = subprocess.run(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode == 0:
        print(f"Готово: {out_path}")
    else:
        print(f"ffmpeg завершился с кодом {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
