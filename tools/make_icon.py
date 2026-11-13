# Created by nc.ai 1.2.9 on new-admin-pc 2026-11-13 14:25:29
"""Сборка иконки EDHUD: SVG-макет -> data/edhud.ico (16…256) и data/edhud.png.

Геометрия повторяет data/edhud-icon.svg (исходный макет 512x512): скруглённый
тёмный квадрат, радиальный градиент, два наклонных эллипса-орбиты и звезда.
Отдельный растеризатор не нужен — рисуем в Pillow с запасом по размеру и
уменьшаем по Ланцошу, поэтому края гладкие.

Запуск (нужен Pillow):
    python tools/make_icon.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

VIEW = 512
SS = 4  # суперсэмплинг: рисуем 2048x2048, сохраняем до 256x256
SIZES = (16, 24, 32, 48, 64, 128, 256)
LARGE = 256

BG = (0x05, 0x0A, 0x14, 255)
BG_RADIUS = 90
CIRCLE_R = 180
CIRCLE_OPACITY = 0.9
GRAD_IN = (0xFF, 0x6B, 0x00)
GRAD_OUT = (0x0B, 0x13, 0x2B)
ELLIPSE_RX = 220
ELLIPSE_RY = 60
ELLIPSE_ANGLE = 15  # SVG rotate(-15): против часовой на экране = PIL rotate(+15)
ORBITS = ((8, (0x00, 0xE5, 0xFF), 255), (2, (0xFF, 0xFF, 0xFF), 128))
STAR = (
    (256, 180), (280, 240), (340, 240), (290, 280), (310, 340),
    (256, 300), (202, 340), (222, 280), (172, 240), (232, 240),
)


def _gradient_circle(radius: int):
    from PIL import Image, ImageDraw

    size = radius * 2
    ramp = Image.radial_gradient("L").resize((size, size), Image.BICUBIC)
    channels = [
        ramp.point(lambda v, a=a, b=b: round(a + (b - a) * v / 255)) for a, b in zip(GRAD_IN, GRAD_OUT)
    ]
    disc = Image.merge("RGB", channels)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    return disc, mask.point(lambda v: round(v * CIRCLE_OPACITY))


def _orbit(width: int, color: tuple[int, int, int], alpha: int):
    from PIL import Image, ImageDraw

    rx, ry, stroke = ELLIPSE_RX * SS, ELLIPSE_RY * SS, width * SS
    pad = stroke * 2
    side = (max(rx, ry) + pad) * 2
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    box = (side // 2 - rx, side // 2 - ry, side // 2 + rx, side // 2 + ry)
    ImageDraw.Draw(layer).ellipse(box, outline=color + (alpha,), width=stroke)
    return layer.rotate(ELLIPSE_ANGLE, resample=Image.BICUBIC)


def render() -> "object":
    from PIL import Image, ImageDraw

    side = VIEW * SS
    img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, side - 1, side - 1), radius=BG_RADIUS * SS, fill=BG)

    radius = CIRCLE_R * SS
    disc, mask = _gradient_circle(radius)
    img.paste(disc, (side // 2 - radius, side // 2 - radius), mask)

    for width, color, alpha in ORBITS:
        layer = _orbit(width, color, alpha)
        img.alpha_composite(layer, (side // 2 - layer.width // 2, side // 2 - layer.height // 2))

    draw = ImageDraw.Draw(img)
    draw.polygon([(x * SS, y * SS) for x, y in STAR], fill=(0xFF, 0xFF, 0xFF, 255))

    return img.resize((LARGE, LARGE), Image.LANCZOS)


def main() -> int:
    if importlib.util.find_spec("PIL") is None:
        print("нужен Pillow: python -m pip install pillow", file=sys.stderr)
        return 1

    data = Path(__file__).resolve().parent.parent / "data"
    big = render()
    png = data / "edhud.png"
    ico = data / "edhud.ico"
    big.save(png, format="PNG", optimize=True)
    big.save(ico, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"{png} ({png.stat().st_size} B)")
    print(f"{ico} ({ico.stat().st_size} B), размеры: {', '.join(str(s) for s in SIZES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
