"""The shop's share picture (1200x630) from our own film's still (ADR-108; QUESTIONS 34, ADR-136).

    uv run python scripts/film/og_image.py apps/web/public/brand/og-shop.png \
        [--still ~/cover-data/media/hero-kota1.jpg] [--font ~/opt/film2/assets/WorkSans.ttf]
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ap = argparse.ArgumentParser()
ap.add_argument("out", type=Path)
ap.add_argument("--still", type=Path, default=Path.home() / "cover-data/media/hero-kota1.jpg")
ap.add_argument("--font", type=Path, default=Path.home() / "opt/film2/assets/WorkSans.ttf")
a = ap.parse_args()
src = Image.open(a.still).convert("RGB")
W = 1300
h = round(src.height * W / src.width)  # 731
im = src.resize((W, h), Image.LANCZOS)
w = 1200
im = im.crop((60, 0, 60 + w, 630))

# a soft dark veil behind the words, top left, so they read on the wall
veil = Image.new("L", (w, 630), 0)
d = ImageDraw.Draw(veil)
d.rectangle((0, 0, 560, 150), fill=140)
veil = veil.filter(ImageFilter.GaussianBlur(70))
dark = Image.new("RGB", (w, 630), (28, 26, 22))
im = Image.composite(dark, im, veil)

font = str(a.font)
big = ImageFont.truetype(font, 48)
small = ImageFont.truetype(font, 24)
try:
    big.set_variation_by_axes([500])
    small.set_variation_by_axes([450])
except Exception:  # noqa: BLE001 - a static font: as it is
    pass
d = ImageDraw.Draw(im)
ink = (246, 240, 230)
d.text((56, 36), "Hoezen op maat.", font=big, fill=ink)
d.text((56, 92), "Made to measure.", font=big, fill=ink)
d.text((58, 156), "s2dio industries", font=small, fill=(222, 214, 200))
im.save(a.out, optimize=True)
print(im.size)
