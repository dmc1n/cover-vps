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

import numpy as np

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
  The x arm is the one drawn along the top of the top view. If the arms' ends slope down
  (the top comes down over the last part of each arm to a lower end wall, a cross line near
  each end in the top view): end_length_cm (how long that part is), end_back_height_cm and
  end_front_height_cm (the end wall's heights at the back and the front); otherwise leave out.
  The strip width is often written in the 3D view (a small size across the top band).
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
OVERRIDES_FILE = Path(__file__).resolve().parents[1] / "config" / "drawing_overrides.json"
OVERRIDES: dict[str, Any] = (
    json.loads(OVERRIDES_FILE.read_text()) if OVERRIDES_FILE.is_file() else {}
)

OUTLINE_MM = 5.0
TOP_PX = 900  # the top view's longest side


def top_view(model: Path) -> Path:
    """The cover seen from straight above, as the drawings' TOP VIEW: every top piece shaded by
    its slope, the seams between pieces as black lines, the overall sizes in the title."""
    import trimesh
    from coverengine.io.model_io import load_model
    from matplotlib.collections import PolyCollection
    from matplotlib.figure import Figure

    hull = load_model(model / "hull.glb")
    m = trimesh.Trimesh(hull.vertices, hull.faces, process=False)
    lab = np.load(model / "hull_parts.npy")
    up = m.face_normals[:, 2] > 0.05  # seen from above
    v = m.vertices
    w, d = np.ptp(v[:, 0]), np.ptp(v[:, 1])
    fig = Figure(figsize=(TOP_PX / 100 * w / max(w, d) + 1, TOP_PX / 100 * d / max(w, d) + 1))
    ax = fig.add_axes((0.04, 0.04, 0.92, 0.88))
    shade = np.clip(0.92 - 1.6 * (1 - m.face_normals[up, 2]), 0.35, 0.92)
    rgb = np.c_[shade, shade, np.minimum(shade + 0.06, 1)]
    ax.add_collection(PolyCollection(m.triangles[up][:, :, :2], facecolors=rgb, edgecolors=rgb,
                                     linewidths=0.3))  # fmt: skip
    adj, edges = m.face_adjacency, m.face_adjacency_edges
    seam = (lab[adj[:, 0]] != lab[adj[:, 1]]) & up[adj[:, 0]] & up[adj[:, 1]]
    open_e = trimesh.grouping.group_rows(m.edges_sorted[np.repeat(up, 3)], require_count=1)
    lines = [v[e][:, :2] for e in edges[seam]]
    lines += [v[e][:, :2] for e in m.edges_sorted[np.repeat(up, 3)][open_e]]
    from matplotlib.collections import LineCollection

    ax.add_collection(LineCollection(lines, colors="black", linewidths=1.0))
    ax.set_xlim(v[:, 0].min() - 20, v[:, 0].max() + 20)
    ax.set_ylim(v[:, 1].min() - 20, v[:, 1].max() + 20)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"TOP VIEW (front at the bottom): {w / 10:.1f} x {d / 10:.1f} cm")
    out = model / "top.png"
    fig.savefig(out, dpi=100)
    return out


COMPARE = """You check whether a program rebuilt a cover workshop's drawing correctly. Image 1 is
the drawing, image 2 the program's cover seen from straight above (like the drawing's TOP VIEW:
the front at the bottom, black lines are the seams between pieces, darker grey is steeper),
image 3 the same cover in 3D (each piece in its own colour, seen from the front right and
above; the program's view may come from another side than the drawing's, so compare shapes,
not which side is in front). The plan view is the most reliable for the seam lines. You get
the sizes the program used (cm) and every flat piece as its outline (the corners in cm, laid
flat; a sloped piece is longer than its plan view; an end piece with five corners is a
pentagon, not a rectangle). Pieces wider than the 150 cm roll are split on
purpose (a seam the drawing may not show), and so is a band longer than the 300 cm the
workshop cuts in one piece; that is not a difference. Two pieces with the same outline are fine
where the drawing has mirror images: a flat piece turned over is its mirror image.
Compare only the shape, the sizes and the seam lines (the lines between pieces): flat strips on
top, slopes, corners, ends, how the pieces meet. Do not count air pockets, elastic, drawcords,
grommets or tie downs (the program adds those to the cut pieces; they are not in image 2), nor
differences in how a picture is drawn. Answer with JSON only:
{"matches": true or false, "differences": ["plain sentences, only real differences"]}"""


