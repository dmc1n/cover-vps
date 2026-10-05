"""Render Blender frames on Modal GPUs (ADR-071): the scene script and its data go up once, the
frames come back as files. Many frames are split over many GPUs (one L4 each).

    uv run python scripts/film/gpu_render.py --script scripts/film/render_story.py
        --data <dir> --out <dir> --frames 1-240 [--per 24] [-- <script args>]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import modal

TAR = "Blender4.2/blender-4.2.3-linux-x64.tar.xz"
MIRRORS = [  # blender.org refuses some cloud builders: mirrors first
    "https://ftp.nluug.nl/pub/graphics/blender/release/",
    "https://mirrors.ocf.berkeley.edu/blender/release/",
    "https://download.blender.org/release/",
]
FETCH = " || ".join(f"curl -fsSL --retry 3 {m}{TAR} -o /tmp/b.tar.xz" for m in MIRRORS)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "curl",
        "ca-certificates",
        "xz-utils",
        "libxi6",
        "libxrender1",
        "libxkbcommon0",
        "libsm6",
        "libgl1",
        "libxfixes3",
        "libxxf86vm1",
        "libegl1",
        "libglu1-mesa",
        "libx11-6",
    )  # fmt: skip
    .run_commands(
        f"({FETCH}) && tar xf /tmp/b.tar.xz -C /opt "
        "&& rm /tmp/b.tar.xz && ln -s /opt/blender-4.2.3-linux-x64/blender /usr/local/bin/blender"
    )  # fmt: skip
)
app = modal.App("cover-render", image=image)


@app.function(gpu="L4", timeout=3600)
def render(
    script: bytes, data: dict[str, bytes], first: int, last: int, args: list[str]
) -> dict[str, bytes]:
    import subprocess
    import tempfile

    work = Path(tempfile.mkdtemp())
    (work / "script.py").write_bytes(script)
    for name, blob in data.items():
        (work / "data" / name).parent.mkdir(parents=True, exist_ok=True)
        (work / "data" / name).write_bytes(blob)
    out = work / "out"
    out.mkdir()
    cmd = ["blender", "-b", "-P", str(work / "script.py"), "--", "--data", str(work / "data"),
           "--out", str(out), "--frames", f"{first}-{last}", "--gpu", *args]  # fmt: skip
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stdout[-3000:] + r.stderr[-3000:])
    return {p.name: p.read_bytes() for p in sorted(out.iterdir())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frames", default="1-1")
    ap.add_argument("--per", type=int, default=24)
    argv = sys.argv[1:]
    extra = argv[argv.index("--") + 1 :] if "--" in argv else []
    a = ap.parse_args(argv[: argv.index("--")] if "--" in argv else argv)
    first, last = (int(x) for x in a.frames.split("-"))
    data = {str(p.relative_to(a.data)): p.read_bytes() for p in a.data.rglob("*") if p.is_file()}
    chunks = [(s, min(s + a.per - 1, last)) for s in range(first, last + 1, a.per)]
    a.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with app.run():
        script = a.script.read_bytes()
        for files in render.starmap([(script, data, s, e, extra) for s, e in chunks]):
            for name, blob in files.items():
                (a.out / name).write_bytes(blob)
            print(f"{len(files)} frame(s) back, {time.time() - t0:.0f} s", flush=True)
    print(f"{last - first + 1} frames in {time.time() - t0:.0f} s -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
