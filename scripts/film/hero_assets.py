"""Fetch the CC0 assets the hero film uses (ADR-101) from Poly Haven into one folder.

Only scanned textures, an HDRI for the light and a plant model; the furniture, the cover, its
seams, the cut pieces and the rain are our own data. Poly Haven assets are CC0 (no attribution
required; credited in docs/LICENSES.md all the same). Nothing is fetched twice.

    uv run python scripts/film/hero_assets.py ~/opt/film2/assets
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com/files/"
HDRIS = {"hotel_rooftop_balcony": "4k", "kloofendal_overcast": "4k"}
# texture: (resolution, maps)
TEXTURES = {
    "stretch_poplin": ("2k", ["Diffuse", "nor_gl", "Rough"]),  # a fine plain weave
    "large_grey_tiles": ("2k", ["Diffuse", "nor_gl", "Rough"]),
    "white_plaster_02": ("2k", ["Diffuse", "nor_gl", "Rough"]),
    "concrete_floor_02": ("2k", ["Diffuse", "nor_gl", "Rough"]),
}
MODELS = {"potted_plant_04": "2k"}
UA = {"User-Agent": "cover-studio-film/1.0"}


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def save(url: str, path: Path) -> None:
    if path.is_file() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(get(url))
    print("fetched", path.name)


def main(out: Path) -> None:
    for name, res in HDRIS.items():
        files = json.loads(get(API + name))
        save(files["hdri"][res]["hdr"]["url"], out / f"{name}_{res}.hdr")
    for name, (res, maps) in TEXTURES.items():
        files = json.loads(get(API + name))
        for m in maps:
            save(files[m][res]["jpg"]["url"], out / name / f"{m}.jpg")
    for name, res in MODELS.items():
        files = json.loads(get(API + name))
        g = files["gltf"][res]["gltf"]
        save(g["url"], out / name / f"{name}.gltf")
        for rel, f in g["include"].items():
            save(f["url"], out / name / rel)


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