def compare(row: dict[str, Any], model: Path, sizes: dict[str, Any], picture: Path,
            params: Any) -> dict[str, Any]:  # fmt: skip
    import shapely

    pattern = json.loads((model / "pattern.json").read_text())
    pieces = []
    for p in pattern["panels"]:
        ring = shapely.Polygon(p["outline_mm"]).simplify(OUTLINE_MM)
        corners = [[round(x / 10, 1), round(y / 10, 1)] for x, y in ring.exterior.coords[:-1]]
        pieces.append({"name": p["name"], "corners": len(corners), "outline_cm": corners})
    parts = [
        {"type": "text", "text": json.dumps({"sizes_cm": sizes, "pieces": pieces})},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,"
                                            + base64.b64encode(picture.read_bytes()).decode()}},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,"
         + base64.b64encode(top_view(model).read_bytes()).decode()}},
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
    fixed = OVERRIDES.get(code, {})  # the owner's corrections win over the AI's reading
    if fixed.get("shape"):
        shape = fixed["shape"]
    sizes = {**sizes, **fixed.get("sizes", {})}
    out["owner_corrected"] = sorted(fixed.get("sizes", {}))
    out.update(shape=shape, sizes=sizes, measured=ans.get("measured") or [],
               notes=ans.get("notes", ""), why_not=ans.get("why_not", ""))  # fmt: skip
    if fixed.get("why_not"):
        out["why_not"] = fixed["why_not"]
    if shape not in ("box", "sloped box", "L shape", "round"):
        return {**out, "status": "not built", "detail": out["why_not"]}
    checked = {
        k: written(float(v), row["sizes_cm"])
        for k, v in sizes.items()
        if k.endswith("_cm") and isinstance(v, (int, float)) and v
    }
    out["size_check"] = checked
    unsure = sorted(
        ({k for k, v in checked.items() if v == "not written"} | set(out["measured"]))
        - set(out["owner_corrected"])
    )
    try:
        text = " ".join(row["text"].lower().split())
        middle = "drawstring in the middle" in text or "drawcord in the middle" in text
        out["middle_cord"] = middle
        model = make(code, shape, sizes, models, note=out.get("notes", ""), middle_cord=middle)
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


def recompare(folder: Path) -> None:
    """Only the comparison again, for the covers already built (covers.json is updated)."""
    rows = {r["code"]: r for r in json.loads((folder / "drawings.json").read_text())}
    results = json.loads((folder / "covers.json").read_text())
    params = Registry.load(None).resolve()

    def again(r: dict[str, Any]) -> dict[str, Any]:
        if not r.get("model_id"):
            return r
        row = rows[r["code"]]
        picture = folder / "pictures" / (Path(row["file"]).stem + ".png")
        check = compare(row, Path("models") / r["model_id"], r["sizes"], picture, params)
        unsure = r.get("detail", "").startswith("sizes not written")
        status = "built, check sizes" if unsure else "built"
        detail = [d for d in r.get("detail", "").split(" | ") if d.startswith("sizes not")]
        if check["matches"] is False:
            status = "built, AI sees differences"
            detail += check["differences"]
        return {**r, "status": status, "detail": " | ".join(detail), "comparison": check}

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(again, results))
    write_results(folder, results)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path, help="the drawings analysis (drawings.json)")
    ap.add_argument("--only", help="codes, comma separated")
    ap.add_argument("--pdfs", type=Path, help="the folder with the PDF drawings")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--compare-only", action="store_true", help="only compare again")
    args = ap.parse_args()
    if args.compare_only:
        recompare(args.folder)
        return 0
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
    if args.only and (args.folder / "covers.json").is_file():  # merge into the earlier run
        done = {r["code"]: r for r in results}
        earlier = json.loads((args.folder / "covers.json").read_text())
        results = [done.pop(r["code"], r) for r in earlier] + list(done.values())
    write_results(args.folder, results)
    return 0


def write_results(folder: Path, results: list[dict[str, Any]]) -> None:
    (folder / "covers.json").write_text(json.dumps(results, indent=1) + "\n")
    keys = ["code", "status", "shape", "pieces", "max_stretch_pct", "detail", "notes", "model_id",
            "sizes", "file"]  # fmt: skip
    with (folder / "covers.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow({**r, "sizes": json.dumps(r.get("sizes", {}))})
    from collections import Counter

    print(Counter(r["status"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
