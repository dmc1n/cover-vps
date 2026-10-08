"""`cover audit`: a fixed check of a calculated cover, and a second opinion from the AI (ADR-042).

The program measures, for each model:

- complete: every step's files are there and newer than the cover surface (a step that failed
  leaves older files behind, which must not count);
- furniture inside: points spread over the furniture above the hem all lie inside the cover;
- balloons: a table has at least one balloon under its cover;
- symmetric: a mirror-symmetric piece of furniture has a mirror-symmetric cover;
- water: the cover sheds water;
- pieces: the grade (stretch, seams, roll width) and no scrap pieces;
- drape: once the cover was dropped over the furniture, not too many folds, no deep sag;
- slivers: no piece narrower than seams.min_piece_width_mm (ADR-055); a top that would fit
  the roll in one piece with folds is noted.
- gentle folds: a box cover has no seam between two pieces on the same side that meet at a fold
  of at most seams.fold_join_max_deg and would fit the roll together (Rens, 8 Oct 2026; ADR-099).
- plan: an arrangement built to follow its pieces lies, seen from above, within the pieces plus
  the clearance: no diagonal across an open corner (ADR-095).

Then, with `--ai`, the AI gets three straight views (front, side, top: the furniture in grey,
the cover in see-through blue, furniture outside the cover in red), the product photo and the
measured facts, and gives its own verdict. Both go into `audit.json`; the views into
`audit.png`.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from coverengine.catalogue import grade, info
from coverengine.io.model_io import load_model
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
AUDIT_JSON, AUDIT_PNG = "audit.json", "audit.png"
SAMPLES = 20000  # param-ok: points spread over the furniture
OUTSIDE_MM = 3.0  # param-ok: a furniture point further than this outside the cover is outside
MIRROR_MM = 30.0  # param-ok: a symmetric cover mirrored lies within this of itself (95 %); the
# furniture itself counts as symmetric within 25 mm (hull/box.py SYMMETRY_MM)
MIRROR_PCT = 95  # param-ok: share of points
SCRAP_M2 = 0.02  # param-ok: a piece smaller than this is scrap
STEP_FILES = ("panels.json", "pattern.json", "finished.json", "cut.dxf")
VIEW_IN = (9.0, 3.2)  # param-ok: picture size (inches)
VIEW_DPI = 110  # param-ok: picture resolution
MM_PER_CM = 10.0  # param-ok: unit conversion
TITLE_PT = 8  # param-ok: display
PERCENT = 100.0  # param-ok: ratio to percent
GREY, BLUE, RED = "#7d828c", "#1f5fbf", "#e0302a"  # param-ok: display colours
PALE = "#cfe0f7"  # param-ok: display colour (the cover's area)
PAD_SHARE = 0.03  # param-ok: display margin
ON_TOP = 10  # param-ok: drawing order (red dots over everything)
SHORT_SIDE = 1.05  # param-ok: a seam this close to a piece's width runs along its short side


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "ok": bool(ok), "detail": detail}


def _furniture_above(model_dir: Path, hem: float) -> trimesh.Trimesh:
    m = load_model(model_dir)
    return trimesh.intersections.slice_mesh_plane(
        m, plane_normal=[0.0, 0.0, 1.0], plane_origin=[0.0, 0.0, hem], cap=False
    )


def outside(furniture: trimesh.Trimesh, cover: trimesh.Trimesh) -> tuple[Array, Array]:
    """Points on the furniture and how far each lies outside the cover (mm; <= 0 inside)."""
    import igl

    pts, _ = trimesh.sample.sample_surface(furniture, SAMPLES, seed=0)
    pts = np.vstack([pts, furniture.vertices])
    d2, face, near = igl.point_mesh_squared_distance(
        np.asarray(pts, np.float64),
        np.asarray(cover.vertices, np.float64),
        np.asarray(cover.faces, np.int32),
    )
    side = np.einsum("ij,ij->i", pts - near, cover.face_normals[face])
    return pts, np.where(side > 0, np.sqrt(d2), -np.sqrt(d2))


def mirror_gap(cover: trimesh.Trimesh, axis: int, mid: float) -> float:
    """How far (95 %) the mirrored cover lies from the cover itself (mm)."""
    import igl

    v = np.asarray(cover.vertices, np.float64).copy()
    v[:, axis] = 2 * mid - v[:, axis]
    d2, _, _ = igl.point_mesh_squared_distance(
        v, np.asarray(cover.vertices, np.float64), np.asarray(cover.faces, np.int32)
    )
    return float(np.percentile(np.sqrt(d2), MIRROR_PCT))


def views(furniture: trimesh.Trimesh, cover: trimesh.Trimesh, bad: Array, out: Path) -> Path:
    """Three straight views: the cover as a light blue area with a dark blue outline, the
    furniture solid grey on top of it, furniture outside the cover in red. Grey beyond the blue
    outline is furniture sticking out."""
    import shapely
    from matplotlib.collections import PolyCollection
    from matplotlib.figure import Figure

    fig = Figure(figsize=VIEW_IN, dpi=VIEW_DPI)
    views_ = (
        ("looking along y (x across)", 0, 2),
        ("looking along x (y across)", 1, 2),
        ("from above", 0, 1),
    )
    for k, (title, a, b) in enumerate(views_):
        ax = fig.add_subplot(1, 3, k + 1)
        ctri = cover.vertices[cover.faces][:, :, [a, b]]
        ax.add_collection(PolyCollection(list(ctri), facecolors=PALE, edgecolors="none"))
        ftri = furniture.vertices[furniture.faces][:, :, [a, b]]
        ax.add_collection(PolyCollection(list(ftri), facecolors=GREY, edgecolors="none"))
        shapes = [shapely.Polygon(t) for t in ctri]
        area = shapely.union_all([g for g in shapes if g.is_valid and g.area > 0])
        for poly in getattr(area, "geoms", [area]):
            if hasattr(poly, "exterior"):
                x, y = poly.exterior.xy
                ax.plot(x, y, color=BLUE, linewidth=1.4)
        if len(bad):
            ax.scatter(bad[:, a], bad[:, b], s=3, c=RED, zorder=ON_TOP)
        allv = np.vstack([furniture.vertices, cover.vertices])
        pad = float(np.ptp(allv, axis=0).max()) * PAD_SHARE
        ax.set_xlim(allv[:, a].min() - pad, allv[:, a].max() + pad)
        ax.set_ylim(allv[:, b].min() - pad, allv[:, b].max() + pad)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=TITLE_PT)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out, dpi=VIEW_DPI, metadata={"Software": None})
    return out


def drape_checks(model_dir: Path, params: EffectiveParams) -> list[dict[str, Any]]:
    """When the cover has been dropped over the furniture (cover drape, ADR-056): not too many
    folds, and no deep sag on top where water would stand."""
    path = model_dir / "drape.json"
    if not path.is_file():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    folds, sag = float(d["fold_share_pct"]), float(d["max_sag_mm"]) / MM_PER_CM
    most = float(params["drape.max_fold_share_pct"])
    deepest = float(params["drape.max_sag_cm"])
    problems = []
    if folds > most:
        problems.append(f"folds on {folds:g} % of the cover (more than {most:g} %)")
    if sag > deepest:
        problems.append(f"the top sags {sag:.0f} cm where nothing holds it (water)")
    wet = d.get("wet") or {}  # the rain on the cover as it lies (ADR-057)
    if float(wet.get("pond_volume_l", 0.0)) > float(params["drape.max_pond_l"]):
        problems.append(f"{wet['pond_volume_l']} l of rain stays on it in {wet['ponds']} pond(s)")
    ai = (d.get("ai") or {}).get("verdict")
    detail = "; ".join(problems) or f"folds on {folds:g} %, sags at most {sag:.0f} cm"
    return [_check("drape", not problems, detail + (f"; AI: {ai}" if ai else ""))]


def sliver_checks(model_dir: Path, params: EffectiveParams) -> list[dict[str, Any]]:
    """No piece narrower than seams.min_piece_width_mm; and a top in several pieces that lie flat
    together within the roll is noted (one piece with folds, seams.fold_merge; ADR-055)."""
    path = model_dir / "pattern.json"
    if not path.is_file():
        return []
    panels = json.loads(path.read_text(encoding="utf-8"))["panels"]
    least = float(params["seams.min_piece_width_mm"])
    thin = [f"{p['name']} {p['flat_width_mm'] / MM_PER_CM:.1f} cm" for p in panels
            if p["flat_width_mm"] < least]  # fmt: skip
    hull = json.loads((model_dir / "hull.json").read_text(encoding="utf-8"))
    drawn = hull.get("top") == "given"  # the owner's drawing: its strips are as drawn
    out = [_check("slivers", drawn or not thin,
                  ("narrower than " + f"{least / MM_PER_CM:g} cm: " + ", ".join(thin)) if thin
                  else f"no piece narrower than {least / MM_PER_CM:g} cm")]  # fmt: skip
    tops = [p for p in panels if p["name"].startswith("top")]
    roll = float(params["roll.usable_width_mm"])
    together = sum(p["flat_width_mm"] for p in tops)
    if len(tops) > 1 and together <= roll and not drawn:
        out.append(_check("top pieces", True, f"the top is {len(tops)} pieces, together "
                          f"{together / MM_PER_CM:.0f} cm wide: one piece with folds would fit "
                          "the roll (seams.fold_merge, on request)"))  # fmt: skip
    return out


def fold_checks(model_dir: Path, params: EffectiveParams) -> list[dict[str, Any]]:
    """A box cover: no seam between two pieces on the same side (top or skirt) whose faces meet
    at a fold of at most seams.fold_join_max_deg, when the two would fit the roll together:
    those lie flat as one piece with a fold line (Rens, 8 Oct 2026, ADR-099)."""
    limit = float(params["seams.fold_join_max_deg"])
    cut_path, npz = model_dir / "panels.json", model_dir / "panels.npz"
    if limit <= 0 or not cut_path.is_file() or not npz.is_file():
        return []
    hull = json.loads((model_dir / "hull.json").read_text(encoding="utf-8"))
    if hull.get("top") != "box":
        return []
    panels = json.loads(cut_path.read_text(encoding="utf-8"))["panels"]
    data = np.load(npz)
    faces = np.asarray(data["original_vertex"])[np.asarray(data["faces"])]
    labels = np.asarray(data["labels"])
    pts = np.zeros((int(faces.max()) + 1, 3))
    pts[np.asarray(data["original_vertex"])] = np.asarray(data["vertices"])
    mesh = trimesh.Trimesh(pts, faces, process=False)
    pairs = np.asarray(mesh.face_adjacency)
    la, lb = labels[pairs[:, 0]], labels[pairs[:, 1]]
    across = la != lb
    n = mesh.face_normals
    angle = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", n[pairs[:, 0]], n[pairs[:, 1]]),
                                         -1.0, 1.0)))  # fmt: skip
    roll = float(params["roll.usable_width_mm"])
    flagged = []
    for a, b in {(min(x, y), max(x, y)) for x, y in zip(la[across], lb[across], strict=True)}:
        pa, pb = panels[int(a)], panels[int(b)]
        if pa["region"] != pb["region"]:
            continue
        sel = across & (((la == a) & (lb == b)) | ((la == b) & (lb == a)))
        fold = float(np.median(angle[sel]))
        ends = np.asarray(mesh.face_adjacency_edges)[sel]
        seam = float(np.linalg.norm(pts[ends[:, 0]] - pts[ends[:, 1]], axis=1).sum())
        wa, wb = float(pa["flat_width_mm"]), float(pb["flat_width_mm"])
        # joined along their short sides the width stays; along their long sides they add up
        joined = max(wa, wb) if seam <= max(wa, wb) * SHORT_SIDE else wa + wb
        if fold <= limit and joined <= roll:
            flagged.append(f"{pa['name']} / {pb['name']} ({fold:.0f} degrees)")
    detail = ("seams where the pieces lie flat together (one piece with a fold): "
              + ", ".join(flagged)) if flagged else (
              f"no seam at a fold of {limit:g} degrees or less")  # fmt: skip
    return [_check("gentle folds", not flagged, detail)]


def plan_checks(model_dir: Path, params: EffectiveParams) -> list[dict[str, Any]]:
    """An arrangement whose cover should follow its members (ADR-095): seen from above, the
    cover lies within the members' rectangles plus the clearance, so no wall runs diagonally
    across an open corner (owner, 7 Oct 2026, the Portofino corner)."""
    from coverengine import arrange

    if not (model_dir / arrange.ARRANGEMENT_JSON).is_file():
        return []
    import shapely

    doc = arrange.read(model_dir)
    chosen = arrange.footprint_of(doc, params)
    cover = load_model(model_dir / "hull.glb")
    tri = np.asarray(cover.vertices)[np.asarray(cover.faces)][:, :, :2]
    plan = shapely.union_all([shapely.Polygon(t) for t in tri if shapely.Polygon(t).area > 1])
    c = float(params["hull.clearance_mm"])  # type: ignore[arg-type]
    rects = [shapely.Polygon(r) for r in arrange.plan_rects(doc)]
    own = shapely.union_all(rects).buffer(c + float(params["arrange.align_mm"]), join_style="mitre")  # type: ignore[arg-type]
    empty = float(plan.difference(own).area) / 1e6
    if chosen != "follow":
        return [_check("plan", True, f"the plan chosen is {chosen}: {empty:.2f} m2 over empty "
                                     "floor, as chosen")]  # fmt: skip
    return [_check("plan", empty < SCRAP_M2,
                   "the cover follows the pieces seen from above" if empty < SCRAP_M2 else
                   f"{empty:.2f} m2 of the cover lies over empty floor (a diagonal across an "
                   "open corner?)")]  # fmt: skip


def measure(model_dir: Path, params: EffectiveParams) -> dict[str, Any]:
    """The program's checks for one model."""
    from coverengine.hull.box import Box

    checks = []
    hull_glb, hull_json = model_dir / "hull.glb", model_dir / "hull.json"
    if not hull_glb.is_file():
        return {"checks": [_check("complete", False, "no cover surface calculated")]}
    hull = json.loads(hull_json.read_text(encoding="utf-8"))
    t0 = hull_json.stat().st_mtime
    stale = [f for f in STEP_FILES if not (model_dir / f).is_file()]
    stale += [
        f for f in STEP_FILES if (model_dir / f).is_file() and (model_dir / f).stat().st_mtime < t0
    ]
    checks.append(
        _check(
            "complete",
            not stale,
            "all steps done after the cover surface"
            if not stale
            else f"missing or older than the cover surface: {', '.join(sorted(set(stale)))}",
        )
    )
    hem = float(params["hull.hem_height_mm"])  # type: ignore[arg-type]
    furniture = _furniture_above(model_dir, hem)
    cover = load_model(hull_glb)
    pts, dist = outside(furniture, cover)
    bad = pts[dist > OUTSIDE_MM]
    worst = float(dist.max())
    where = pts[int(np.argmax(dist))]
    checks.append(
        _check(
            "furniture inside",
            not len(bad),
            "all of the furniture above the hem is inside the cover"
            if not len(bad)
            else f"{len(bad) / len(pts) * PERCENT:.1f} % of the furniture is outside the cover, up "
            f"to {worst / MM_PER_CM:.1f} cm, near x {where[0] / MM_PER_CM:.0f}, "
            f"y {where[1] / MM_PER_CM:.0f}, z {where[2] / MM_PER_CM:.0f} cm",
        )
    )
    if info(model_dir)["family"] == "table":
        sup = hull.get("support") or {}
        n = int(sup.get("balloons", 0)) if sup.get("kind") == "balloons" else 0
        checks.append(
            _check(
                "balloons",
                n >= 1,
                f"{n} balloon(s) under the cover ({sup.get('chosen_by', '')})"
                if n
                else "a table without balloons under its cover",
            )
        )
    seated = hull.get("chairs") or {}
    if seated:
        # across the long sides, where the chairs are (the axis the chair blocks are thin in)
        if seated.get("blocks"):
            lo, hi = np.asarray(seated["blocks"][0])
            axis = int(np.argmin(np.abs(hi[:2] - lo[:2] - float(seated["room_mm"]))))
            across = float(np.ptp(cover.vertices[:, axis]))
        else:  # all round a round table
            across = float(np.ptp(cover.vertices[:, :2], axis=0).min())
        need = float(seated["cover_width_mm"])
        checks.append(
            _check(
                "chair space",
                across >= need,
                f"{seated['kind'].replace('_', ' ')} table: the cover is "
                f"{across / MM_PER_CM:.0f} cm wide across, at least {need / MM_PER_CM:.0f} cm "
                f"(table + 2 x {seated['room_mm'] / MM_PER_CM:g} cm for the chairs), "
                f"{seated['height_mm'] / MM_PER_CM:g} cm high at the chairs",
            )
        )
    axes = Box._symmetry(np.asarray(furniture.vertices, np.float64))
    for axis, mid in axes:
        gap = mirror_gap(cover, axis, mid)
        side = "left-right" if axis == 0 else "front-back"
        checks.append(
            _check(
                f"symmetric {side}",
                gap < MIRROR_MM,
                f"the furniture is {side} symmetric; the cover mirrored lies within "
                f"{gap / MM_PER_CM:.1f} cm of itself",
            )
        )
    drains = bool((hull.get("drainage") or {}).get("drains", False))
    if hull.get("top") == "given" and not drains:
        # the owner's own cover, replicated exactly (owner, 1 Oct 2026): noted, not a fault
        flat = (hull.get("drainage") or {}).get("flat_area_mm2", 0.0) / 1e6
        checks.append(
            _check("water", True, f"{flat:.2f} m2 flat on top, as in the drawing (replicated)")
        )
    else:
        checks.append(_check("water", drains, "runs off" if drains else "water would stay on top"))
    g = grade(model_dir)
    pieces: list[dict[str, Any]] = []
    if (model_dir / "panels.json").is_file():
        pieces = json.loads((model_dir / "panels.json").read_text(encoding="utf-8"))["panels"]
    scrap = [p["name"] for p in pieces if p["area_m2"] < SCRAP_M2]
    checks.append(
        _check(
            "pieces",
            g["grade"] == "ready" and not scrap,
            f"{len(pieces)} pieces, {g['grade']}"
            + (f"; scrap pieces: {', '.join(scrap)}" if scrap else "")
            + (f"; {'; '.join(g.get('reasons', []))}" if g.get("reasons") else ""),
        )
    )
    checks += sliver_checks(model_dir, params)
    checks += fold_checks(model_dir, params)
    checks += plan_checks(model_dir, params)
    checks += drape_checks(model_dir, params)
    views(furniture, cover, bad, model_dir / AUDIT_PNG)
    return {
        "checks": checks,
        "pieces": len(pieces),
        "cover": hull.get("top"),
        "size_cm": [round(v / MM_PER_CM) for v in np.ptp(cover.vertices, axis=0)],
        "furniture_size_cm": [round(v / MM_PER_CM) for v in np.ptp(furniture.vertices, axis=0)],
    }


