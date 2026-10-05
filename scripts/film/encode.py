"""The film's frames (render_film.py) as web video: an MP4 (H.264) at full size and one at
1280 wide for phones, plus a poster picture. Run inside Blender, which carries its own ffmpeg:

    blender -b -P scripts/film/encode.py -- --frames DIR --out DIR [--name welcome] [--poster 190]

Copy the files into the data directory's media/ folder; the shop serves them at /media/<file>
(Shop settings: film_url /media/welcome.mp4, film_poster /media/welcome.jpg).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy

FPS = 24


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--name", default="welcome")
    ap.add_argument("--poster", type=int, default=190)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    files = sorted(a.frames.glob("frame-*.png"))
    if not files:
        raise SystemExit(f"no frames in {a.frames}")
    a.out.mkdir(parents=True, exist_ok=True)
    for width, suffix, quality in ((1920, "", "HIGH"), (1280, "-1280", "MEDIUM")):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = bpy.context.scene
        sc.render.fps = FPS
        sc.render.resolution_x, sc.render.resolution_y = width, width * 9 // 16
        sc.sequence_editor_create()
        strip = sc.sequence_editor.sequences.new_image(
            "film", str(files[0]), channel=1, frame_start=1
        )
        for f in files[1:]:
            strip.elements.append(f.name)
        sc.frame_start, sc.frame_end = 1, len(files)
        r = sc.render
        r.image_settings.file_format = "FFMPEG"
        r.ffmpeg.format = "MPEG4"
        r.ffmpeg.codec = "H264"
        r.ffmpeg.constant_rate_factor = quality
        r.ffmpeg.ffmpeg_preset = "BEST"
        r.ffmpeg.gopsize = FPS
        r.ffmpeg.audio_codec = "NONE"
        r.filepath = str(a.out / f"{a.name}{suffix}.mp4")
        r.use_file_extension = False
        bpy.ops.render.render(animation=True)
    # the poster: the covered sofa just before the rain, as a JPEG
    img = bpy.data.images.load(str(files[min(a.poster, len(files)) - 1]))
    img.file_format = "JPEG"
    sc = bpy.context.scene
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 85
    img.save_render(str(a.out / f"{a.name}.jpg"), scene=sc)


main()
