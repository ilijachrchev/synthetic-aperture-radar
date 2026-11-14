"""Turn the generated hero masters into web files, each with a visible SI watermark baked in.

    python -I scripts/make_hero.py <folder with hero-day.png and hero-dusk.png>

Space Apps 2026 asks for a visible watermark on every SI-generated image, so the mark is part of the file itself and
survives any reuse (slides, the demo video). Writes public/img/hero-{day,dusk}.webp (16:9, desktop) and
public/img/hero-{day,dusk}-tall.webp (9:16 cut around the barraca, phones). The masters stay outside the repo.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/seguisb.ttf"
LABEL = "SI-generated image"
# 9:16 window on the 2752 x 1536 master, centred on the barraca
TALL_X0 = 150


def watermark(im, font_px, inset):
    """Bottom centre: the page shows these with object-fit cover anchored at the bottom, so the sides and the top
    may be trimmed on some screens but the bottom centre is always in view."""
    im = im.convert("RGBA")
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = ImageFont.truetype(FONT, font_px)
    x0, y0, x1, y1 = d.textbbox((0, 0), LABEL, font=font)
    pad_x, pad_y = round(font_px * 0.7), round(font_px * 0.38)
    w, h = (x1 - x0) + 2 * pad_x, (y1 - y0) + 2 * pad_y
    left, top = (im.width - w) // 2, im.height - inset - h
    d.rounded_rectangle((left, top, left + w, top + h), radius=h // 2, fill=(14, 12, 36, 120), outline=(255, 255, 255, 70), width=max(1, font_px // 14))
    d.text((left + pad_x - x0, top + pad_y - y0), LABEL, font=font, fill=(255, 255, 255, 240))
    return Image.alpha_composite(im, layer).convert("RGB")


def main():
    src = sys.argv[1]
    out = os.path.join("public", "img")
    os.makedirs(out, exist_ok=True)
    for name in ("day", "dusk"):
        master = Image.open(os.path.join(src, f"hero-{name}.png")).convert("RGB")
        wide = master.resize((2560, round(2560 * master.height / master.width)), Image.LANCZOS)
        watermark(wide, 26, round(wide.width * 0.035)).save(os.path.join(out, f"hero-{name}-v2.webp"), "WEBP", quality=84, method=6)
        h = master.height
        w = round(h * 9 / 16)
        tall = master.crop((TALL_X0, 0, TALL_X0 + w, h))
        watermark(tall, 30, round(tall.width * 0.06)).save(os.path.join(out, f"hero-{name}-tall-v2.webp"), "WEBP", quality=84, method=6)
        print(name, wide.size, tall.size)


if __name__ == "__main__":
    main()
