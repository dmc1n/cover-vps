"""All the owner's cover drawings as cover models (ADR-046).

    uv run python scripts/drawing_covers.py out/drawings/covers-and-all --pdfs <PDF folder>
        [--only C6,S22]

For every drawing: the AI reads the shape and its sizes into the shape's form (coverengine/
drawn.py); the program checks that every size is written on the drawing (or the sum or
difference of two written sizes) and marks the others; the cover is built as
models/drawing-<code>/ and calculated. Results: out/drawings/<...>/covers.json and covers.csv.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverengine.ai import ask_parts  # noqa: E402
from coverengine.params import Registry  # noqa: E402
from drawing_cover import make  # noqa: E402

SYSTEM = """You turn a cover workshop's technical drawing into the sizes a program needs to
rebuild the cover exactly. The drawing shows one cover (views with sizes; inch drawings give cm
in brackets, e.g. "33.46 (85 cm)"). Choose the shape and fill in its sizes in cm:

- "box": flat top, four upright walls. length_cm, depth_cm, height_cm.
- "sloped box": back higher than the front, a straight slope between. length_cm (along the
  back), depth_cm, back_height_cm, front_height_cm, back_strip_cm (depth of a flat strip on top
  along the back, 0 only if the slope clearly starts at the back edge), front_strip_cm (flat
  strip along the front, usually 0).
- "L shape": a sloped box along two arms meeting at a corner, high at the outside (back), low
  at the inside (front). x_length_cm and y_length_cm (outside lengths of the two arms),
  x_arm_depth_cm and y_arm_depth_cm (how deep each arm is), x_back_strip_cm and
  y_back_strip_cm (flat strip along the back of each arm; 0 only if clearly none), back_height_cm,
  front_height_cm, strip_corner: "mitre" if the strips meet in a diagonal line at the corner,
  "x" if the strip of the x arm runs through to the outside corner, "y" if the other one does.
  The x arm is the one drawn along the top of the top view.
- "round": a cylinder. diameter_cm, height_cm, band_pieces (how many pieces the side band is,
  counted from the vertical seams drawn on the side; at least 2).
- "other": anything else (curved, U shape, a slope at one end only, steps, cut-outs): then
  explain in why_not.

