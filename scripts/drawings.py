"""Read a folder of the owner's cover drawings (PDF) and describe every cover (ADR-043).

    uv run python scripts/drawings.py <folder with PDFs> --out out/drawings/<name>

For each drawing: its texts and sizes (PyMuPDF), the table fields (fabric, colour, tie downs,
grommets, quantity), a picture of the page, and the AI's reading of the picture (furniture type,
cover shape, pieces, skirt band, air pockets, ...). Writes drawings.json, drawings.csv and the
pictures; the AI calls run 4 at a time.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from coverapi.references import SIZE, TO_MM  # noqa: E402
from coverengine.ai import ask_parts  # noqa: E402
from coverengine.params import Registry  # noqa: E402

FIELDS = ("Order Number", "Fabric Type", "Product Number", "Tie Downs", "Color", "Quantity",
          "Grommets")  # fmt: skip
DPI = 110

AI_SYSTEM = """You read technical drawings of outdoor furniture covers made by a cover workshop.
Each drawing shows one cover: views (front, side, top, 3D) with sizes in cm and inches, notes
like air pockets, and a table (fabric, colour, tie downs). Read the picture and the texts and
describe the cover as it is drawn. Count the fabric pieces from the lines between panels in the
views (a panel is an area bounded by seam lines; count both sides even when only one is
visible). Sizes in cm. Use null when the drawing does not show something. Answer with JSON
only:
{"furniture": "sofa | corner sofa | chair | lounge chair | dining chair | daybed | lounger |
  ottoman | table | round table | bench | fire pit | cushion | other",
 "shape": "box | sloped box (back higher) | box with gable | curved | round | L shape |
  U shape | other",
 "description": "one plain sentence",
 "width_cm": n, "depth_cm": n, "height_cm": n,
 "front_height_cm": n, "back_height_cm": n,
 "skirt_band_cm": n,
 "pieces": n,
 "pieces_list": ["top", "front", ...],
 "top": "flat | sloped | gabled | domed | follows the furniture",
 "air_pockets": n, "air_pocket_places": "plain words",
 "opening": "open at the bottom | other",
 "fastening": "elastic | drawcord | ties | straps | other",
 "support_under_cover": "none | balloon | frame | unknown",
 "symmetric_left_right": true,
 "mirror_of": "code of the drawing it mirrors, or null",
 "fabric": "from the table", "colour": "from the table", "tie_downs": "from the table",
 "grommets": "from the table",
 "special": ["anything unusual: cut-outs for legs, zips, flaps, handles, ..."]}"""


def _fields(text: str) -> dict[str, str]:
    out = {}
    lines = [t.strip() for t in text.splitlines() if t.strip()]
    for f in FIELDS:
        for t in lines:
            if t.startswith(f):
                rest = t.split(":", 1)[1].strip() if ":" in t else ""
                out[f] = rest
    return out


def read(pdf: Path, out: Path, params: Any, use_ai: bool) -> dict[str, Any]:
    doc = pymupdf.open(pdf)
    page = doc[0]
    text = "\n".join(doc[i].get_text("text") for i in range(doc.page_count))
    sizes = sorted(
        {
            round(float(m.group(1).replace(",", ".")) * TO_MM[m.group(2).lower()] / 10, 1)
            for m in SIZE.finditer(text)
            if m.group(2).lower() in ("mm", "cm", "m")
        }
    )
    picture = out / "pictures" / (pdf.stem + ".png")
    picture.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=DPI).save(picture)
    m = re.match(r"cover (\d+) - (.+)", pdf.stem, re.IGNORECASE)
    row: dict[str, Any] = {
        "file": pdf.name,
        "number": int(m.group(1)) if m else None,
        "code": m.group(2) if m else pdf.stem,
        "pages": doc.page_count,
        "vector_paths": len(page.get_drawings()),
        "images": len(page.get_images()),
        "sizes_cm": sizes,
        "inches_only": "All Dimensions are in inches" in text,
        "table": _fields(text),
        "text": text[:3000],
    }
    if use_ai:
        data = base64.b64encode(picture.read_bytes()).decode()
        parts = [
            {"type": "text", "text": f"Drawing {pdf.name}. Its texts:\n{text[:3000]}"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
        ]
        try:
            row["ai"] = ask_parts(params, AI_SYSTEM, parts)
            row["ai"].pop("_usage", None)
        except Exception as exc:  # noqa: BLE001 - one drawing must not stop the rest
            row["ai"] = {"error": str(exc)}
    return row


CSV_KEYS = ("number", "code", "furniture", "shape", "pieces", "width_cm", "depth_cm",
            "height_cm", "front_height_cm", "back_height_cm", "skirt_band_cm", "top",
            "air_pockets", "air_pocket_places", "fastening", "support_under_cover",
            "symmetric_left_right", "mirror_of", "fabric", "colour", "tie_downs", "description",
            "special", "file")  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    params = Registry.load(None).resolve()
    pdfs = sorted(args.folder.glob("*.pdf"), key=lambda p: [
        int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)])  # fmt: skip
    args.out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda p: read(p, args.out, params, not args.no_ai), pdfs))
    (args.out / "drawings.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    with (args.out / "drawings.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(CSV_KEYS))
        w.writeheader()
        for r in rows:
            ai = r.get("ai") or {}
            w.writerow(
                {
                    **{k: ai.get(k) for k in CSV_KEYS if k in ai},
                    "number": r["number"],
                    "code": r["code"],
                    "special": "; ".join(ai.get("special") or []),
                    "file": r["file"],
                }
            )
    errors = sum(1 for r in rows if "error" in (r.get("ai") or {}))
    print(f"{len(rows)} drawings -> {args.out} ({errors} AI errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