AI_SYSTEM = """You check outdoor furniture covers for a workshop, as a second opinion next to the
program's own measurements. Image 1 shows three straight views (looking along y, looking along
x, and from above): the cover is the light blue area with a dark blue outline, the furniture is
solid grey on top of it. Grey outside the dark blue outline, or red dots, is furniture outside
the cover. Image 2 is the product photo. Facts about these covers, not faults: the cover ends
5 cm above the floor (the hem; legs below it are fine); a box cover with flat faces over
rounded furniture is intended; a top sloping 5 degrees or more sheds water even if it looks
almost flat; tables have balloons and dining tables chair space beside the long sides, so their
cover is wider and higher than the table. A good cover covers all of the furniture above the
hem, sheds water, is symmetric when the furniture is, and has few pieces. You also get the
program's measured checks (measured on 20 000 points; trust them for what was measured, and
use the pictures for what they cannot see). Answer with JSON only:
{"verdict": "good | doubt | wrong", "problems": ["short plain sentences"],
 "disagree_with_program": ["checks where your view differs, with why"]}"""


def _image(path: Path) -> dict[str, Any]:
    mime = "image/png" if path.suffix == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def second_opinion(model_dir: Path, params: EffectiveParams, facts: dict[str, Any]) -> Any:
    from coverengine.ai import ask_parts, lessons_text

    parts: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(facts)}]
    parts.append(_image(model_dir / AUDIT_PNG))
    if (model_dir / "product.jpg").is_file():
        parts.append(_image(model_dir / "product.jpg"))
    return ask_parts(params, AI_SYSTEM + lessons_text("all"), parts)


