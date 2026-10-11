"""The scroll story's picture set from rendered frames (ADR-071, ADR-121): 360 WEBP pictures for
the desktop (`NAME-001.webp` …, 1600 × 900) and for upright screens (`NAMEu-001.webp`: the 960 × 900
cut round the cover, which the render frames at 0.6 of the width; a phone shows it across its
width above the caption, at full sharpness), plus a strip to look at the set at a glance.

From the six chapters of render_reel.py (each 60 PNG frames, st1-0001.png …):

    uv run python scripts/film/story_frames.py OUT --name story6 --chapters DIR

Or an older set with some of its pictures replaced (the rain chapter without baked drops):

    uv run python scripts/film/story_frames.py OUT --name story5 \\
        --base ~/cover-data/media/story4- --replace DIR

(DIR holds story-300.webp … from render_story.py --no-drops; every picture not in DIR is taken
from the base set as it is.)

NAME is new for every set: the website's edge keeps /media files for a day.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import Image

FRAMES = 360
CHAPTERS = 6
FULL = 1600
UPRIGHT = (960, 900)  # the cut for upright screens, in pictures of FULL width
FOCUS = 0.6  # where the cover sits across the picture (StoryFrames.tsx's FOCUS)


def pictures(a: argparse.Namespace) -> list[Path]:
    if a.chapters:
        per = FRAMES // CHAPTERS
        out = []
        for c in range(1, CHAPTERS + 1):
            files = sorted(a.chapters.glob(f"st{c}-*.png"))
            if len(files) != per:
                raise SystemExit(f"chapter {c}: {len(files)} frames, {per} wanted")
            out += files
        return out
    base = Path(str(a.base) + "001.webp").parent
    stem = Path(str(a.base)).name
    out = []
    for n in range(1, FRAMES + 1):
        new = a.replace / f"story-{n:03d}.webp" if a.replace else None
        out.append(new if new and new.is_file() else base / f"{stem}{n:03d}.webp")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--chapters", type=Path)
    ap.add_argument("--base", type=str)
    ap.add_argument("--replace", type=Path)
    ap.add_argument("--quality", type=int, default=74)
    a = ap.parse_args()
    src = pictures(a)
    a.out.mkdir(parents=True, exist_ok=True)
    total = {"full": 0, "phone": 0}
    strip = []
    for n, path in enumerate(src, start=1):
        im = Image.open(path).convert("RGB")
        same = path.suffix == ".webp" and im.width == FULL
        if im.width != FULL:
            im = im.resize((FULL, round(im.height * FULL / im.width)), Image.Resampling.LANCZOS)
        dst = a.out / f"{a.name}-{n:03d}.webp"
        if same:
            shutil.copyfile(path, dst)  # a rendered WEBP as it is: no second loss
        else:
            im.save(dst, quality=a.quality, method=6)
        total["full"] += dst.stat().st_size
        cw, ch = UPRIGHT
        x0 = min(max(round(FOCUS * FULL - cw / 2), 0), FULL - cw)
        y0 = max((im.height - ch) // 2, 0)
        dst = a.out / f"{a.name}u-{n:03d}.webp"
        im.crop((x0, y0, x0 + cw, y0 + ch)).save(dst, quality=a.quality, method=6)
        total["phone"] += dst.stat().st_size
        if n % 12 == 0:
            strip.append(
                im.resize((320, round(im.height * 320 / im.width)), Image.Resampling.LANCZOS)
            )
    cols = 6
    w, h = strip[0].size
    sheet = Image.new("RGB", (cols * w, -(-len(strip) // cols) * h), (20, 22, 20))
    for i, im in enumerate(strip):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(a.out / f"{a.name}-strip.jpg", quality=85)
    full, phone = (total[k] for k in ("full", "phone"))
    print(
        f"{len(src)} pictures: {full / 1e6:.1f} MB wide ({full / len(src) / 1e3:.0f} KB each), "
        f"{phone / 1e6:.1f} MB upright ({phone / len(src) / 1e3:.0f} KB each)"
    )


if __name__ == "__main__":
    main()
