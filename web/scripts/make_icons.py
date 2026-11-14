"""Export the generated story icons with a visible SI watermark baked into each file.

    python -I scripts/make_icons.py <folder with icon-water.png, icon-fire.png, icon-sink.png, icon-quake.png>

Keeps transparency (the masters were keyed off chroma green), trims to the object plus even padding, resizes to
512 px and adds a small "SI" pill in the bottom-right corner, as Space Apps asks for every SI-generated image.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/seguisb.ttf"
NAMES = ("water", "fire", "sink", "quake")
SIZE = 512


def main():
    src = sys.argv[1]
    out = os.path.join("public", "img", "icons")
    os.makedirs(out, exist_ok=True)
    for name in NAMES:
        im = Image.open(os.path.join(src, f"icon-{name}.png")).convert("RGBA")
        box = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        obj = im.crop(box)
        side = round(max(obj.size) * 1.08)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.alpha_composite(obj, ((side - obj.width) // 2, (side - obj.height) // 2))
        canvas = canvas.resize((SIZE, SIZE), Image.LANCZOS)
        d = ImageDraw.Draw(canvas)
        font = ImageFont.truetype(FONT, 34)
        x0, y0, x1, y1 = d.textbbox((0, 0), "SI", font=font)
        pw, ph = (x1 - x0) + 30, (y1 - y0) + 18
        left, top = SIZE - pw - 6, SIZE - ph - 6
        d.rounded_rectangle((left, top, left + pw, top + ph), radius=ph // 2, fill=(14, 12, 36, 150), outline=(255, 255, 255, 90), width=2)
        d.text((left + 15 - x0, top + 9 - y0), "SI", font=font, fill=(255, 255, 255, 245))
        canvas.save(os.path.join(out, f"{name}.webp"), "WEBP", quality=88, method=6, exact=True)
        print(name, canvas.size)


if __name__ == "__main__":
    main()
