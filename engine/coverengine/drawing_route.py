"""Route A: the workshop's drawing (PDF) → a cover, read by the program itself (ADR-081).

The team (6 October 2026) asked for two routes only: a drawing → a cover, and a 3D cover surface →
a cover. This is the first, as one step (`cover drawing-build`, and the upload in the web app):

1. **Read** with one AI-free reader chain:
   a. a closed free outline drawn as vector lines, scaled by its written circumference or length
      (drawing_vectors, ADR-072): the plan straight up to the written height;
   b. otherwise the views: the silhouettes, the scale from the size arrows, the plan cut by the
      elevations, the best fit to the drawing's 3D view (drawing_views, drawing_solid, ADR-075).
   A shape is only taken when it fits the drawing's 3D view at least `drawing.min_iou`.
2. **Nothing is guessed.** When neither reader is sure, the cover is marked "needs a person" with
   the reasons; no surface is built, an existing cover is left as it is.
3. **The features** from the drawing's text: the vent count (written, or the arrows from the label)
   wins over the one-per-metre rule (`features.vents_total`).
4. **The pieces** the program made are joined where there is no crease (drawn_merge, ADR-076),
   written as a cover surface with one part per piece, and from there it is route B: import as a
   cover surface, hull, cut, flatten, export, preview.

What was read is kept in drawing_read.json (for the Desk's card): the reader, the views, the scale
and how it was found, the sizes, the written sizes that contradict each other (S45: 152.4 against
141.1 in round), the vents and where their number came from, and the fit to the 3D view.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import trimesh

from coverengine.errors import CoverError
from coverengine.params import EffectiveParams

STEPS = ("hull", "cut", "flatten", "export", "preview")
READ_FILE = "drawing_read.json"
SURFACE_FILE = "drawing-surface.glb"
NEEDS_PERSON = "needs a person"
JOINABLE = ("swept", "outline", "views")  # the program made these seams
SCALE_DIGITS = 5  # param-ok: decimals of the scale kept in drawing_read.json


def roll_mm(params: EffectiveParams) -> float:
    """The width a piece may have before allowances: the roll minus a stitch allowance each side."""
    return float(params["roll.usable_width_mm"]) - 2 * float(params["stitching.allowance_mm"])  # type: ignore[arg-type]


def surface(pieces: list[Any], shape: str, params: EffectiveParams) -> trimesh.Scene:
    """The drawn pieces as a scene with one part per piece; pieces the program made are joined
    where there is no crease (ADR-076)."""
    from coverengine.drawn import scene

    sc = scene(pieces)
    if shape not in JOINABLE:
        return sc
    from coverengine.drawn_merge import merge

    parts = [(str(n), sc.geometry[sc.graph[n][1]].copy()) for n in sc.graph.nodes_geometry]
    joined = merge(parts, roll_mm(params), float(params["drawn.merge_fold_deg"]),  # type: ignore[arg-type]
                   float(params["drawn.merge_max_stretch_pct"]))  # type: ignore[arg-type]  # fmt: skip
    out = trimesh.Scene()
    for name, m in joined:
        out.add_geometry(m, node_name=name, geom_name=name)
    return out


def _mesh(sc: trimesh.Scene) -> trimesh.Trimesh:
    m = trimesh.util.concatenate(list(sc.dump()))
    assert isinstance(m, trimesh.Trimesh)
    return m


def _views_info(read: dict[str, Any]) -> dict[str, Any]:
    return {
        "views": [
            {
                "kind": v.kind,
                "page": v.page + 1,
                "size_cm": [round(float(x) * float(v.meta.get("scale", 0)), 1) for x in v.size],
            }
            for v in read["views"]
        ],  # fmt: skip
        "scale_cm_per_pt": round(float(read["scale_cm_per_pt"]), SCALE_DIGITS),
        "scale_from": read["scale_from"],
        "sizes_cm": read["sizes_cm"],
        "dimensions": [
            {"cm": round(d.value_cm, 1), "page": d.page + 1, "text": d.text}
            for d in read["dimensions"]
        ],  # fmt: skip
    }


def read(pdf: Path, params: EffectiveParams) -> dict[str, Any]:
    """The reader chain. {"status": "built" | NEEDS_PERSON, "reader", "shape", "pieces", "info",
    "reasons"}; `pieces` only when built."""
    from coverengine import drawing_solid, drawing_vectors, drawn

    min_iou = float(params["drawing.min_iou"])  # type: ignore[arg-type]
    roll = roll_mm(params)
    reasons: list[str] = []
    info: dict[str, Any] = {}
    views: dict[str, Any] | None = None
    iso = None
    try:
        from coverengine import drawing_views

        views = drawing_views.read(pdf)
        info["views"] = _views_info(views)
        iso = next((v for v in views["views"] if v.kind == "iso"), None)
    except Exception as exc:  # noqa: BLE001 - a drawing the views reader cannot read
        reasons.append(f"the views could not be read: {exc}")

    # a. a closed free outline (a kidney, a lens) straight up
    outline = drawing_vectors.outline_shape(pdf)
    if outline and "shape" in outline:
        pieces = drawn.build("outline", outline["shape"], roll)
        fit = None
        if iso is not None:
            fit = drawing_solid.iso_fit(_mesh(drawn.scene(pieces)), iso, mirror=True)[0]
        info["outline"] = {k: outline[k] for k in ("scaled_by", "conflicts", "plan_cm", "sizes")}
        info["outline"]["fits_3d_view"] = None if fit is None else round(fit, 3)
        if fit is None or fit >= min_iou:
            return {"status": "built", "reader": "outline", "shape": "outline", "pieces": pieces,
                    "info": info, "reasons": []}  # fmt: skip
        reasons.append(f"the drawn outline fits the 3D view only {fit:.0%}")
    elif outline and "error" in outline:
        reasons.append(f"a closed outline is drawn, but: {outline['error']}")

    # b. the views: the plan cut by the elevations, checked against the 3D view
    if views is not None:
        kinds = [v.kind for v in views["views"]]
        if "plan" not in kinds:
            reasons.append("no top view found (only " + (", ".join(kinds) or "no views") + ")")
        if iso is None:
            reasons.append("no 3D view to check the shape against")
        if not views["dimensions"]:
            reasons.append("no size arrows found: " + views["scale_from"])
        try:
            best = drawing_solid.best_solid(pdf)
        except Exception as exc:  # noqa: BLE001
            best = {"best": None}
            reasons.append(f"no shape could be built from the views: {exc}")
        b = best["best"]
        if b is not None:
            info["solid"] = {"how": b["how"], "fits_3d_view": round(float(b["iou"]), 3),
                             "candidates": len(best["candidates"])}  # fmt: skip
            if iso is not None and b["iou"] >= min_iou:
                return {"status": "built", "reader": "views", "shape": "views",
                        "pieces": drawing_solid.pieces(b["solid"], roll), "info": info,
                        "reasons": []}  # fmt: skip
            if iso is not None:
                reasons.append(f"the best shape from the views fits the 3D view only "
                               f"{b['iou']:.0%} (needs {min_iou:.0%})")  # fmt: skip
    return {"status": NEEDS_PERSON, "reader": None, "shape": None, "pieces": None, "info": info,
            "reasons": reasons or ["nothing on the drawing could be read"]}  # fmt: skip


def _write(path: Path, doc: Any) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def build(
    pdf: Path,
    model_dir: Path,
    params: EffectiveParams,
    code: str | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Read the drawing and, when sure, build and calculate its cover in `model_dir` (a new
    model, or a new revision of an existing drawing cover). Never deletes the model's
    reference/, desk.json or revisions/."""
    from coverengine.catalogue import set_info
    from coverengine.cli import main as cover
    from coverengine.drawing_vectors import features
    from coverengine.io.kind import confirm

    model_dir.mkdir(parents=True, exist_ok=True)
    ref = model_dir / "reference.pdf"
    if pdf.resolve() != ref.resolve():
        shutil.copyfile(pdf, ref)
    code = code or model_dir.name.removeprefix("drawing-").upper()
    feats = features(ref)
    _write(model_dir / "drawing_features.json", feats)
    res = read(ref, params)
    doc: dict[str, Any] = {
        "code": code, "time": time.time(), "status": res["status"], "reader": res["reader"],
        "reasons": res["reasons"], "features": feats, **res["info"],
    }  # fmt: skip
    _write(model_dir / READ_FILE, doc)
    if res["status"] != "built":
        # the Desk puts it at the top ("person to check"), the reasons in place of an AI verdict
        why = "The program could not read this drawing surely: " + "; ".join(res["reasons"])
        _write(model_dir / "check.json", {
            "code": code, "outcome": "person to check", "source": "drawing route",
            "gemini": {"summary": why, "differences": res["reasons"]}})  # fmt: skip
        log(f"{code}: {NEEDS_PERSON}: " + "; ".join(res["reasons"]))
        return doc
    sc = surface(res["pieces"], res["shape"], params)
    src = model_dir / SURFACE_FILE
    sc.export(src)
    doc["pieces_drawn"] = len(sc.geometry)
    if cover(["import", str(src), "--out", str(model_dir), "--units", "mm", "--up", "z"]):
        raise CoverError(f"{code}: the drawn cover surface could not be imported")
    confirm(model_dir, "cover")
    cj = model_dir / "cover.json"
    cover_doc = json.loads(cj.read_text(encoding="utf-8"))
    mine = cover_doc.setdefault("parameters", {})
    mine.setdefault("hull", {})["top"] = "given"
    if feats.get("vents_total"):
        mine.setdefault("features", {})["vents_total"] = int(feats["vents_total"])
        mine["features"].pop("vents_min", None)
    else:
        mine.get("features", {}).pop("vents_total", None)
    cj.write_text(json.dumps(cover_doc, indent=2) + "\n", encoding="utf-8")
    how = res["info"].get("solid", {}).get("how") or ["the drawn outline straight up"]
    set_info(model_dir, {
        "tags": sorted(set(cover_doc.get("tags") or []) | {"drawing", "reference"}),
        "notes": f"Drawing {code}: read by the program itself (ADR-081): {res['reader']}, "
                 f"{', '.join(how)}.",
    })  # fmt: skip
    for step in STEPS:
        log(f"{code}: {step}")
        if cover([step, str(model_dir)]):
            raise CoverError(f"{code}: cover {step} failed")
    fin = json.loads((model_dir / "finished.json").read_text(encoding="utf-8"))
    doc["pieces"] = sum(1 for p in fin["pieces"] if not str(p["name"]).startswith("vent-"))
    doc["vents"] = sum(int(p["quantity"]) for p in fin["pieces"] if p["name"] == "vent-hood")
    _write(model_dir / READ_FILE, doc)
    stale = model_dir / "check.json"  # an old verdict was about the cover before this one
    if stale.is_file() and json.loads(stale.read_text()).get("source") == "drawing route":
        stale.unlink()
    log(f"{code}: built ({res['reader']}), {doc['pieces']} pieces, {doc['vents']} vents")
    return doc
