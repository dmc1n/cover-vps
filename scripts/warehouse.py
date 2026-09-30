"""Fetch products from SketchUp 3D Warehouse (public models only; no login).

    uv run python scripts/warehouse.py list <creator-id> > catalogue.json
    uv run python scripts/warehouse.py fetch catalogue.json --out ~/suns/glb
    uv run python scripts/warehouse.py photos --models models --tag suns

`list` writes {entity id: title} of every model a creator published (the creator id is in the
page source of the creator's 3D Warehouse page). `fetch` downloads each model's GLB (skipping
ones already there; some models need a logged-in account and are reported). `photos` puts the
3D Warehouse thumbnail of each model into its folder as product.jpg, for the catalogue page; it
finds the entity id in the model's notes ("3D Warehouse <id>").
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://3dwarehouse.sketchup.com/warehouse/v1.0"
PAGE = 100
ID = re.compile(r"3D Warehouse ([0-9a-f-]{36})")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "cover-pattern-engine"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - fixed https host
        data: bytes = r.read()
        return data


def list_creator(creator: str) -> dict[str, str]:
    out: dict[str, str] = {}
    offset = 0
    while True:
        q = urllib.parse.urlencode(
            {"fq": f"creator.id=={creator}", "contentType": "3dw", "count": PAGE, "offset": offset}
        )
        page = json.loads(get(f"{API}/entities?{q}"))
        for e in page.get("entries", []):
            out[e["id"]] = e["title"]
        offset += PAGE
        if offset >= int(page.get("total", 0)):
            return out


def fetch(catalogue: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for entity, title in json.loads(catalogue.read_text()).items():
        dest = out / f"{entity}.glb"
        if dest.is_file() and dest.stat().st_size:
            continue
        try:
            dest.write_bytes(get(f"{API}/entities/{entity}/binaries/glb?download=true"))
        except Exception as exc:  # noqa: BLE001 - report and go on
            print(f"no GLB for {title} ({entity}): {exc}")


def photos(models: Path, tag: str | None) -> None:
    n = 0
    for d in sorted(models.iterdir()):
        cover = d / "cover.json"
        if not cover.is_file():
            continue
        doc = json.loads(cover.read_text())
        if tag and tag not in doc.get("tags", []):
            continue
        m = ID.search(doc.get("notes", ""))
        if not m or (d / "product.jpg").is_file():
            continue
        try:
            (d / "product.jpg").write_bytes(
                get(f"{API}/entities/{m.group(1)}/binaries/bot_lt?download=true")
            )
            n += 1
        except Exception as exc:  # noqa: BLE001
            print(f"no photo for {d.name}: {exc}")
    print(f"{n} photo(s)")


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "list":
        print(json.dumps(list_creator(argv[1]), indent=1))
        return 0
    if len(argv) >= 4 and argv[0] == "fetch" and argv[2] == "--out":
        fetch(Path(argv[1]), Path(argv[3]).expanduser())
        return 0
    if argv and argv[0] == "photos":
        args = dict(zip(argv[1::2], argv[2::2], strict=False))
        photos(Path(args.get("--models", "models")), args.get("--tag"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
