"""Рисует иконку приложения PSEyes: камера с объективом и красным индикатором записи.

Запуск: python assets/make_icon.py
Создаёт assets/pseyes.png (512x512) и assets/pseyes.ico (16..256 px).
Рисуется кодом (Pillow), без внешних картинок — чтобы иконка всегда была воспроизводима.
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 512
S = SIZE / 512.0  # множитель: все размеры заданы для холста 512x512

# Палитра
BODY_TOP = (72, 84, 104)
BODY_BOTTOM = (34, 40, 54)
LENS_RING = (200, 208, 220)
LENS_GLASS = (28, 96, 148)
LENS_CENTER = (10, 30, 48)
REC_RED = (232, 44, 44)
WHITE = (245, 247, 250)


def _rounded_body(base: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """Корпус камеры: скруглённый прямоугольник с вертикальным градиентом."""
    left, top, right, bottom = int(56 * S), int(150 * S), int(456 * S), int(420 * S)
    radius = int(48 * S)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([left, top, right, bottom], radius=radius, fill=255)
    gradient = Image.new("RGB", (1, SIZE))
    for y in range(SIZE):
        t = min(max((y - top) / max(bottom - top, 1), 0.0), 1.0)
        colour = tuple(int(BODY_TOP[i] + (BODY_BOTTOM[i] - BODY_TOP[i]) * t) for i in range(3))
        gradient.putpixel((0, y), colour)
    gradient = gradient.resize((SIZE, SIZE)).convert("RGBA")
    base.paste(gradient, (0, 0), mask)


def _lens(draw: ImageDraw.ImageDraw) -> None:
    """Объектив по центру корпуса: кольцо, стекло, блик, зрачок."""
    cx, cy = int(256 * S), int(285 * S)
    steps = [
        (int(126 * S), LENS_RING),
        (int(110 * S), (24, 30, 42)),
        (int(96 * S), LENS_GLASS),
        (int(58 * S), LENS_CENTER),
    ]
    for radius, colour in steps:
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=colour)
    # блик на стекле
    draw.ellipse(
        [cx - int(80 * S), cy - int(84 * S), cx - int(24 * S), cy - int(30 * S)],
        fill=(90, 170, 210),
    )
    # тонкая диафрагма
    draw.ellipse(
        [cx - int(96 * S), cy - int(96 * S), cx + int(96 * S), cy + int(96 * S)],
        outline=(120, 130, 148),
        width=max(int(3 * S), 1),
    )


def _rec_dot(draw: ImageDraw.ImageDraw) -> None:
    """Красный кружок записи в правом верхнем углу корпуса."""
    cx, cy, radius = int(404 * S), int(196 * S), int(26 * S)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=REC_RED)
    inner = int(radius * 0.45)
    draw.ellipse(
        [cx - inner, cy - inner, cx + inner, cy + inner],
        fill=(255, 120, 120),
    )


def _rec_ring(draw: ImageDraw.ImageDraw) -> None:
    """Пунктирное кольцо «идёт запись» вокруг точки."""
    cx, cy = int(404 * S), int(196 * S)
    radius = int(44 * S)
    for index in range(12):
        angle = math.radians(index * 30)
        dot = int(6 * S)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        draw.ellipse([x - dot, y - dot, x + dot, y + dot], fill=REC_RED)


def _viewfinder(draw: ImageDraw.ImageDraw) -> None:
    """Нижняя плашка-«видоискатель» с полоской таймлапса."""
    left, top, right, bottom = int(96 * S), int(366 * S), int(416 * S), int(402 * S)
    draw.rounded_rectangle([left, top, right, bottom], radius=int(12 * S), fill=(18, 22, 32))
    for step in range(8):
        bar_left = left + int(10 * S) + step * int(38 * S)
        bar_top = top + int(8 * S)
        draw.rectangle([bar_left, bar_top, bar_left + int(18 * S), bottom - int(8 * S)], fill=WHITE)


def build() -> None:
    """Собирает изображение и пишет PNG/ICO."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # внешняя рамка-подложка
    draw.rounded_rectangle(
        [int(16 * S), int(16 * S), int(496 * S), int(496 * S)],
        radius=int(96 * S),
        fill=(16, 20, 30),
        outline=(120, 132, 156),
        width=max(int(6 * S), 1),
    )
    _rounded_body(image, draw)
    _lens(draw)
    _viewfinder(draw)
    _rec_ring(draw)
    _rec_dot(draw)

    png_path = os.path.join(HERE, "pseyes.png")
    image.save(png_path)

    ico_path = os.path.join(HERE, "pseyes.ico")
    image.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Иконки созданы:\n  {png_path}\n  {ico_path}")


if __name__ == "__main__":
    build()
