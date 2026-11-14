"""Put the storyboard frames into docs/storyboard/, and stamp every SI-generated mockup with a visible watermark.

    python scripts/make_storyboard.py --real <folder of real screenshots> --mock <folder of generated mockups>

Two kinds of frame, never mixed up:
  real   screenshots of the running app on real data (scripts/shoot_flood.py, scripts/record_flood.py).
         They need no watermark.
  mock   pictures made with an SI image model for scenes that are not built yet. Space Apps 2026 asks for a visible
         watermark on every SI-generated image, so the mark is baked into the file. A mockup shows a layout, never
         a measurement: every number in it is a placeholder.

Files are written as <order>_<name>.jpg at 1920 px wide, mockups as <order>_<name>_mock.jpg.
Written with SI assistance (Claude Code), reviewed by the team.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/seguisb.ttf"
LABEL = "SI-generated mockup, not data"
WIDTH = 1920


def watermark(im):
    """A pill at the bottom centre and a second one at the top centre, so a crop of either half still carries it."""
    im = im.convert("RGBA")
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    px = round(im.width * 0.019)
    font = ImageFont.truetype(FONT, px) if os.path.exists(FONT) else ImageFont.load_default()
    x0, y0, x1, y1 = d.textbbox((0, 0), LABEL, font=font)
    pad_x, pad_y = round(px * 0.8), round(px * 0.42)
    w, h = (x1 - x0) + 2 * pad_x, (y1 - y0) + 2 * pad_y
    for top in (round(im.height * 0.022), im.height - round(im.height * 0.02) - h):
        left = (im.width - w) // 2
        d.rounded_rectangle((left, top, left + w, top + h), radius=h // 2, fill=(255, 196, 0, 235), outline=(20, 16, 0, 255), width=max(2, px // 12))
        d.text((left + pad_x - x0, top + pad_y - y0), LABEL, font=font, fill=(20, 16, 0, 255))
    return Image.alpha_composite(im, layer).convert("RGB")


def fit(im):
    im = im.convert("RGB")
    return im.resize((WIDTH, round(WIDTH * im.height / im.width)), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--real", nargs="*", default=[], help="order=path pairs, for example 01_space=shots/storm_space.png")
    ap.add_argument("--mock", nargs="*", default=[], help="order=path pairs of SI-generated mockups")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "..", "docs", "storyboard"))
    ap.add_argument("--quality", type=int, default=84)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for pair in args.real:
        name, path = pair.split("=", 1)
        fit(Image.open(path)).save(os.path.join(args.out, f"{name}.jpg"), "JPEG", quality=args.quality)
        print("real", name)
    for pair in args.mock:
        name, path = pair.split("=", 1)
        watermark(fit(Image.open(path))).save(os.path.join(args.out, f"{name}_mock.jpg"), "JPEG", quality=args.quality)
        print("mock", name)


if __name__ == "__main__":
    sys.exit(main())