def audit(model_dir: Path, params: EffectiveParams, use_ai: bool) -> dict[str, Any]:
    if "set" in (info(model_dir).get("tags") or []):  # a whole set in one file: no cover
        doc: dict[str, Any] = {"model_id": model_dir.name, "time": round(time.time()), "ok": True,
               "set": True,
               "checks": [_check("set", True, "a complete set in one file: covers per piece, "
                                 "not over the whole set")]}  # fmt: skip
        (model_dir / AUDIT_JSON).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return doc
    doc = measure(model_dir, params)
    doc["model_id"] = model_dir.name
    doc["time"] = round(time.time())
    doc["ok"] = all(c["ok"] for c in doc["checks"])
    if use_ai and (model_dir / AUDIT_PNG).is_file():
        cover = info(model_dir)
        facts = {
            "product": (cover.get("notes") or model_dir.name).split(": ", 1)[-1],
            "family": cover.get("family"),
            **{k: doc.get(k) for k in ("cover", "pieces", "size_cm", "furniture_size_cm")},
            "checks": doc["checks"],
        }
        try:
            answer = second_opinion(model_dir, params, facts)
            doc["ai"] = {
                "model": str(params["ai.model"]),
                "verdict": str(answer.get("verdict", "")),
                "problems": [str(p) for p in answer.get("problems", [])],
                "disagree": [str(p) for p in answer.get("disagree_with_program", [])],
            }
        except Exception as exc:  # noqa: BLE001 - the AI is a second opinion, not required
            doc["ai"] = {"model": str(params["ai.model"]), "error": str(exc)}
    (model_dir / AUDIT_JSON).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc
