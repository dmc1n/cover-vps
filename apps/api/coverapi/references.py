"""Reference covers: the owner's own drawings with their 3D models, for learning (ADR-037).

One zip holds pairs with the same name: `1.step` + `1.pdf`, `kota.stp` + `kota.pdf`, ... (folders
inside the zip do not matter). Each pair becomes a model folder `models/ref-<batch>-<name>/` with
the 3D file imported as usual and the drawing kept beside it:

- `reference.pdf`: the owner's drawing as it came;
- `reference.png`: its first page as a picture, for the web app;
- `reference.json`: everything read from the drawing: the texts with their place on the page,
  and the sizes found in them (in mm), for the comparison and for the AI.
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coverapi.store import UPLOAD_SUFFIXES, Store, slug

REFERENCE_PDF = "reference.pdf"
REFERENCE_PNG = "reference.png"
REFERENCE_JSON = "reference.json"
PAGE_DPI = 110  # the drawing as a picture in the web app
# A size in a drawing: a number with a unit (cm, mm, m, in, "), optionally in brackets.
SIZE = re.compile(r"\[?\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m|in|inch|\")(?![a-z])", re.IGNORECASE)
TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4, '"': 25.4}


@dataclass
class Pair:
    name: str
    model: Path | None = None
    drawing: Path | None = None


@dataclass
class Batch:
    id: str
    pairs: list[Pair] = field(default_factory=list)
    unpaired: list[str] = field(default_factory=list)


def unpack(store: Store, zip_path: Path, batch_id: str) -> Batch:
    """Unpack a zip into uploads/<batch>/ and pair the 3D files with the drawings by name."""
    folder = store.uploads / batch_id
    folder.mkdir(parents=True, exist_ok=True)
    found: dict[str, Pair] = {}
    batch = Batch(batch_id)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or "__MACOSX" in info.filename:
                continue
            name = Path(info.filename).name
            if name.startswith("."):
                continue
            stem, suffix = Path(name).stem.lower(), Path(name).suffix.lower()
            if suffix not in UPLOAD_SUFFIXES and suffix != ".pdf":
                batch.unpaired.append(info.filename)
                continue
            dest = folder / name
            with zf.open(info) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            pair = found.setdefault(stem, Pair(stem))
            if suffix == ".pdf":
                pair.drawing = dest
            else:
                pair.model = dest
    for key in sorted(found, key=_natural):
        p = found[key]
        if p.model and p.drawing:
            batch.pairs.append(p)
        else:
            batch.unpaired.append(str((p.model or p.drawing).name))  # type: ignore[union-attr]
    return batch


def _natural(s: str) -> list[Any]:
    """Sort 2 before 10."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def read_drawing(pdf: Path, out_dir: Path) -> dict[str, Any]:
    """The drawing's first page as reference.png, and its texts and sizes as reference.json."""
    import pymupdf

    doc = pymupdf.open(pdf)
    texts: list[dict[str, Any]] = []
    sizes: list[dict[str, Any]] = []
    for page_no in range(doc.page_count):
        page = doc[page_no]
        width, height = page.rect.width, page.rect.height
        for x0, y0, x1, y1, text, *_ in page.get_text("words"):
            texts.append(
                {
                    "page": page_no + 1,
                    "text": text,
                    "at": [round((x0 + x1) / 2 / width, 3), round((y0 + y1) / 2 / height, 3)],
                }
            )
        for line in page.get_text("text").splitlines():
            for m in SIZE.finditer(line):
                value = float(m.group(1).replace(",", "."))
                unit = m.group(2).lower()
                sizes.append(
                    {
                        "page": page_no + 1,
                        "text": m.group(0).strip(" ["),
                        "mm": round(value * TO_MM[unit], 1),
                        "unit": unit,
                        "line": line.strip()[:80],
                    }
                )
        if page_no == 0:
            page.get_pixmap(dpi=PAGE_DPI).save(out_dir / REFERENCE_PNG)
    drawn = sum(len(doc[i].get_drawings()) for i in range(doc.page_count))
    info = {
        "format_version": 1,
        "source": pdf.name,
        "pages": doc.page_count,
        "vector_paths": drawn,  # 0: a scan or photo (then only an image-reading AI can help)
        "texts": texts,
        "sizes": sizes,
        # metric sizes only: drawings often give inches beside cm
        "sizes_mm": sorted({s["mm"] for s in sizes if s["unit"] in ("mm", "cm", "m")}),
    }
    (out_dir / REFERENCE_JSON).write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    return info


def register(store: Store, batch: Batch) -> list[dict[str, Any]]:
    """A model folder per pair, with the drawing in it; returns what to calculate."""
    out = []
    for p in batch.pairs:
        assert p.model is not None and p.drawing is not None
        model_id = store.new_id(f"ref-{batch.id}-{slug(p.name)}")
        d = store.model_dir(model_id)
        d.mkdir(parents=True)
        shutil.copyfile(p.drawing, d / REFERENCE_PDF)
        try:
            info = read_drawing(d / REFERENCE_PDF, d)
            note = f"{info['pages']} page(s), {len(info['sizes_mm'])} size(s) read"
        except Exception as exc:  # noqa: BLE001 - a broken PDF must not stop the batch
            note = f"the drawing could not be read: {exc}"
        cover = {
            "format_version": 1,
            "model_id": model_id,
            "status": "draft",
            "tags": ["reference", f"batch-{batch.id}"],
            "notes": f"Reference {p.name}: {p.model.name} with {p.drawing.name}. {note}",
        }
        (d / "cover.json").write_text(json.dumps(cover, indent=2) + "\n", encoding="utf-8")
        out.append({"model_id": model_id, "name": p.name, "source": str(p.model), "note": note})
    return out
