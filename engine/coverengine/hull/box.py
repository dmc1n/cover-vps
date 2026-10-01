"""Box covers (`hull.top: box`, ADR-038): the cover is the tightest box with a chosen number of
flat faces round the furniture, so every face is one fabric piece that lies flat exactly and
every seam is a straight box edge.

How the box is made:
1. Start with the smallest rectangle round the furniture seen from above (four upright sides)
   and a top, all `hull.clearance_mm` clear of the furniture.
2. Add faces one at a time, each time the cut that removes the most empty room (for a sofa: the
   slope from the front edge to the top of the back), up to `hull.box_max_pieces`.
3. Choose how many pieces: `hull.box_pieces`, or (0) the AI's choice from the options with their
   room and extra volume, or, without AI, the fewest pieces whose extra volume is within
   `hull.box_volume_slack_pct` of the tightest box.
4. Water must run off (rule 12): a face flatter than `hull.min_slope_deg` is tilted; a flat face
   over the middle of the furniture (a table top) becomes a low gable of two faces.
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import shapely
import trimesh
from numpy.typing import NDArray
from scipy.spatial import ConvexHull, HalfspaceIntersection

from coverengine.params import EffectiveParams

Array = NDArray[np.float64]

PERCENT = 100.0  # param-ok: ratio to percent
# Mirror symmetry of the furniture's outside: checked in this many directions, within this
# distance (mm).
SYMMETRY_DIRECTIONS = 2000  # param-ok: sampling
SYMMETRY_MM = 25.0  # param-ok: geometric tolerance
# The box starts square to the furniture unless a turned rectangle is this share smaller.
STRAIGHT_SHARE = 0.01  # param-ok: geometric tolerance
# Candidate face directions closer than this are one candidate (degrees).
CANDIDATE_SPACING_DEG = 3.0
# Room between box and furniture is sampled at this many points per box triangle.
ROOM_SAMPLES = 40  # param-ok: geometric constant
# A face counts as upright (a side, part of the skirt) below this |normal z|.
UPRIGHT_NZ = 0.1  # param-ok: geometric constant
# A flat face whose centre is within this share of the box's half-size from the middle is a
# table top: it becomes a gable.
CENTRAL_SHARE = 0.35
# Box faces are split into triangles of at most this size (mm), for the rest of the chain.
EDGE_MM = 40.0  # param-ok: geometric constant


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


class Box:
    """The furniture's points and the box faces round them."""

    def __init__(self, points: Array, hem: float, clearance: float) -> None:
        self.hem, self.clearance = hem, clearance
        pts = np.vstack([points, np.column_stack([points[:, :2], np.full(len(points), hem)])])
        hull = ConvexHull(pts)
        self.points = pts[hull.vertices]
        self.volume = float(hull.volume)
        self.inside = np.append(self.points[:, :2].mean(axis=0), (hem + points[:, 2].max()) / 2)
        cands: list[Array] = []
        for e in hull.equations:
            n = e[:3]
            if n[2] < -UPRIGHT_NZ:
                continue
            spaced = all(
                math.degrees(math.acos(float(np.clip(n @ c, -1, 1)))) > CANDIDATE_SPACING_DEG
                for c in cands
            )
            if spaced:
                cands.append(n)
        self.candidates = cands
        self.mirrors = self._symmetry(np.asarray(points, np.float64))

    @staticmethod
    def _symmetry(points: Array) -> list[tuple[int, float]]:
        """The axes (0 = left-right, 1 = front-back) the furniture's outside is mirror-symmetric
        about: in every direction it reaches as far as in the mirrored direction, within
        SYMMETRY_MM (loose cushions placed a little differently do not count). A symmetric
        cover needs its faces in mirror pairs (lesson from the Vento daybed, ADR-041)."""
        rng = np.random.default_rng(0)
        d = rng.normal(size=(SYMMETRY_DIRECTIONS, 3))
        d[:, 2] = np.abs(d[:, 2])
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        hull = points[ConvexHull(points).vertices]
        out = []
        for k in (0, 1):
            mid = float(hull[:, k].min() + hull[:, k].max()) / 2
            c = hull.copy()
            c[:, k] -= mid
            m = d.copy()
            m[:, k] = -m[:, k]
            reach, mirrored = (c @ d.T).max(axis=0), (c @ m.T).max(axis=0)
            if float(np.abs(reach - mirrored).max()) < SYMMETRY_MM:
                out.append((k, mid))
        return out

    def mirror(self, n: Array) -> list[Array]:
        """n and its mirror images (for a symmetric cover). A face almost square to a mirror
        plane is made exactly square to it, so it is its own mirror image."""
        out = [n.copy()]
        for k, _ in self.mirrors:
            for m in list(out):
                flipped = m.copy()
                flipped[k] = -flipped[k]
                apart = math.degrees(math.acos(float(np.clip(flipped @ m, -1, 1))))
                if apart <= CANDIDATE_SPACING_DEG:
                    m[k] = 0.0
                    m /= np.linalg.norm(m)
                else:
                    out.append(flipped)
        return out

    def plane(self, n: Array) -> Array:
        n = n / np.linalg.norm(n)
        return np.append(n, -(float((self.points @ n).max()) + self.clearance))

    def start(self) -> list[Array]:
        cloud = shapely.MultiPoint(self.points[:, :2])
        turned = cloud.minimum_rotated_rectangle
        lo, hi = self.points[:, :2].min(axis=0), self.points[:, :2].max(axis=0)
        # a turned rectangle only when it is clearly smaller: for a round table any turn is as
        # small, and the box must stay square to the furniture
        if turned.area < (1 - STRAIGHT_SHARE) * float(np.prod(hi - lo)):
            rect = np.asarray(turned.exterior.coords)[:4]
        else:
            rect = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]])
        out = [np.array([0.0, 0.0, -1.0, self.hem]), self.plane(np.array([0.0, 0.0, 1.0]))]
        centre = rect.mean(axis=0)
        for i in range(4):
            e = rect[(i + 1) % 4] - rect[i]
            n = np.array([e[1], -e[0], 0.0])
            if n[:2] @ (rect[i] - centre) < 0:
                n = -n
            out.append(self.plane(n))
        return out

    def solid(self, planes: list[Array]) -> ConvexHull | None:
        try:
            pts = HalfspaceIntersection(np.array(planes), self.inside).intersections
            return ConvexHull(pts)
        except Exception:  # noqa: BLE001 - a plane set that does not close
            return None

    def grow(self, max_faces: int) -> list[list[Array]]:
        """Plane sets with 5, 6, ... max_faces box faces (the open bottom not counted)."""
        planes = self.start()
        sets = [list(planes)]
        while len(planes) - 1 < max_faces:
            best: list[Array] | None = None
            best_v = math.inf
            for c in self.candidates:
                group = self.mirror(c)  # a face and its mirror images go in together
                if len(planes) - 1 + len(group) > max_faces:
                    continue
                s = self.solid([*planes, *(self.plane(g) for g in group)])
                if s is not None and s.volume < best_v:
                    best, best_v = group, s.volume
            if best is None:
                break
            planes.extend(self.plane(g) for g in best)
            sets.append(list(planes))
        return sets