Use the sizes written on the drawing. If the shape needs a size that is not written (often the
flat strip along the back: drawn as a separate band on top but without a size), measure it on
the picture, using a written size in the same view as the scale, and list its key in
"measured". Never put 0 for a strip that is drawn. Answer with JSON only:
{"shape": "...", "sizes": {...}, "measured": ["keys"], "why_not": "for other: what does not fit",
 "notes": "anything the shape does not capture (a band, flaps, zips), or empty"}"""

TOLERANCE_CM = 0.6

COMPARE = """You check whether a program rebuilt a cover workshop's drawing correctly. Image 1 is
the drawing, image 2 the program's cover (each piece in its own colour, seen from the front
right and above). You get the sizes the program used (cm) and its pieces (net sizes in mm).
Compare only the shape, the sizes and the seam lines (the lines between pieces): flat strips on
top, slopes, corners, ends, how the pieces meet. Do not count air pockets, elastic, drawcords,
grommets or tie downs (the program adds those to the cut pieces; they are not in image 2), nor
differences in how a picture is drawn. Answer with JSON only:
{"matches": true or false, "differences": ["plain sentences, only real differences"]}"""


def compare(row: dict[str, Any], model: Path, sizes: dict[str, Any], picture: Path,
            params: Any) -> dict[str, Any]:  # fmt: skip
    pattern = json.loads((model / "pattern.json").read_text())
    pieces = [
        {"name": p["name"], "net_mm": [round(p["flat_width_mm"]), round(p["flat_length_mm"])]}
        for p in pattern["panels"]
    ]
    parts = [
        {"type": "text", "text": json.dumps({"sizes_cm": sizes, "pieces": pieces})},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,"
                                            + base64.b64encode(picture.read_bytes()).decode()}},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,"
         + base64.b64encode((model / "cover.png").read_bytes()).decode()}},
    ]  # fmt: skip
    try:
        ans = ask_parts(params, COMPARE, parts)
        return {"matches": bool(ans.get("matches")), "differences": ans.get("differences", [])}
    except Exception as exc:  # noqa: BLE001
        return {"matches": None, "differences": [f"no comparison: {exc}"]}


def written(value: float, sizes: list[float]) -> str:
    """'written', 'derived' (sum or difference of two written sizes) or 'not written'."""
    if any(abs(value - s) <= TOLERANCE_CM for s in sizes):
        return "written"
    for a in sizes:
        for b in sizes:
            if abs(value - (a + b)) <= TOLERANCE_CM or abs(value - abs(a - b)) <= TOLERANCE_CM:
                return "derived"
    return "not written"


def one(row: dict[str, Any], pictures: Path, params: Any, models: Path) -> dict[str, Any]:
    code = row["code"]
    out: dict[str, Any] = {"code": code, "file": row["file"]}
    picture = pictures / (Path(row["file"]).stem + ".png")
    data = base64.b64encode(picture.read_bytes()).decode()
    parts = [
        {"type": "text", "text": f"Drawing {row['file']}. Its texts:\n{row['text'][:3000]}"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}},
    ]
    try:
        ans = ask_parts(params, SYSTEM, parts)
    except Exception as exc:  # noqa: BLE001
        return {**out, "status": "AI error", "detail": str(exc)}
    shape, sizes = ans.get("shape"), ans.get("sizes") or {}
    out.update(shape=shape, sizes=sizes, measured=ans.get("measured") or [],
               notes=ans.get("notes", ""), why_not=ans.get("why_not", ""))  # fmt: skip
    if shape not in ("box", "sloped box", "L shape", "round"):
        return {**out, "status": "not built", "detail": ans.get("why_not", "")}
    checked = {
        k: written(float(v), row["sizes_cm"])
        for k, v in sizes.items()
        if k.endswith("_cm") and isinstance(v, (int, float)) and v
    }
    out["size_check"] = checked
    unsure = sorted({k for k, v in checked.items() if v == "not written"} | set(out["measured"]))
    try:
        model = make(code, shape, sizes, models, note=out.get("notes", ""))
    except BaseException as exc:  # noqa: BLE001 - one drawing must not stop the rest
        return {**out, "status": "failed", "detail": str(exc) or traceback.format_exc()[-300:]}
    import shutil

    shutil.copyfile(Path(row["source_pdf"]), model / "reference.pdf")  # the "Your drawing" tab
    shutil.copyfile(picture, model / "reference.png")
    pattern = json.loads((model / "pattern.json").read_text())
    check = compare(row, model, sizes, picture, params)
    status = "built"
    detail = []
    if unsure:
        status = "built, check sizes"
        detail.append("sizes not written on the drawing: " + ", ".join(unsure))
    if check["matches"] is False:
        status = "built, AI sees differences"
        detail += check["differences"]
    out.update(
        model_id=model.name,
        pieces=pattern["summary"]["panels"],
        max_stretch_pct=pattern["summary"]["max_stretch_pct"],
        status=status,
        detail=" | ".join(detail),
        comparison=check,
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path, help="the drawings analysis (drawings.json)")
    ap.add_argument("--only", help="codes, comma separated")
    ap.add_argument("--pdfs", type=Path, required=True, help="the folder with the PDF drawings")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    rows = json.loads((args.folder / "drawings.json").read_text())
    for r in rows:
        r["source_pdf"] = str(args.pdfs / r["file"])
    if args.only:
        wanted = set(args.only.split(","))
        rows = [r for r in rows if r["code"] in wanted]
    params = Registry.load(None).resolve()
    with ThreadPoolExecutor(args.workers) as pool:
        results = list(
            pool.map(lambda r: one(r, args.folder / "pictures", params, Path("models")), rows)
        )
    (args.folder / "covers.json").write_text(json.dumps(results, indent=1) + "\n")
    keys = ["code", "status", "shape", "pieces", "max_stretch_pct", "detail", "notes", "model_id",
            "sizes", "file"]  # fmt: skip
    with (args.folder / "covers.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow({**r, "sizes": json.dumps(r.get("sizes", {}))})
    from collections import Counter

    print(Counter(r["status"] for r in results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
