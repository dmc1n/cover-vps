"""A cover from the drawing's exact top view and a profile from the back edge (ADR-084).

For curved sofas (C27: a C-shaped sectional whose arms curl in and end in round noses) a swept
cross-section along a path cannot follow the drawing: the top view is no offset of one curve.
Here the plan is the drawing's own outline, exactly, and the top's height at every point is the
profile at that point's distance from the back edge: e.g. a back strip 20.3 cm wide at 86.4 cm,
then down to 38.1 cm at 99 cm from the back. The walls stand on the outline up to the top.

Pieces:
- the top split along the profile's creases (the strip and the slope meet at a fold);
- across, along the drawing's seam lines (at given distances along the back edge, square to it);
- the walls: the back wall and the front wall, cut at the same seam lines.

Sizes in cm (as on the drawings), the surface in mm; z up.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from coverengine.drawn import MM, Piece
from coverengine.errors import CoverError

STEP_CM = 6.0  # param-ok: the top mesh, at most this coarse
CUT_REACH_CM = 400.0  # param-ok: a seam line reaches this far across the cover


def _height(profile: np.ndarray, d: np.ndarray) -> np.ndarray:
    return np.interp(d, profile[:, 0], profile[:, 1])


def _tri_region(region: Any, step: float) -> tuple[np.ndarray, np.ndarray]:
    """A plane region as fine triangles (xy, cm): constrained on its densified outline, then
    split until no edge is longer than `step`."""
    import shapely
    import trimesh

    dense = shapely.segmentize(region, step)
    tris = shapely.constrained_delaunay_triangles(dense)
    pts: dict[tuple[float, float], int] = {}
    faces = []
    for t in tris.geoms:
        idx = []
        for x, y in list(t.exterior.coords)[:3]:
            key = (round(x, 6), round(y, 6))
            if key not in pts:
                pts[key] = len(pts)
            idx.append(pts[key])
        faces.append(idx)
    v = np.array(list(pts.keys()))
    v3 = np.column_stack([v, np.zeros(len(v))])
    v3, f = trimesh.remesh.subdivide_to_size(v3, np.array(faces), max_edge=step)
    return v3[:, :2], np.asarray(f)


def _cuts(back: Any, at_cm: list[float]) -> list[Any]:
    """Seam lines square to the back edge at the given distances along it."""
    import shapely

    out = []
    for s in at_cm:
        p = np.array(back.interpolate(s).coords[0])
        q = np.array(back.interpolate(min(s + 1.0, back.length)).coords[0])
        r = np.array(back.interpolate(max(s - 1.0, 0.0)).coords[0])
        t = q - r
        t /= max(np.linalg.norm(t), 1e-9)
        n = np.array([-t[1], t[0]])
        out.append(shapely.LineString([p - n * CUT_REACH_CM, p + n * CUT_REACH_CM]))
    return out


def _split(region: Any, lines: list[Any]) -> list[Any]:
    from shapely.ops import split

    parts = [region]
    for ln in lines:
        nxt = []
        for g in parts:
            res = split(g, ln)
            nxt += [x for x in res.geoms if x.area > 1.0]  # param-ok: cm², no slivers
        parts = nxt
    return parts


def build(p: dict[str, Any], roll_mm: float = math.inf) -> list[Piece]:
    import shapely

    plan = shapely.Polygon(np.asarray(p["plan_cm"], dtype=float)).buffer(0)
    if plan.is_empty or plan.geom_type != "Polygon":
        raise CoverError("the plan must be one closed outline")
    back = shapely.LineString(np.asarray(p["back_cm"], dtype=float))
    profile = np.asarray(p["profile"], dtype=float)
    profile = profile[np.argsort(profile[:, 0])]
    creases = [float(d) for d in profile[1:-1, 0]]
    cut_lines = _cuts(back, [float(s) for s in p.get("seams_at_cm") or []])

    # the top: bands between the creases (distance from the back edge), cut across
    bands = []
    edges = [0.0, *creases, math.inf]
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        outer = back.buffer(b, quad_segs=32) if math.isfinite(b) else plan
        inner = back.buffer(a, quad_segs=32) if a > 0 else None
        band = plan.intersection(outer)
        if inner is not None:
            band = band.difference(inner)
        band = band.buffer(0)
        for g in getattr(band, "geoms", [band]):
            if g.geom_type == "Polygon" and g.area > 1.0:  # param-ok: cm²
                bands.append((a, g))
    pieces: list[Piece] = []
    k = 0
    for a, band in bands:
        for part in _split(band, cut_lines):
            v, f = _tri_region(part, STEP_CM)
            d = np.array([back.distance(shapely.Point(x, y)) for x, y in v])
            z = _height(profile, d)
            k += 1
            kind = "top" if a == 0 else "slope"
            faces = [[(float(v[i, 0] * MM), float(v[i, 1] * MM), float(z[i] * MM)) for i in tri]
                     for tri in f]  # fmt: skip
            pieces.append(Piece(f"{kind}-{k}", faces))

    # the walls on the outline: the back wall where the outline runs along the back edge
    ring = np.asarray(shapely.segmentize(plan.exterior, STEP_CM).coords)
    near = np.array([back.distance(shapely.Point(x, y)) for x, y in ring]) < 1.0  # param-ok: cm
    cut_pts = [ln.intersection(plan.exterior) for ln in cut_lines]
    walls: dict[str, list[list[tuple[float, float, float]]]] = {}
    for i in range(len(ring) - 1):
        (x0, y0), (x1, y1) = ring[i], ring[i + 1]
        z0 = float(_height(profile, np.array([back.distance(shapely.Point(x0, y0))]))[0])
        z1 = float(_height(profile, np.array([back.distance(shapely.Point(x1, y1))]))[0])
        side = "back" if near[i] and near[i + 1] else "front"
        mid = shapely.Point((x0 + x1) / 2, (y0 + y1) / 2)
        # which stretch between seam lines this wall bit is in
        s = back.project(mid)
        stretch = sum(1 for c in (p.get("seams_at_cm") or []) if s > float(c))
        name = f"{side}-{stretch + 1}"
        walls.setdefault(name, []).append([
            (x0 * MM, y0 * MM, 0.0), (x1 * MM, y1 * MM, 0.0),
            (x1 * MM, y1 * MM, z1 * MM), (x0 * MM, y0 * MM, z0 * MM)])  # fmt: skip
    del cut_pts
    pieces += [Piece(n, f) for n, f in sorted(walls.items())]
    return pieces


# --- reading such a cover from its drawing, by the program (ADR-084) -------------------------

HULL_NEAR_CM = 2.0  # param-ok: a point of the outline this close to its convex hull is "outside"
LINE_NEAR_PT = 3.5  # param-ok: a seam line starts and ends this close to the drawn outline
STRIP_SHARE = 0.4  # param-ok: the back strip is narrower than this share of the depth
STRIP_MIN_CM = 5.0  # param-ok: and wider than this
HALF = 0.5  # param-ok: the middle of a line
LABEL_REACH_PT = 120.0  # param-ok: a "Length" word sits beside its value
CONCAVE = 0.85  # param-ok: a plan filling less of its convex hull is curved like a C or U
SEAM_END_CM = 4.0  # param-ok: a seam line ends this close to the back and the front edge
SEAM_SHARE = 0.7  # param-ok: a seam line runs across most of the depth
SEAM_INSIDE_CM = 10.0  # param-ok: its middle lies well inside the cover, not along its edge
SEAM_SAME_CM = 5.0  # param-ok: lines this close along the back edge are one seam
JOIN_PT = 1.5  # param-ok: two drawn bits of one seam line meet within this (at the crease)
STRAIGHT_COS = 0.5  # param-ok: a seam line bends less than 60° at the crease
FULL_WIDTH = 0.1  # param-ok: seam lines within 10 % of the longest span the whole depth
SCALE_FIX_MAX = 0.25  # param-ok: a larger correction means the drawing was misread


def back_edge(plan: Any) -> Any:
    """The back edge: the longest run of the outline along its convex hull (the outside of a C
    or U shaped sofa), as a line."""
    import shapely

    pts = np.asarray(plan.exterior.coords)[:-1]
    hull = plan.convex_hull.exterior
    on = np.array([hull.distance(shapely.Point(p)) < HULL_NEAR_CM for p in pts])
    n = len(pts)
    best = (0, 0)
    for start in range(n):
        if on[start] and not on[start - 1]:
            k = 0
            while on[(start + k) % n] and k < n:
                k += 1
            if k > best[1]:
                best = (start, k)
    if best[1] < 3:  # param-ok: a line needs points
        raise CoverError("no back edge found on the outline")
    return shapely.LineString(pts[[(best[0] + i) % n for i in range(best[1])]])


def _profile_from_text(pdf: Any) -> dict[str, float] | None:
    """Back height, front height, depth and the back strip from words on the drawing (C26,
    C27: "86.4cm Height", "38.1cm Front Height", "99.0cm Depth", a bare "20.3cm")."""
    import re

    import pymupdf

    from coverengine.drawing_views import written_cm

    got: dict[str, float] = {}
    for page in pymupdf.open(pdf).pages():
        for b in page.get_text("blocks"):
            t = b[4]
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*cm", t)
            if not m:
                continue
            v = float(m.group(1).replace(",", "."))
            low = t.lower()
            if "front" in low:
                got["front"] = v
            elif "depth" in low:
                got["depth"] = v
            elif "height" in low:
                got["back"] = max(v, got.get("back", 0.0))
    # "Front" and "Height" may be separate blocks: a height block next to a Front block
    if not {"back", "front", "depth"} <= set(got):
        return None
    small = [s for s in written_cm(pdf) if STRIP_MIN_CM < s < STRIP_SHARE * got["depth"]]
    got["strip"] = min(small) if small else 0.0
    return got


def _seam_lines(page: Any, plan_pt: Any) -> list[Any]:
    """The drawing's seam lines over the top view: drawn lines that leave the outline, run
    across the cover (in up to three joined bits: outer edge → crease → front edge) and reach
    the outline again."""
    import shapely

    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for d in page.get_drawings():
        if d.get("fill") is not None:
            continue
        for it in d["items"]:
            if it[0] == "l":
                segs.append(((it[1].x, -it[1].y), (it[2].x, -it[2].y)))
    ring = plan_pt.exterior
    near = lambda q: ring.distance(shapely.Point(q)) < LINE_NEAR_PT  # noqa: E731
    out = []
    for a, b in segs:
        for start, cur in ((a, b), (b, a)):
            if not near(start) or near(cur):
                continue  # begins at the outline and leaves it
            chain = [start, cur]
            for _ in range(2):  # param-ok: at most three bits in all
                # of the bits that go on from here, the one that runs on most straight (at the
                # crease the line between the strip and the slope also passes)
                here = np.subtract(chain[-1], chain[-2])
                best: tuple[float, Any] = (-2.0, None)
                for c, d2 in segs:
                    for p0, p1 in ((c, d2), (d2, c)):
                        if (
                            math.dist(p0, chain[-1]) < JOIN_PT
                            and math.dist(p1, chain[-2]) > JOIN_PT
                        ):
                            go = np.subtract(p1, p0)
                            cos = float(
                                here @ go / max(np.linalg.norm(here) * np.linalg.norm(go), 1e-9)
                            )
                            if cos > best[0]:
                                best = (cos, p1)
                nxt = best[1] if best[0] > STRAIGHT_COS else None
                if nxt is None:
                    break
                chain.append(nxt)
                if near(nxt):
                    break
            if len(chain) > 2 and near(chain[-1]):  # param-ok: joined bits only
                ln = shapely.LineString(chain)
                if plan_pt.buffer(LINE_NEAR_PT).contains(ln):
                    out.append(ln)
    return out


def read_drawing(pdf: Any) -> dict[str, Any]:
    """The shape of a C or U shaped cover from its drawing: the top view's exact outline, the
    back profile from the written heights and depth, the seams from the drawn seam lines.
    Returns {"shape": ...} or {"error": why}."""
    import pymupdf
    import shapely

    from coverengine import drawing_views as dv

    read = dv.read(pdf)
    ortho = [v for v in read["views"] if v.kind != "iso"]
    if not ortho:
        return {"error": "no top view"}
    plan_v = max(ortho, key=lambda v: v.size[0] * v.size[1])
    k = float(plan_v.meta["scale"])
    plan_pt = shapely.Polygon(plan_v.outline).buffer(0)
    plan = shapely.Polygon(plan_v.outline * k).buffer(0).simplify(0.3)
    if plan.area / plan.convex_hull.area > CONCAVE:
        return {"error": "the top view is not curved like a C or U"}
    prof = _profile_from_text(pdf)
    if prof is None:
        return {"error": "no written back height, front height and depth"}
    back = back_edge(plan)
    page = pymupdf.open(pdf)[plan_v.page]
    lines = _seam_lines(page, plan_pt)
    # the top view's own scale can be off (C26: 16 %): the seam lines run straight across the
    # cover, so the widest of them is the written depth
    widths = [ln.length * k for ln in lines]
    full = [w for w in widths if widths and w > (1 - FULL_WIDTH) * max(widths)]
    fix = float(prof["depth"] / np.median(full)) if full else 1.0
    if abs(fix - 1) > SCALE_FIX_MAX:
        return {"error": f"the top view's scale disagrees with the written depth by {fix - 1:+.0%}"}
    k *= fix
    plan = shapely.Polygon(plan_v.outline * k).buffer(0).simplify(0.3)
    back = back_edge(plan)
    seams: list[float] = []
    inner = plan.exterior.difference(back.buffer(HULL_NEAR_CM))
    for ln in lines:
        cm = shapely.affinity.scale(ln, k, k, origin=(0, 0))
        a, b = shapely.Point(cm.coords[0]), shapely.Point(cm.coords[-1])
        if back.distance(a) > back.distance(b):
            a, b = b, a
        mid = cm.interpolate(HALF, normalized=True)
        across = (back.distance(a) < SEAM_END_CM and inner.distance(b) < SEAM_END_CM
                  and cm.length > SEAM_SHARE * prof["depth"]
                  and plan.exterior.distance(mid) > SEAM_INSIDE_CM)  # fmt: skip
        if not across:
            continue
        at = float(back.project(a))
        if all(abs(at - s) > SEAM_SAME_CM for s in seams):
            seams.append(round(at, 2))
    profile = [[0.0, prof["back"]]]
    if prof["strip"] > 0:
        profile.append([prof["strip"], prof["back"]])
    profile.append([prof["depth"], prof["front"]])
    flip = lambda pts: [[float(x), -float(y)] for x, y in pts]  # noqa: E731 - page y is up
    return {
        "shape": {"plan_cm": flip(np.asarray(plan.exterior.coords)[:-1]),
                  "back_cm": flip(np.asarray(back.coords)), "profile": profile,
                  "seams_at_cm": sorted(seams)},
        "profile": prof, "seams": len(seams), "scale_from": read["scale_from"],
        "scale_fix": round(fix, 4),
    }  # fmt: skip


LENGTH_TOL = 0.02  # param-ok: a written length found within 2 % (or 2 cm)
TRUST_SHARE = 0.75  # param-ok: this share of the back edge's segments must match written lengths


def _written_lengths(pdf: Any) -> list[dict[str, float]]:
    """Every size labelled "Length": its cm and its inch value (they can disagree: C27 writes
    235.1 cm beside 96.5 in = 245.1 cm)."""
    import re

    import pymupdf

    out = []
    for page in pymupdf.open(pdf).pages():
        blocks = page.get_text("blocks")
        for b in blocks:
            t = b[4]
            cm = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:cm)?\s*\n\s*(\d+(?:[.,]\d+)?)\s*in", t)
            if not cm:
                continue
            near_word = any("length" in o[4].lower() and abs(o[1] - b[1]) < 40  # param-ok: pt
                            and abs(o[0] - b[0]) < LABEL_REACH_PT for o in blocks)  # fmt: skip
            if "length" in t.lower() or near_word:
                out.append({"cm": float(cm.group(1).replace(",", ".")),
                            "in_cm": float(cm.group(2).replace(",", ".")) * 2.54})  # fmt: skip
    return out


def check_lengths(pdf: Any, shape: dict[str, Any]) -> dict[str, Any]:
    """The back edge's segments between the drawn seams against the written lengths: how many
    match, and the written sizes whose cm and inch values disagree (the inch one was right)."""
    import shapely

    at = sorted(float(s) for s in shape.get("seams_at_cm") or [])
    segs = [b - a for a, b in zip(at[:-1], at[1:], strict=True)]
    written = _written_lengths(pdf)
    ok, typos = 0, []
    for seg in segs:
        hit = None
        for w in written:
            for key in ("cm", "in_cm"):
                if abs(w[key] - seg) <= max(2.0, LENGTH_TOL * seg):  # param-ok: cm
                    hit = (w, key)
                    break
            if hit:
                break
        if hit:
            ok += 1
            w, key = hit
            if key == "in_cm" and abs(w["cm"] - w["in_cm"]) > max(2.0, LENGTH_TOL * w["in_cm"]):
                typos.append({"written_cm": w["cm"], "inch_gives_cm": round(w["in_cm"], 1),
                              "measured_cm": round(seg, 1)})  # fmt: skip
    del shapely
    return {"segments": [round(s, 1) for s in segs], "matched": ok, "of": len(segs),
            "trusted": bool(segs) and ok / len(segs) >= TRUST_SHARE, "typos": typos}  # fmt: skip