def drain(box: Box, planes: list[Array], min_slope_deg: float) -> list[Array]:
    """Tilt faces flatter than the minimum slope; a flat face in the middle becomes a gable."""
    solid = box.solid(planes)
    if solid is None:
        return planes
    lo, hi = solid.points[:, :2].min(axis=0), solid.points[:, :2].max(axis=0)
    centre, half = (lo + hi) / 2, (hi - lo) / 2
    tilt = math.radians(min_slope_deg)
    out: list[Array] = []
    for pl in planes:
        n = pl[:3]
        flat = n[2] > math.cos(tilt) - 1e-9
        if not flat:
            out.append(pl)
            continue
        # where is this face? (its points on the solid)
        on = np.abs(solid.points @ n + pl[3]) < 1.0
        mid = solid.points[on, :2].mean(axis=0) if on.any() else centre
        off = (mid - centre) / np.maximum(half, 1.0)
        # a symmetric cover may only tilt across its mirror lines (lesson: a table top tilted to
        # one side made the cover of a symmetric table lopsided)
        for k, _ in box.mirrors:
            off[k] = 0.0
        if np.abs(off).max() < CENTRAL_SHARE:  # a table top: a gable along the long side
            across = np.array([0.0, 1.0]) if half[0] >= half[1] else np.array([1.0, 0.0])
            for sign in (1.0, -1.0):
                d = sign * across
                out.append(box.plane(np.array([d[0] * math.sin(tilt), d[1] * math.sin(tilt),
                                               math.cos(tilt)])))  # fmt: skip
        else:  # tilt towards the outside, so water runs off that edge
            d = off / (np.linalg.norm(off) or 1.0)
            out.append(box.plane(np.array([d[0] * math.sin(tilt), d[1] * math.sin(tilt),
                                           math.cos(tilt)])))  # fmt: skip
    return out


