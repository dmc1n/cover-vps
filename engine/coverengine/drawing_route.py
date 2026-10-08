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
import math
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
JOINABLE = ("swept", "outline", "views", "isofit")  # the program made these seams
SCALE_DIGITS = 5  # param-ok: decimals of the scale kept in drawing_read.json


CM_TO_MM = 10.0  # param-ok: unit
CORRECTION_CM = 1.0  # param-ok: a corrected size names a read size within 1 cm ...
CORRECTION_SHARE = 0.01  # param-ok: ... or 1 %


def roll_mm(params: EffectiveParams) -> float:
    """The width a piece may have before allowances: the roll minus a stitch allowance each side."""
    return float(params["roll.usable_width_mm"]) - 2 * float(params["stitching.allowance_mm"])  # type: ignore[arg-type]


def surface(pieces: list[Any], shape: str, params: EffectiveParams) -> trimesh.Scene:
    """The drawn pieces as a scene with one part per piece; pieces the program made are joined
    where there is no crease (ADR-076)."""
    from coverengine.drawn import scene
    from coverengine.drawn_merge import absorb_slivers, merge

    sc = scene(pieces)
    parts = [(str(n), sc.geometry[sc.graph[n][1]].copy()) for n in sc.graph.nodes_geometry]
    stretch = float(params["drawn.merge_max_stretch_pct"])  # type: ignore[arg-type]
    if shape in JOINABLE:
        parts = merge(parts, roll_mm(params), float(params["drawn.merge_fold_deg"]),  # type: ignore[arg-type]
                      stretch)  # fmt: skip
    # no slivers, whoever made the seams (ADR-097)
    joined = absorb_slivers(parts, float(params["seams.min_piece_width_mm"]), roll_mm(params),  # type: ignore[arg-type]
                            stretch)  # fmt: skip
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


def _fixes(corrections: list[dict[str, Any]] | None) -> list[tuple[float, float]]:
    """(read cm, right cm) from the Desk's size corrections (ADR-082)."""
    out = []
    for c in corrections or []:
        try:
            r, ok = float(c.get("read_cm") or 0), float(c.get("correct_cm") or 0)
        except (TypeError, ValueError):
            continue
        if r > 0 and ok > 0:
            out.append((r, ok))
    return out


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= max(CORRECTION_CM, CORRECTION_SHARE * max(a, b))


def _correct_outline(outline: dict[str, Any], fixes: list[tuple[float, float]]) -> list[str]:
    """A person said a read size is wrong: the plan (circumference, longest) is scaled, the
    height replaced. Returns what was applied."""
    done = []
    shape, plan = outline["shape"], outline["plan_cm"]
    for r, ok in fixes:
        if _same(r, float(plan["circumference"])) or _same(r, float(plan["longest"])):
            k = ok / r
            shape["outline_cm"] = [[x * k, y * k] for x, y in shape["outline_cm"]]
            plan["circumference"] = round(float(plan["circumference"]) * k, 1)
            plan["longest"] = round(float(plan["longest"]) * k, 1)
            done.append(f"plan scaled by {k:.3f} ({r:g} -> {ok:g} cm)")
        elif _same(r, float(shape["height_cm"])):
            shape["height_cm"] = ok
            done.append(f"height {r:g} -> {ok:g} cm")
    return done


def _correct_solid(mesh: trimesh.Trimesh, fixes: list[tuple[float, float]]) -> list[str]:
    """A person said a read size is wrong: the solid is stretched along the axis whose extent
    it is (x, y or z)."""
    done = []
    for r, ok in fixes:
        ext = mesh.extents / CM_TO_MM
        for axis, name in enumerate("xyz"):
            if _same(r, float(ext[axis])):
                v = mesh.vertices.copy()
                lo = v[:, axis].min()
                v[:, axis] = lo + (v[:, axis] - lo) * ok / r
                mesh.vertices = v
                done.append(f"{name} {r:g} -> {ok:g} cm")
                break
    return done


def _isofit(
    pdf: Path,
    views: dict[str, Any],
    params: EffectiveParams,
    solid: dict[str, Any] | None,
    info: dict[str, Any],
    reasons: list[str],
) -> dict[str, Any] | None:
    """The fitted heights when they can be taken and beat the views' shape on the 3D view
    (silhouette plus creases, by `drawing.isofit_min_gain`); else None, with the reason."""
    from coverengine import drawing_isofit

    try:
        res = drawing_isofit.fit(pdf, views, params, roll_mm(params) / CM_TO_MM)
    except Exception as exc:  # noqa: BLE001 - a drawing the fit cannot read
        reasons.append(f"the heights could not be fitted to the 3D view: {exc}")
        return None
    best = res["fit"]
    if best is None:
        info["isofit"] = {"why_not": [res["why"]]}
        return None
    why = drawing_isofit.why_not(best, params)
    info["isofit"] = {**drawing_isofit.info(best), "why_not": why}
    if why:
        if solid is None or solid["iou"] < float(params["drawing.min_iou"]):  # type: ignore[arg-type]
            reasons += why
        return None
    if solid is not None:
        theirs = drawing_isofit.solid_score(solid["solid"], pdf, views, params)
        info["isofit"]["views_shape_score"] = round(theirs["score"], 3)
        info["isofit"]["score"] = round(float(best["score"]), 3)
        if best["score"] < theirs["score"] + float(params["drawing.isofit_min_gain"]):  # type: ignore[arg-type]
            info["isofit"]["why_not"] = ["the views' own shape fits the 3D view as well"]
            return None
    info["isofit"]["how"] = drawing_isofit.describe(best)
    return best


