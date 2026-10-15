"""Снимок и геометрия окна PSEyes (для проверки запуска).

Запуск: python tools/win_geometry.py [out.png]

Ищет окно по заголовку, печатает его геометрию и (если задан путь) сохраняет снимок окна.
"""
from __future__ import annotations

import ctypes
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import ImageGrab  # noqa: E402

TITLE = "PSEyes"
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

SW_RESTORE = 9
SW_SHOW = 5


def find_window() -> int:
    """Возвращает дескриптор окна PSEyes или 0."""
    result = [0]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value.startswith(TITLE):
                result[0] = hwnd
                return False
        return True

    user32.EnumWindows(_cb, 0)
    return result[0]


def rect_of(hwnd: int) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) окна в координатах рабочего стола."""
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def main(argv: list[str]) -> int:
    """Печатает геометрию окна и, при желании, сохраняет снимок."""
    out = argv[1] if len(argv) > 1 else ""
    hwnd = find_window()
    if not hwnd:
        print("Окно PSEyes не найдено")
        return 1
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)
    user32.SetForegroundWindow(hwnd)
    left, top, right, bottom = rect_of(hwnd)
    print(f"hwnd={hwnd} rect=({left}, {top}, {right}, {bottom}) size={right - left}x{bottom - top}")

    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    mon_w = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
    mon_h = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
    print(f"primary={screen_w}x{screen_h} virtual={mon_w}x{mon_h}")

    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        ImageGrab.grab(bbox=(left, top, right, bottom)).save(out)
        print(f"Снимок сохранён: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
