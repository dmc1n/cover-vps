"""The hero film from its rendered frames (ADR-108): one seamless loop, two codecs, a poster.

- Soft dissolves between the shots (shots.json from render_hero.py), and the end dissolving into
  the start, so the loop has no seam: the film starts DISSOLVE frames into the first shot.
- `NAME-av1.mp4` (AV1, for every browser that plays it) and `NAME-h264.mp4` (H.264, the
  fallback, Safari before AV1), both two-pass to a size under `--max-mb`, no sound, the index at
  the front (fast start), so the first frame shows at once.
- `NAME.jpg` and `NAME.webp`: the first frame as the poster (also what visitors who asked for
  less motion see).
- `strip.jpg`: one picture per second, to look at the film at a glance.

    uv run python scripts/film/hero_encode.py FRAMES OUT [--name hero-kota1] [--ffmpeg PATH]
        [--max-mb 3.8]

NAME is new for every render: the website's edge keeps /media files for a day (ADR-071), and
the studio serves only names of letters, digits, - and _ (no second dot).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

FPS = 24
DISSOLVE = 10  # frames each dissolve takes


Step = tuple[Path, Path, float]  # picture a, picture b, how far into b (0: a alone)


def frames_in_order(src: Path) -> list[Path]:
    files = sorted(src.glob("hero-*.png"))
    if not files:
        raise SystemExit(f"no frames in {src}")
    return files


def blend(a: Path, b: Path, t: float) -> Step:
    return (a, b, t * t * (3 - 2 * t))  # eased


def picture(step: Step) -> Image.Image:
    a, b, t = step
    im = Image.open(a).convert("RGB")
    return im if t <= 0 else Image.blend(im, Image.open(b).convert("RGB"), t)


def edit(frames: list[Path], shots: list[tuple[str, int]]) -> list[Step]:
    """The shots joined by dissolves; the last shot dissolves into the first."""
    cuts, at = [], 0
    for _, n in shots:
        cuts.append((at, at + n))
        at += n
    if at != len(frames):
        raise SystemExit(f"{len(frames)} frames, the shots add up to {at}")
    d = DISSOLVE
    parts = [frames[s:e] for s, e in cuts]
    out: list[Step] = []

    def plain(fs: list[Path]) -> list[Step]:
        return [(f, f, 0.0) for f in fs]

    # the first shot without its head (the head closes the loop at the end)
    cur = parts[0][d:]
    for nxt in parts[1:]:
        out += plain(cur[:-d])
        out += [blend(cur[-d + i], nxt[i], (i + 1) / (d + 1)) for i in range(d)]
        cur = nxt[d:]
    out += plain(cur[:-d])
    out += [blend(cur[-d + i], parts[0][i], (i + 1) / (d + 1)) for i in range(d)]
    return out


def encode(ffmpeg: str, src: str, out: Path, codec: str, kbps: int, size: str, tmp: Path) -> None:
    common = ["-y", "-hide_banner", "-loglevel", "error", "-framerate", str(FPS), "-i", src,
              "-an", "-vf", f"scale={size}:flags=lanczos,format=yuv420p"]  # fmt: skip
    if codec == "av1":
        enc = ["-c:v", "libaom-av1", "-b:v", f"{kbps}k", "-cpu-used", "3", "-row-mt", "1",
               "-tiles", "2x2", "-g", "96", "-aq-mode", "1"]  # fmt: skip
    else:
        enc = ["-c:v", "libx264", "-b:v", f"{kbps}k", "-preset", "slow", "-profile:v", "high",
               "-level", "4.1", "-tune", "film", "-g", "48"]  # fmt: skip
    log = str(tmp / f"pass-{codec}")
    for p in (1, 2):
        target = ["-f", "mp4", "/dev/null"] if p == 1 else ["-movflags", "+faststart", str(out)]
        subprocess.run([ffmpeg, *common, *enc, "-pass", str(p), "-passlogfile", log, *target],
                       check=True)  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    ap.add_argument("--max-mb", type=float, default=3.8)
    ap.add_argument("--name", default="hero-kota1")
    ap.add_argument("--av1-size", default="1920:1080")
    ap.add_argument("--h264-size", default="1600:900")
    a = ap.parse_args()
    shots = [tuple(s) for s in json.loads((a.frames / "shots.json").read_text())]
    film = edit(frames_in_order(a.frames), shots)  # type: ignore[arg-type]
    seconds = len(film) / FPS
    a.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        for i, step in enumerate(film):
            picture(step).save(tmp / f"f{i:04d}.png", compress_level=1)
        src = str(tmp / "f%04d.png")
        for codec, size in (("av1", a.av1_size), ("h264", a.h264_size)):
            kbps = int(a.max_mb * 8 * 1000 / seconds * 0.97)
            out = a.out / f"{a.name}-{codec}.mp4"
            for _ in range(4):  # two-pass lands close; step down if it is still over
                encode(a.ffmpeg, src, out, codec, kbps, size, tmp)
                if out.stat().st_size <= a.max_mb * 1e6:
                    break
                kbps = int(kbps * 0.9)
            print(f"{out.name}: {out.stat().st_size / 1e6:.2f} MB, {kbps} kbit/s, {seconds:.1f} s")
    first = picture(film[0])
    first.save(a.out / f"{a.name}.jpg", quality=84, optimize=True, progressive=True)
    first.save(a.out / f"{a.name}.webp", quality=80, method=6)
    # the strip: one picture a second
    picks = [picture(s) for s in film[::FPS]]
    w = 384
    h = int(first.height * w / first.width)
    cols = 5
    rows = int(np.ceil(len(picks) / cols))
    strip = Image.new("RGB", (cols * w, rows * h), (20, 22, 20))
    for i, im in enumerate(picks):
        strip.paste(im.resize((w, h), Image.LANCZOS), ((i % cols) * w, (i // cols) * h))
    strip.save(a.out / "strip.jpg", quality=85)
    poster_kb = (a.out / f"{a.name}.jpg").stat().st_size // 1024
    print(f"{len(film)} frames, {seconds:.1f} s; poster {poster_kb} KB")


if __name__ == "__main__":
    main()