def room(box: Box, solid: ConvexHull, model: trimesh.Trimesh) -> Array:
    """Distances from points spread over the box (not its bottom) to the furniture."""
    import igl

    rng = np.random.default_rng(0)
    samples = []
    for simplex, e in zip(solid.simplices, solid.equations, strict=True):
        if e[2] < -1 + 1e-6:
            continue
        a, b, c = solid.points[simplex]
        uv = rng.random((ROOM_SAMPLES, 2))
        flip = uv.sum(axis=1) > 1
        uv[flip] = 1 - uv[flip]
        samples.append(a + uv[:, :1] * (b - a) + uv[:, 1:] * (c - a))
    pts = np.vstack(samples)
    d2, _, _ = igl.point_mesh_squared_distance(
        pts, np.asarray(model.vertices, np.float64), np.asarray(model.faces, np.int32)
    )
    return np.sqrt(d2)


def options(box: Box, sets: list[list[Array]], model: trimesh.Trimesh) -> list[dict[str, Any]]:
    rows = []
    for planes in sets:
        solid = box.solid(planes)
        if solid is None:
            continue
        dist = room(box, solid, model)
        rows.append(
            {
                "pieces": len(planes) - 1,
                "room_median_mm": round(float(np.median(dist))),
                "room_95pct_mm": round(float(np.percentile(dist, 95))),
                "extra_volume_pct": round(PERCENT * (solid.volume / box.volume - 1), 1),
            }
        )
    return rows


AI_SYSTEM = """You advise a workshop that sews outdoor furniture covers. The cover is a box with
flat faces round the furniture: each face is one fabric piece, seams on the box edges, open at
the bottom. You get the furniture and the options: how many pieces, with the typical room between
cover and furniture, the room within which 95 % of the cover lies (large where the cover spans a
seat from the front edge to the top of the back, as intended) and how much bigger the box is than
the furniture. The owner wants as few pieces as possible with a good fit; more pieces only when
they clearly tighten the fit. A symmetric piece of furniture gets a symmetric cover, so the
options of a symmetric product grow by mirror pairs. Answer with JSON only:
{"pieces": <one of the options>, "reason": "one or two plain sentences"}"""