SIDE_AGREE = 0.03  # param-ok: a side view's width agrees with a written size within 3 %


def _side_view(views: dict[str, Any]) -> Any:
    """The drawing's only picture when it is a side view (no slant lines of a 3D view), else
    None. drawing_views calls a lone picture the 3D view; its iso_share says otherwise."""
    from coverengine.drawing_views import ISO_SHARE

    vs = views.get("views") or []
    if len(vs) != 1 or not views.get("sizes_cm"):
        return None
    v = vs[0]
    return v if float(v.meta.get("iso_share", 1.0)) < ISO_SHARE and "scale" in v.meta else None


def read(
    pdf: Path, params: EffectiveParams, corrections: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
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
    fixes = _fixes(corrections)
    outline = drawing_vectors.outline_shape(pdf)
    if outline and "shape" in outline:
        if fixes:
            info["corrections_applied"] = _correct_outline(outline, fixes)
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

    # b. a C or U shaped sofa: the exact top view, the written back profile, the drawn seams
    #    (ADR-084), trusted when the back edge's segments match the written lengths
    try:
        from coverengine import plan_profile

        pp = plan_profile.read_drawing(pdf)
    except Exception as exc:  # noqa: BLE001 - not this kind of drawing
        pp = {"error": str(exc)}
    if "shape" in pp:
        lengths = plan_profile.check_lengths(pdf, pp["shape"])
        info["plan_profile"] = {"profile": pp["profile"], "scale_fix": pp["scale_fix"],
                                "seams": pp["seams"], "lengths": lengths}  # fmt: skip
        if lengths["trusted"]:
            pieces = plan_profile.build(pp["shape"], roll,
                                        float(params["seams.max_skirt_panel_mm"]))  # type: ignore[arg-type]  # fmt: skip
            return {"status": "built", "reader": "plan-profile", "shape": "plan-profile",
                    "pieces": pieces, "info": info, "reasons": []}  # fmt: skip
        reasons.append(f"a C or U shape: only {lengths['matched']} of {lengths['of']} lengths "
                       "along the back match the drawing")  # fmt: skip

    # b2. one side view alone (U2, a parasol cover; Rens: "should be cylindrical, the drawing is
    #     a side view"): a single picture with no 3D slant lines draws a round object from the
    #     side; scaled by its largest written size (the height), taken when its width is a
    #     written size too
    side = _side_view(views) if views is not None else None
    if side is not None:
        from coverengine import drawing_given

        tall = max(views["sizes_cm"])  # type: ignore[index]
        prof = drawing_given.side_profile(side.outline * float(side.meta["scale"]), tall)
        wide = 2 * max(r for r, _ in prof)
        hit = [s for s in views["sizes_cm"] if abs(s - wide) <= SIDE_AGREE * s]  # type: ignore[index]
        info["side_view"] = {"profile_cm": prof, "height_cm": tall, "width_cm": round(wide, 1),
                             "width_written": bool(hit)}  # fmt: skip
        if hit:
            return {"status": "built", "reader": "side view", "shape": "revolve",
                    "pieces": drawing_given.revolve({"profile": prof}, roll), "info": info,
                    "reasons": []}  # fmt: skip
        reasons.append(f"one side view: its width {wide:.1f} cm is no written size")

    # c. the views: the plan cut by the elevations, checked against the 3D view
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
        if b is not None and fixes:
            info["corrections_applied"] = _correct_solid(b["solid"], fixes)
        if b is not None:
            info["solid"] = {"how": b["how"], "fits_3d_view": round(float(b["iou"]), 3),
                             "candidates": len(best["candidates"])}  # fmt: skip
        # d. the heights over the top view fitted to the 3D view (phase 4, ADR-094): a corner sofa
        #    whose back is higher than its seat, drawn with no elevation; taken when it fits and
        #    scores better than the views' shape (a size corrected at the Desk keeps the views)
        fitted = (
            _isofit(pdf, views, params, b, info, reasons) if iso is not None and not fixes else None
        )
        if fitted is not None:
            from coverengine import drawing_isofit

            fall = float(params["drawing.isofit_strip_fall_deg"])  # type: ignore[arg-type]
            return {"status": "built", "reader": "isofit", "shape": "isofit",
                    "pieces": drawing_isofit.build(fitted, roll / CM_TO_MM, fall), "info": info,
                    "reasons": []}  # fmt: skip
        if b is not None:
            if iso is not None and b["iou"] >= min_iou:
                return {"status": "built", "reader": "views", "shape": "views",
                        "pieces": drawing_solid.pieces(b["solid"], roll), "info": info,
                        "reasons": []}  # fmt: skip
            if iso is not None:
                reasons.append(f"the best shape from the views fits the 3D view only "
                               f"{b['iou']:.0%} (needs {min_iou:.0%})")  # fmt: skip
    return {"status": NEEDS_PERSON, "reader": None, "shape": None, "pieces": None, "info": info,
            "reasons": reasons or ["nothing on the drawing could be read"]}  # fmt: skip


def ai_read(pdf: Path, params: EffectiveParams, code: str) -> dict[str, Any]:
    """The AI reads the drawing (advice, ADR-083): Gemini Flash into the swept shape, every
    written size checked against the shape's lengths. When the AI says the shape does not fit,
    or the shape cannot be built, nothing is built."""
    from coverengine import drawing_ai, swept
    from coverengine.params import Registry

    vision = Registry.load(None).resolve(trial={
        "ai.provider": str(params["ai.vision_provider"]),
        "ai.model": str(params["ai.vision_model"]),
        "ai.base_url": str(params["ai.vision_base_url"]), "ai.timeout_s": 600})  # fmt: skip
    res = drawing_ai.read(code, pdf, vision, int(params["drawing.ai_rounds"]))  # type: ignore[arg-type]
    shape = res.get("shape") or {}
    info = {"ai": {"matched": res.get("matched"), "written": res.get("written"),
                   "missing": res.get("missing"), "notes": shape.get("notes"),
                   "why_not": shape.get("why_not"), "error": res.get("error")}}  # fmt: skip
    reasons = []
    if shape.get("why_not"):
        reasons.append(f"the AI says the shape does not fit: {shape['why_not']}")
    if res.get("error"):
        reasons.append(f"the AI's shape could not be built: {res['error']}")
    if reasons:
        return {"status": NEEDS_PERSON, "reader": "ai", "shape": None, "pieces": None,
                "info": info, "reasons": reasons}  # fmt: skip
    pieces = swept.build(shape, roll_mm(params), float(shape.get("max_piece_mm") or math.inf))
    return {"status": "built", "reader": "ai", "shape": "swept", "pieces": pieces, "info": info,
            "reasons": []}  # fmt: skip


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
    ai: bool = False,
) -> dict[str, Any]:
    """Read the drawing and, when sure, build and calculate its cover in `model_dir` (a new
    model, or a new revision of an existing drawing cover). Never deletes the model's
    reference/, desk.json or revisions/."""
    from coverengine import drawing_given
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
    fixes = model_dir / "drawing_corrections.json"
    corrections = json.loads(fixes.read_text()).get("sizes") if fixes.is_file() else None
    given = None if ai else drawing_given.load(model_dir)
    res: dict[str, Any]
    if given is not None:  # a person read the shape from the drawing (drawing_shape.json)
        join = (float(params["drawn.merge_fold_deg"]), float(params["drawn.merge_max_stretch_pct"]))  # type: ignore[arg-type]
        res = {"status": "built", "reader": "given", "shape": "given",
               "pieces": drawing_given.build(given, roll_mm(params),
                                             float(params["seams.max_skirt_panel_mm"]), join),  # type: ignore[arg-type]
               "info": {"given": {k: given.get(k) for k in ("shape", "mirror", "read")}},
               "reasons": []}  # fmt: skip
    else:
        res = ai_read(ref, params, code) if ai else read(ref, params, corrections)
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
    how = (res["info"].get("isofit", {}).get("how") if res["reader"] == "isofit" else None) or (
        res["info"].get("solid", {}).get("how") or ["the drawn outline straight up"]
    )
    tags = set(cover_doc.get("tags") or []) | {"drawing", "reference"}
    if ai:  # advice: a person approves it at the Desk (ADR-083)
        tags.add("ai-read")
        note = (
            f"Drawing {code}: read by the AI as advice (ADR-083), "
            f"{res['info']['ai'].get('matched')} written sizes found; approve at the Desk."
        )
    elif given is not None:
        tags.discard("ai-read")
        note = (f"Drawing {code}: shape read by a person from the drawing's sizes "
                f"({given.get('shape')}{', mirrored' if given.get('mirror') else ''}): "
                f"{given.get('read') or ''}")  # fmt: skip
    else:
        tags.discard("ai-read")
        note = (f"Drawing {code}: read by the program itself (ADR-081): {res['reader']}, "
                f"{', '.join(how)}.")  # fmt: skip
    set_info(model_dir, {"tags": sorted(tags), "notes": note})
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
    if ai:  # the Desk puts it at the top: a person decides
        missing = res["info"]["ai"].get("missing") or []
        verdict = {"summary": "Read by the AI (advice): check the shape against the drawing "
                              "before approving.",
                   "differences": [f"written size not found: {m} cm" for m in missing]}  # fmt: skip
        _write(stale, {"code": code, "outcome": "person to check", "source": "drawing route",
                       "gemini": verdict})  # fmt: skip
    log(f"{code}: built ({res['reader']}), {doc['pieces']} pieces, {doc['vents']} vents")
    return doc
