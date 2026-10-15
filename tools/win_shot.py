"""Снимок окна PSEyes с подгонкой под текущий рабочий стол.

Windows не даёт захватывать окно больше видимой области (часть «за экраном»
превращается в чёрный прямоугольник), поэтому окно сначала растягивается на
весь рабочий стол, затем снимается.

Запуск: python tools/win_shot.py [out.png]
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

SPI_GETWORKAREA = 0x0030
SW_MAXIMIZE = 3
SW_RESTORE = 9


def find_window() -> int:
    """Возвращает дескриптор окна PSEyes или 0."""
    found = [0]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value.startswith(TITLE):
                found[0] = hwnd
                return False
        return True

    user32.EnumWindows(_cb, 0)
    return found[0]


def work_area() -> tuple[int, int, int, int]:
    """(left, top, right, bottom) рабочего стола основного монитора."""
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    r = RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right, r.bottom


def main(argv: list[str]) -> int:
    """Растягивает окно на рабочий стол, печатает геометрию и сохраняет снимок."""
    out = argv[1] if len(argv) > 1 else ""
    hwnd = find_window()
    if not hwnd:
        print("Окно PSEyes не найдено")
        return 1
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    user32.SetForegroundWindow(hwnd)
    left, top, right, bottom = work_area()
    print(f"hwnd={hwnd} workarea=({left}, {top}, {right}, {bottom})")
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        ImageGrab.grab(bbox=(left, top, right, bottom)).save(out)
        print(f"Снимок сохранён: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