def choose(
    rows: list[dict[str, Any]], params: EffectiveParams, product: str
) -> tuple[int, str, str]:
    """The number of pieces, who chose it (setting / ai / rule), and why."""
    fixed = int(params["hull.box_pieces"])
    if fixed > 0:
        best = min(rows, key=lambda r: abs(r["pieces"] - fixed))
        return int(best["pieces"]), "setting", f"hull.box_pieces = {fixed}"
    slack = _p(params, "hull.box_volume_slack_pct")
    tightest = min(r["extra_volume_pct"] for r in rows)
    rule = next(r for r in rows if r["extra_volume_pct"] <= tightest + slack)
    if params["ai.provider"] != "none":
        try:
            from coverengine.ai import ask

            facts = {"furniture": product, "options": rows}
            from coverengine.ai import lessons_text

            answer = ask(params, AI_SYSTEM + lessons_text("box"), json.dumps(facts))
            n = int(answer["pieces"])
            if any(r["pieces"] == n for r in rows):
                return n, "ai", str(answer.get("reason", ""))
        except Exception as exc:  # noqa: BLE001 - no AI: the rule decides
            return (
                int(rule["pieces"]),
                "rule",
                f"the AI could not decide ({exc}); fewest pieces within the slack",
            )
    return int(rule["pieces"]), "rule", f"fewest pieces within {slack:g} % of the tightest box"


def mesh_of(box: Box, planes: list[Array]) -> trimesh.Trimesh:
    """The box surface without its bottom, in triangles of at most EDGE_MM."""
    solid = box.solid(planes)
    if solid is None:
        raise ValueError("the box does not close")
    pts = solid.points
    tris = []
    for simplex, e in zip(solid.simplices, solid.equations, strict=True):
        if e[2] < -1 + 1e-6:  # the bottom stays open
            continue
        a, b, c = simplex
        # keep the outward winding
        n = np.cross(pts[b] - pts[a], pts[c] - pts[a])
        tris.append([a, b, c] if n @ e[:3] > 0 else [a, c, b])
    mesh = trimesh.Trimesh(pts, np.array(tris), process=True)
    v, f = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=EDGE_MM)
    return trimesh.Trimesh(v, f, process=True)


def box_hull(
    points: Array, model: trimesh.Trimesh, params: EffectiveParams, product: str
) -> tuple[trimesh.Trimesh, dict[str, Any], list[str]]:
    hem = _p(params, "hull.hem_height_mm")
    box = Box(points, hem, _p(params, "hull.clearance_mm"))
    sets = box.grow(int(params["hull.box_max_pieces"]))
    rows = options(box, sets, model)
    pieces, by, why = choose(rows, params, product)
    planes = next(s for s in sets if len(s) - 1 == pieces)
    planes = drain(box, planes, _p(params, "hull.min_slope_deg"))
    mesh = mesh_of(box, planes)
    warnings = []
    outline = shapely.MultiPoint(points[:, :2]).convex_hull
    above = model.submesh([np.flatnonzero(model.triangles_center[:, 2] > hem)], append=True)
    spread, _ = trimesh.sample.sample_surface(above, FOOTPRINT_SAMPLES, seed=0)  # even cover
    cells = np.unique(np.floor(spread[:, :2] / PLAN_CELL_MM).astype(np.int64), axis=0)
    plan_area = len(cells) * PLAN_CELL_MM**2  # the furniture seen from above, roughly
    if plan_area > 0 and outline.area / plan_area > CONCAVE_LIMIT:
        warnings.append(
            "seen from above the furniture is far from a box (bays or an L shape): a box cover "
            "spans those; the tensioned cover (hull.top: tensioned) follows them"
        )
    report = {
        "pieces": len({tuple(np.round(n, 4)) for n in mesh.face_normals}),
        "chosen": pieces,
        "chosen_by": by,
        "reason": why,
        "options": rows,
    }
    return mesh, report, warnings


# A box cover spans bays seen from above; warn when the convex footprint is this much larger.
CONCAVE_LIMIT = 1.15
FOOTPRINT_SAMPLES = 40000  # param-ok: points spread over the furniture for the footprint
PLAN_CELL_MM = 20.0  # grid for the footprint check  # param-ok: geometric constant
