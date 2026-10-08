"""A box cover's plan from the furniture seen from above (ADR-107).

Rens at the Desk, 8 October 2026, on 18 round tables: "make the cover round in top view, not
square or octagonal"; on 12 organic lounges: "follow the (round) outline from the top view
better". The box cover of ADR-038 is an intersection of half-spaces: its plan is a convex
polygon of a few straight sides, so a round table got a square (or, with 9 pieces, an
octagon) and a moon-shaped sofa a hexagon over empty floor. Here the plan comes first, from
the furniture's own footprint, as ADR-095 does for arrangements:

1. The footprint: the furniture above the hem seen from above (a height map on a
   `hull.plan_cell_mm` grid), gaps narrower than `hull.bridge_gap_mm` spanned, holes filled;
   plus the chair space of a table (hull/chairs.py) and its balloons.
2. Round (`hull.plan: round`, or `auto` when the footprint fills at least `hull.round_fill`
   of its smallest enclosing circle): a circle round it plus the clearance. The cover is a
   cylinder skirt with a cone on top that rests on the support (balloons) and slopes at least
   `hull.min_slope_deg` everywhere, so water runs off (rule 12) and the skirt seam lies at one
   height (rule 13). The top is cut into equal sectors (seams running straight downhill from
   the apex) and the skirt into equal strips, as few as fit the roll (rule 5).
3. Follow (`hull.plan: follow`, or `auto` when a side or corner of the box's plan stands more
   than `hull.plan_follow_mm` beyond the footprint plan): the footprint offset by the
   clearance, its inner corners, bays and small jogs rounded to `hull.plan_round_mm` so every
   seam is a smooth line (rule 13); the walls stand straight down on that outline and the top is the
   box's own top faces (they span seats, so water runs off as before, rule 12). Every flat top
   face is a piece; the wall is cut into strips at its corners and where it gets longer than
   `seams.max_skirt_panel_mm`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import shapely
import trimesh
from numpy.typing import NDArray
from scipy import ndimage
from shapely.geometry import Polygon

from coverengine.errors import CoverError
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

PERCENT = 100.0  # param-ok: ratio to percent
# A face steeper than this |normal z| is a wall (as hull/box.py and hull/plan.py).
UPRIGHT_NZ = 0.1  # param-ok: geometric constant
# Triangles of the cover at most this long (mm), as hull/box.py.
EDGE_MM = 40.0  # param-ok: geometric constant
# The plan outline is simplified within this (mm): far inside the fit tolerance.
SIMPLIFY_MM = 0.5  # param-ok: geometric tolerance
# Splitting the solid's triangles: passes at most.
SAME_FACE = 0.9999  # param-ok: the cosine between faces of one flat piece
SHIFTS_MM = (0.0, 0.37, -0.53, 1.13)  # param-ok: small offsets for a cut that tore
REFINE_PASSES = 40  # param-ok: loop guard (each pass halves the longest edges)
# A cut that changes the area by more than this (mm2) tore the surface.
CUT_AREA_MM2 = 1.0  # param-ok: geometric tolerance
WELD_MM = 1e-3  # param-ok: points closer than a thousandth of a mm are one point
# A face smaller than this (mm2) has no direction of its own (a joint along a straight line).
AREA_MM2 = 1e-3  # param-ok: numerical tolerance
# Bumps of the grid narrower than twice this (mm) are smoothed off the outline.
STEP_MM = 30.0  # param-ok: a few grid cells
# Points of a round arc (shapely buffer quadrant segments).
QUAD_SEGS = 16  # param-ok: sampling
# The cone's slope is tried in steps of this (degrees) up to CONE_MAX_DEG.
CONE_STEP_DEG = 0.25  # param-ok: sampling
CONE_MAX_DEG = 45.0  # param-ok: search bound, steeper is never the smallest cover
# Every ring of the cone has at least this many points per sector (no flat fan triangles).
MIN_RING_POINTS = 3  # param-ok: meshing
# A round cover's top has at least two sectors: a cone in one piece would need a slit.
MIN_SECTORS = 2  # param-ok: geometry (a cone is not a disc)
MAX_SECTORS = 16  # param-ok: search bound
MIN_STRIPS = 2  # param-ok: a closed wall needs a seam; two keep a symmetric cover symmetric
# Flattened sectors are measured on this many arc points.
ARC_POINTS = 90  # param-ok: sampling


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def _largest(shape: shapely.Geometry) -> Polygon:
    polys = [p for p in getattr(shape, "geoms", [shape]) if isinstance(p, Polygon)]
    if not polys:
        raise CoverError("the furniture has no footprint above the hem")
    return Polygon(max(polys, key=lambda p: p.area).exterior)


def footprint(
    v: Array, f: IntArray, hem: float, cell: float, close_mm: float, extra: list[Array]
) -> Polygon:
    """The furniture above the hem seen from above (no holes), gaps up to close_mm spanned,
    with the convex outline of every extra point set (chair space, balloons) added."""
    from coverengine.hull.heightmap import rasterize

    reach = int(math.ceil(close_mm / 2 / cell))
    hm = rasterize(v, f, cell, close_mm + 4 * cell)
    inside = np.isfinite(hm.z) & (hm.z > hem)
    if not inside.any():
        raise CoverError("the furniture has no footprint above the hem")
    if reach > 0:
        d = np.arange(-reach, reach + 1)
        disk = d[:, None] ** 2 + d[None, :] ** 2 <= reach**2
        inside = ndimage.binary_closing(inside, structure=disk)
    inside = ndimage.binary_fill_holes(inside)
    from skimage.measure import find_contours

    padded = np.pad(inside.astype(np.float64), 1)
    polys = []
    for c in find_contours(padded, 0.5):  # param-ok: the level between in (1) and out (0)
        if len(c) < 4:  # param-ok: a polygon needs three corners
            continue
        xy = np.column_stack([hm.x0 + (c[:, 0] - 1) * cell, hm.y0 + (c[:, 1] - 1) * cell])
        p = Polygon(xy).buffer(0)
        if p.area > 0:
            polys.append(p)
    shape = shapely.union_all(polys)
    # each cell centre stands for its cell: the furniture may reach half a cell further
    shape = shape.buffer(cell / 2, quad_segs=QUAD_SEGS)
    if isinstance(shape, shapely.MultiPolygon):  # pieces apart: one cover round all of them
        shape = shape.convex_hull
    for pts in extra:
        if len(pts) >= 3:  # param-ok: a polygon needs three corners
            shape = shapely.union_all([shape, shapely.MultiPoint(pts[:, :2]).convex_hull])
    return _largest(shape)


def roundness(foot: Polygon) -> tuple[float, Array, float]:
    """How much of its smallest enclosing circle the footprint fills (a circle 1, a regular
    octagon 0.90, a square 0.64), the circle's centre and radius."""
    circle = shapely.minimum_bounding_circle(foot)
    radius = float(shapely.minimum_bounding_radius(foot))
    centre = np.asarray(circle.centroid.coords[0], np.float64)
    fill = float(foot.area) / (math.pi * radius**2) if radius > 0 else 0.0
    return fill, centre, radius


def follow_plan(
    foot: Polygon, clearance: float, round_mm: float, mirrors: list[tuple[int, float]]
) -> Polygon:
    """The cover's plan at the hem: the footprint plus the clearance, inner corners and bays
    narrower than twice round_mm rounded to that radius (a smooth line for the seams); for a
    mirror-symmetric piece of furniture made exactly symmetric."""
    plan = foot.buffer(clearance, quad_segs=QUAD_SEGS)
    # the grid's steps on a slanting or round side: bumps narrower than twice STEP_MM shaved
    # off, then all of it grown back out by the most that was shaved (never inside the
    # clearance), so the line along it is smooth
    shaved = _largest(
        plan.buffer(-STEP_MM, quad_segs=QUAD_SEGS).buffer(STEP_MM, quad_segs=QUAD_SEGS)
    )
    ring = np.asarray(plan.exterior.segmentize(STEP_MM / 2).coords)
    lost = float(shapely.distance(shaved, shapely.points(ring[:, 0], ring[:, 1])).max())
    plan = shaved.buffer(lost, quad_segs=QUAD_SEGS) if lost > 0 else plan
    plan = plan.buffer(round_mm, quad_segs=QUAD_SEGS).buffer(-round_mm, quad_segs=QUAD_SEGS)
    from coverengine.hull.box import SYMMETRY_MM

    for k, mid in mirrors:
        xs, ys = (-1.0, 1.0) if k == 0 else (1.0, -1.0)
        origin = (mid, 0.0) if k == 0 else (0.0, mid)
        mirrored = shapely.affinity.scale(plan, xs, ys, origin=origin)
        # the box's mirror lines come from the convex outside: a bay on one side only (a
        # kidney sofa's front) is no mirror image of the other side, and stays
        if shapely.hausdorff_distance(plan, mirrored) < SYMMETRY_MM:
            plan = shapely.union_all([plan, mirrored])
    return _largest(_largest(plan).simplify(SIMPLIFY_MM))


def box_plan(mesh: trimesh.Trimesh, hem: float) -> Polygon | None:
    """The floor a box cover stands on: its outline at the hem."""
    v = np.asarray(mesh.vertices)
    low = v[v[:, 2] < hem + 1.0][:, :2]  # param-ok: the hem ring
    if len(low) < 3:  # param-ok: a polygon needs three corners
        return None
    hull = shapely.MultiPoint(low).convex_hull
    return hull if isinstance(hull, Polygon) else None


def stands_out(box: Polygon | None, plan: Polygon, step_mm: float) -> float:
    """How far the box's outline stands beyond the plan at most (mm)."""
    if box is None:
        return 0.0
    ring = np.asarray(box.exterior.segmentize(step_mm).coords)
    return float(shapely.distance(plan, shapely.points(ring[:, 0], ring[:, 1])).max())


@dataclass
class Study:
    """The furniture seen from above, next to its box cover's plan."""

    foot: Polygon
    fill: float  # share of its smallest circle the footprint fills
    centre: Array
    radius: float  # of that circle (mm)
    plan: Polygon  # the outline a following cover stands on
    out_mm: float  # how far the box's plan stands beyond that outline at most
    extra_pct: float  # how much more floor the box's plan covers

    def facts(self) -> dict[str, Any]:
        return {"round_fill": round(self.fill, 3), "box_stands_out_mm": round(self.out_mm),
                "box_extra_floor_pct": round(self.extra_pct, 1)}  # fmt: skip

    def why(self, kind: str) -> str:
        if kind == "round":
            return (f"seen from above the furniture fills {PERCENT * self.fill:.0f} % of its "
                    "circle: a round top on a round skirt")  # fmt: skip
        if kind == "follow":
            return (f"the box's straight sides stood up to {self.out_mm:.0f} mm beyond the "
                    "furniture's outline: the walls follow the outline")  # fmt: skip
        return f"the box's plan stands at most {self.out_mm:.0f} mm beyond the outline"


def study(
    v: Array, f: IntArray, extra: list[Array], box_mesh: trimesh.Trimesh,
    mirrors: list[tuple[int, float]], params: EffectiveParams,
) -> Study:  # fmt: skip
    """The footprint (with the chair space in extra), its roundness, the outline to follow and
    how far the box cover's plan stands beyond it."""
    hem = _p(params, "hull.hem_height_mm")
    cell = _p(params, "hull.plan_cell_mm")
    foot = footprint(np.asarray(v), np.asarray(f), hem, cell, _p(params, "hull.bridge_gap_mm"),
                     list(extra))  # fmt: skip
    fill, centre, radius = roundness(foot)
    plan = follow_plan(foot, _p(params, "hull.clearance_mm"), _p(params, "hull.plan_round_mm"),
                       mirrors)  # fmt: skip
    boxed = box_plan(box_mesh, hem)
    out = stands_out(boxed, plan, cell)
    extra_pct = PERCENT * (boxed.area / plan.area - 1) if boxed is not None and plan.area else 0.0
    return Study(foot, fill, centre, radius, plan, out, extra_pct)


def decide(seen: Study, params: EffectiveParams) -> str:
    """round | follow | box, by hull.plan."""
    choice = str(params["hull.plan"])
    if choice != "auto":
        return choice
    if seen.fill >= _p(params, "hull.round_fill"):
        return "round"
    if seen.out_mm > _p(params, "hull.plan_follow_mm"):
        return "follow"
    return "box"


@dataclass
class Shaped:
    mesh: trimesh.Trimesh
    parts: IntArray
    report: dict[str, Any]
    warnings: list[str]


# --- round: a cylinder skirt and a cone on top -------------------------------------------------


def cone(points: Array, centre: Array, radius: float, clearance: float, min_slope: float
         ) -> tuple[float, float]:  # fmt: skip
    """The cone over the points: its apex height and slope (tan), every point at least the
    clearance under it, the slope at least min_slope (degrees); of those the one with the least
    room under it (cylinder plus cone volume)."""
    from scipy.spatial import ConvexHull

    try:
        pts = points[ConvexHull(points).vertices]
    except Exception:  # noqa: BLE001 - flat or too few points: use them all
        pts = points
    r = np.linalg.norm(pts[:, :2] - centre, axis=1)
    z = pts[:, 2] + clearance
    best: tuple[float, float, float] | None = None
    deg = min_slope
    while deg <= CONE_MAX_DEG + 1e-9:  # param-ok: numerical tolerance
        t = math.tan(math.radians(deg))
        apex = float((z + r * t).max())
        room = apex - 2.0 / 3.0 * radius * t  # param-ok: cone volume is a third of its cylinder
        if best is None or room < best[0] - 1e-9:  # param-ok: numerical tolerance
            best = (room, apex, t)
        deg += CONE_STEP_DEG
    assert best is not None
    return best[1], best[2]


def sector_width(slant: float, angle: float) -> float:
    """The narrowest width of a flat sector (radius slant, opening angle in radians)."""
    a = np.linspace(0.0, angle, ARC_POINTS)
    pts = np.vstack([[0.0, 0.0], np.column_stack([slant * np.cos(a), slant * np.sin(a)])])
    rect = np.asarray(shapely.MultiPoint(pts).minimum_rotated_rectangle.exterior.coords)[:4]
    return float(min(np.linalg.norm(rect[1] - rect[0]), np.linalg.norm(rect[2] - rect[1])))


def sectors(radius: float, t: float, usable: float, fixed: int) -> int:
    """How many equal sectors the cone's top is cut into: the setting, else the fewest whose
    flat pieces fit the roll."""
    if fixed > 0:
        return max(MIN_SECTORS, fixed)
    slant = radius * math.sqrt(1.0 + t * t)
    for k in range(MIN_SECTORS, MAX_SECTORS + 1):
        if sector_width(slant, 2 * math.pi / k * radius / slant) <= usable:
            return k
    raise CoverError(f"a round cover of {2 * radius:.0f} mm across does not fit the roll in "
                     f"{MAX_SECTORS} sectors")  # fmt: skip


def _zipper(a: list[int], fa: Array, b: list[int], fb: Array) -> list[list[int]]:
    """Triangles between two rows of points (inner row a, outer row b) running the same way,
    each row's position given as a fraction 0..1 along the row."""
    tris, i, j = [], 0, 0
    while i < len(a) - 1 or j < len(b) - 1:
        step_a = i < len(a) - 1 and (j == len(b) - 1 or fa[i + 1] <= fb[j + 1])
        if step_a:
            tris.append([a[i], b[j], a[i + 1]])
            i += 1
        else:
            tris.append([a[i], b[j], b[j + 1]])
            j += 1
    return tris


def round_mesh(
    centre: Array, radius: float, apex: float, t: float, hem: float, k_top: int, k_skirt: int,
    start: float,
) -> tuple[trimesh.Trimesh, IntArray]:  # fmt: skip
    """The cone and cylinder as triangles, with every sector and strip boundary on mesh edges;
    the label of every face (sectors 0..k_top-1, strips after them)."""
    rim = apex - radius * t
    slant = radius * math.sqrt(1.0 + t * t)
    per = int(math.ceil(2 * math.pi * radius / (k_skirt * EDGE_MM)))
    n_rim = k_skirt * max(per, MIN_RING_POINTS)
    rings = max(2, int(math.ceil(slant / EDGE_MM)))  # param-ok: at least an inner ring and the rim
    verts: list[list[float]] = [[centre[0], centre[1], apex]]
    ring_ids: list[list[int]] = []
    for i in range(1, rings + 1):
        r = radius * i / rings
        if i == rings:
            n = n_rim
        else:
            per_sector = int(math.ceil(2 * math.pi * r / (k_top * EDGE_MM)))
            n = k_top * max(per_sector, MIN_RING_POINTS)
        ang = start + 2 * math.pi * np.arange(n) / n
        ids = list(range(len(verts), len(verts) + n))
        z = apex - r * t
        verts += [[centre[0] + r * math.cos(a), centre[1] + r * math.sin(a), z] for a in ang]
        ring_ids.append(ids)
    faces: list[list[int]] = []
    labels: list[int] = []
    for s in range(k_top):
        # the fan round the apex
        first = ring_ids[0]
        n = len(first)
        lo, hi = s * n // k_top, (s + 1) * n // k_top
        row = [first[q % n] for q in range(lo, hi + 1)]
        for q in range(len(row) - 1):
            faces.append([0, row[q], row[q + 1]])
            labels.append(s)
        for i in range(len(ring_ids) - 1):
            inner, outer = ring_ids[i], ring_ids[i + 1]
            ni, no = len(inner), len(outer)
            a = [inner[q % ni] for q in range(s * ni // k_top, (s + 1) * ni // k_top + 1)]
            b = [outer[q % no] for q in range(s * no // k_top, (s + 1) * no // k_top + 1)]
            fa = np.linspace(0.0, 1.0, len(a))
            fb = np.linspace(0.0, 1.0, len(b))
            for tri in _zipper(a, fa, b, fb):
                faces.append(tri)
                labels.append(s)
    # the skirt: rows of points straight under the rim
    rim_ids = ring_ids[-1]
    levels = max(1, int(math.ceil((rim - hem) / EDGE_MM)))
    rows = [rim_ids]
    for lvl in range(1, levels + 1):
        z = rim - (rim - hem) * lvl / levels
        ids = list(range(len(verts), len(verts) + n_rim))
        verts += [[verts[q][0], verts[q][1], z] for q in rim_ids]
        rows.append(ids)
    for lvl in range(levels):
        up, down = rows[lvl], rows[lvl + 1]
        for q in range(n_rim):
            q2 = (q + 1) % n_rim
            strip = k_top + q * k_skirt // n_rim
            faces += [[up[q], down[q], down[q2]], [up[q], down[q2], up[q2]]]
            labels += [strip, strip]
    mesh = trimesh.Trimesh(np.asarray(verts), np.asarray(faces), process=False)
    # outward: the top faces up, the skirt away from the axis
    normal = np.asarray(mesh.face_normals)
    middle = np.asarray(mesh.triangles_center)
    away = np.einsum("ij,ij->i", normal[:, :2], middle[:, :2] - centre)
    lab = np.asarray(labels, np.int64)
    flip = np.where(lab < k_top, normal[:, 2] < 0, away < 0)
    f = np.asarray(faces)
    f[flip] = f[flip][:, ::-1]
    return trimesh.Trimesh(np.asarray(verts), f, process=False), lab


def round_cover(points: Array, centre: Array, radius: float, params: EffectiveParams) -> Shaped:
    """The round cover over the points (furniture above the hem, chair space, balloons)."""
    hem = _p(params, "hull.hem_height_mm")
    c = _p(params, "hull.clearance_mm")
    apex, t = cone(points, centre, radius, c, _p(params, "hull.min_slope_deg"))
    rim = apex - radius * t
    if rim <= hem:
        raise CoverError("the round cover's rim would lie below the hem")
    usable = _p(params, "roll.usable_width_mm") - 2 * _p(params, "stitching.allowance_mm")
    k_top = sectors(radius, t, usable, int(params["hull.round_top_pieces"]))
    longest = _p(params, "seams.max_skirt_panel_mm")
    k_skirt = k_top
    while 2 * math.pi * radius / k_skirt > longest or k_skirt < MIN_STRIPS:
        k_skirt += k_top
    if rim - hem > usable:
        raise CoverError(f"the round cover's skirt is {rim - hem:.0f} mm high: wider than the roll")
    # the front (-y) is the middle of a skirt strip, not a seam
    start = -math.pi / 2 - math.pi / k_skirt
    mesh, label = round_mesh(centre, radius, apex, t, hem, k_top, k_skirt, start)
    mesh.merge_vertices()
    report = {
        "kind": "round",
        "centre_mm": [round(float(x), 1) for x in centre],
        "radius_mm": round(radius, 1),
        "rim_mm": round(rim, 1),
        "apex_mm": round(apex, 1),
        "slope_deg": round(math.degrees(math.atan(t)), 2),
        "top_pieces": k_top,
        "skirt_pieces": k_skirt,
        "drainage": {
            "drains": True,
            "flat_area_mm2": 0.0,
            "hollow_area_mm2": 0.0,
            "worst_location_mm": None,
        },  # fmt: skip
    }
    return Shaped(mesh, label, report, [])


# --- follow: the footprint's outline with the box's top --------------------------------------


def corners(plan: Polygon, angle_deg: float, window_mm: float, apart_mm: float) -> list[float]:
    """Arc positions (mm along the outline from its first point) of the corners: where the
    outline turns more than angle_deg within window_mm, at most one per apart_mm."""
    xy = np.asarray(plan.exterior.coords)[:-1]
    n = len(xy)
    seg = np.roll(xy, -1, axis=0) - xy
    length = np.linalg.norm(seg, axis=1)
    s = np.concatenate([[0.0], np.cumsum(length)[:-1]])
    total = float(length.sum())
    heading = np.arctan2(seg[:, 1], seg[:, 0])
    signed = (heading - np.roll(heading, 1) + np.pi) % (2 * np.pi) - np.pi
    turn = np.abs(signed)
    d = np.abs(s[:, None] - s[None, :])
    d = np.minimum(d, total - d)
    # the net turn: a jog (out and back again) is no corner
    windowed = np.abs((np.where(d <= window_mm / 2, 1.0, 0.0) * signed[None, :]).sum(axis=1))
    limit = math.radians(angle_deg)
    chosen: list[int] = []
    for i in np.argsort(-turn, kind="stable"):
        if windowed[i] < limit:
            continue
        if all(d[i, j] >= apart_mm for j in chosen):
            chosen.append(int(i))
    return sorted(float(s[i]) for i in chosen) if n else []


def breaks(plan: Polygon, cut_at: list[float], longest: float, least: int) -> list[float]:
    """Wall seam positions along the outline: the corners, then long stretches split evenly,
    on the outline's own points so every seam is a straight upright edge."""
    xy = np.asarray(plan.exterior.coords)[:-1]
    seg = np.roll(xy, -1, axis=0) - xy
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(seg, axis=1))[:-1]])
    total = float(np.linalg.norm(seg, axis=1).sum())
    points = list(cut_at)
    if not points:  # no corners: the seams at the far left and right, then evenly between
        k = max(least, int(math.ceil(total / longest)))
        first = float(s[int(np.argmin(xy[:, 0]))])
        points = sorted((first + total * j / k) % total for j in range(k))
    out: list[float] = []
    for a, b in zip(points, points[1:] + [points[0] + total], strict=True):
        k = max(1, int(math.ceil((b - a) / longest)))
        out += [(a + (b - a) * j / k) % total for j in range(k)]

    def snap(x: float) -> float:
        d = np.abs(s - x)
        d = np.minimum(d, total - d)
        return float(s[int(np.argmin(d))])

    return sorted({snap(x) for x in out})


def follow_labels(
    mesh: trimesh.Trimesh, plan: Polygon, cuts: list[float], roof: list[Array]
) -> IntArray:
    """Pieces: each top face (the roof plane a face lies on, each connected part of it on its
    own), and the wall cut at the given positions along the outline. Faces without area (the
    solid's straight-line joints) take their neighbours' piece."""

    k = len(mesh.faces)
    nz = np.abs(np.asarray(mesh.face_normals)[:, 2])
    real = np.asarray(mesh.area_faces) > AREA_MM2
    upright = real & (nz < UPRIGHT_NZ)
    top = real & ~upright
    label = np.full(k, -1, np.int64)
    c = np.asarray(mesh.triangles_center)
    if top.any():
        away = np.stack([np.abs(c[top] @ p[:3] + p[3]) for p in roof])
        label[top] = np.argmin(away, axis=0)
    if upright.any():
        s = np.asarray(
            shapely.line_locate_point(plan.exterior, shapely.points(c[upright, 0], c[upright, 1]))
        )
        strip = np.searchsorted(np.asarray(cuts), s, side="right") % max(len(cuts), 1)
        label[upright] = len(roof) + strip
    pairs = np.asarray(mesh.face_adjacency)
    for _ in range(k):  # param-ok: loop guard; the joints take a neighbour's piece
        open_ = (label[pairs[:, 0]] < 0) != (label[pairs[:, 1]] < 0)
        if not open_.any():
            break
        a, b = pairs[open_, 0], pairs[open_, 1]
        to, frm = np.where(label[a] < 0, a, b), np.where(label[a] < 0, b, a)
        label[to] = label[frm]
    label[label < 0] = 0
    return connected(mesh, label)


def connected(mesh: trimesh.Trimesh, label: IntArray) -> IntArray:
    """Every connected part of a piece a piece of its own."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    k = len(mesh.faces)
    pairs = np.asarray(mesh.face_adjacency)
    same = label[pairs[:, 0]] == label[pairs[:, 1]]
    graph = coo_matrix((np.ones(int(same.sum())), (pairs[same, 0], pairs[same, 1])), shape=(k, k))
    _, part = connected_components(graph, directed=False)
    # a part without area (joint faces on an edge three faces share) joins the nearest real one
    area = np.bincount(part, weights=np.asarray(mesh.area_faces))
    empty = area[part] <= AREA_MM2
    if empty.any() and not empty.all():
        faces = np.asarray(mesh.faces)
        owner = np.full(len(mesh.vertices), -1)  # a real part at each point
        real = np.flatnonzero(~empty)
        owner[faces[real].ravel()] = np.repeat(part[real], 3)
        for i in np.flatnonzero(empty):
            touch = owner[faces[i]]
            if (touch >= 0).any():
                part[i] = int(np.bincount(touch[touch >= 0]).argmax())
    return np.unique(part, return_inverse=True)[1].ravel().astype(np.int64)


def even(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """The solid's long thin triangles split until no edge is longer than EDGE_MM: each pass
    halves the longest edges, both triangles on an edge at once, so no T-joint appears (a piece
    would not be one sheet) and every crease, corner and the hem stay exactly where they are
    (a remesher rounds the shallow creases between top faces off: zig-zag seams)."""
    v = [tuple(map(float, p)) for p in np.asarray(mesh.vertices)]
    faces = [list(map(int, t)) for t in np.asarray(mesh.faces)]
    for _ in range(REFINE_PASSES):
        arr = np.asarray(v)
        f = np.asarray(faces)
        e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
        key = np.sort(e, axis=1)
        length = np.linalg.norm(arr[key[:, 0]] - arr[key[:, 1]], axis=1)
        owner = np.tile(np.arange(len(f)), 3)
        long_ = np.flatnonzero(length > EDGE_MM)
        if not len(long_):
            break
        by_edge: dict[tuple[int, int], list[int]] = {}
        for k in range(len(e)):
            by_edge.setdefault((int(key[k, 0]), int(key[k, 1])), []).append(int(owner[k]))
        busy: set[int] = set()
        split: dict[int, tuple[int, int, int]] = {}  # face -> (a, b, midpoint) of its edge
        for k in long_[np.argsort(-length[long_], kind="stable")]:
            ab = (int(key[k, 0]), int(key[k, 1]))
            around = by_edge[ab]
            if any(o in busy for o in around):
                continue
            m = len(v)
            v.append(tuple((arr[ab[0]] + arr[ab[1]]) / 2))
            for o in around:
                busy.add(o)
                split[o] = (ab[0], ab[1], m)
        out: list[list[int]] = []
        for i, t in enumerate(faces):
            if i not in split:
                out.append(t)
                continue
            a, b, m = split[i]
            j = next(q for q in range(3) if {t[q], t[(q + 1) % 3]} == {a, b})
            p0, p1, p2 = t[j], t[(j + 1) % 3], t[(j + 2) % 3]
            out += [[p0, m, p2], [m, p1, p2]]
        faces = out
    return trimesh.Trimesh(np.asarray(v), np.asarray(faces, np.int64), process=False)


def euler(mesh: trimesh.Trimesh, faces: IntArray) -> int:
    """V - E + F of some faces of the mesh (1 for a disc, 0 for a ring)."""
    f = np.asarray(mesh.faces)[faces]
    e = np.sort(np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    return len(np.unique(f)) - len(np.unique(e, axis=0)) + len(f)


def welded(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Points a cut computed twice (once from each side) made one, and the faces that then
    collapse to a line dropped, so the surface stays one sheet."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree

    v = np.asarray(mesh.vertices)
    near = cKDTree(v).query_pairs(WELD_MM, output_type="ndarray")
    if len(near):
        n = len(v)
        graph = coo_matrix((np.ones(len(near)), (near[:, 0], near[:, 1])), shape=(n, n))
        _, group = connected_components(graph, directed=False)
        first = np.full(group.max() + 1, -1)
        first[group[::-1]] = np.arange(n)[::-1]
        mesh = trimesh.Trimesh(v, first[group][np.asarray(mesh.faces)], process=False)
    mesh.merge_vertices()
    f = np.asarray(mesh.faces)
    keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    return mesh


def _sheet(mesh: trimesh.Trimesh) -> tuple[int, int]:
    """The open loops of the surface and its edges shared by more than two faces."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from trimesh.grouping import group_rows

    edges = mesh.edges_sorted
    rim = edges[group_rows(edges, require_count=1)]
    _, count = np.unique(edges, axis=0, return_counts=True)
    n = len(mesh.vertices)
    graph = coo_matrix((np.ones(len(rim)), (rim[:, 0], rim[:, 1])), shape=(n, n))
    k, comp = connected_components(graph, directed=False)
    loops = len(np.unique(comp[np.unique(rim)])) if len(rim) else 0
    return loops, int((count > 2).sum())  # param-ok: an edge belongs to two faces


def cut(mesh: trimesh.Trimesh, across: Array, at: float) -> trimesh.Trimesh:
    """The surface with edges along the upright plane across.p = at, welded into one sheet; the
    surface as it was when the cut would tear it: faces lost (lying in the plane), a new open
    loop, or faces folded onto each other (a cut through points already on the plane)."""
    from coverengine.hull.plan import _insert

    out = welded(_insert(mesh, across, at))
    before, after = _sheet(mesh), _sheet(out)
    torn = (
        abs(float(out.area) - float(mesh.area)) > CUT_AREA_MM2
        or after[0] > before[0]
        or after[1] > before[1]
    )
    return mesh if torn else out


def merge_slivers(mesh: trimesh.Trimesh, label: IntArray, least_mm: float) -> IntArray:
    """A piece narrower than seams.min_piece_width_mm goes into the neighbour of its own kind
    (top or wall) it shares the longest edge with: two flat faces fold along a straight crease
    and still lie flat, a flat face on a curved wall would not."""
    from coverengine.seams import facets

    pairs = np.asarray(mesh.face_adjacency)
    edge_len = np.linalg.norm(
        np.diff(mesh.vertices[mesh.face_adjacency_edges], axis=1)[:, 0], axis=1
    )
    weighted = np.asarray(mesh.face_normals) * np.asarray(mesh.area_faces)[:, None]
    real = np.asarray(mesh.area_faces) > AREA_MM2
    for _ in range(int(label.max()) + 1):
        n = np.zeros((int(label.max()) + 1, 3))
        np.add.at(n, label, weighted)
        wall = np.abs(n[:, 2]) < UPRIGHT_NZ * np.maximum(np.linalg.norm(n, axis=1), 1e-9)
        narrow = None
        for r in np.unique(label):
            own = np.flatnonzero((label == r) & real)  # faces with area: a direction
            if not len(own):
                continue
            f = facets._facet(mesh, int(r), own, True)
            if facets.size_on_roll(facets._shape(mesh, f))[0] < least_mm:
                la, lb = label[pairs[:, 0]], label[pairs[:, 1]]
                touch = ((la == r) & (lb != r)) | ((lb == r) & (la != r))
                other = np.where(la[touch] == r, lb[touch], la[touch])
                kin = wall[other] == wall[r]
                if kin.any():
                    shared = np.bincount(other[kin], weights=edge_len[touch][kin])
                    for q in np.argsort(-shared):
                        if shared[q] <= 0:
                            break
                        # never a ring: a sliver round a piece would close round it
                        if euler(mesh, np.flatnonzero((label == r) | (label == q))) == 1:
                            narrow = (int(r), int(q))
                            break
                if narrow is not None:
                    break
        if narrow is None:
            break
        label = np.where(label == narrow[0], narrow[1], label)
    return np.unique(label, return_inverse=True)[1].ravel().astype(np.int64)


def follow_cover(
    plan: Polygon, planes: list[Array], top_z: float, params: EffectiveParams
) -> Shaped:
    """The cover standing on the plan, cut by the box's top faces."""
    from manifold3d import CrossSection, Manifold

    from coverengine.hull.plan import _wide_tops

    hem = _p(params, "hull.hem_height_mm")
    roof = [p for p in planes if p[2] >= UPRIGHT_NZ]
    if not roof:
        raise CoverError("the box has no top faces")
    ring = shapely.geometry.polygon.orient(plan, 1.0)
    from coverengine.hull.plan import heights

    # the solid reaches above the top faces everywhere over the plan, so they alone are its top
    corners_xy = np.asarray(ring.exterior.coords)[:-1]
    top_z = max(top_z, float(heights(roof, corners_xy).max()) + EDGE_MM)
    s = Manifold.extrude(CrossSection([corners_xy]), top_z - hem)
    s = s.translate((0.0, 0.0, hem))
    for p in roof:
        s = s.trim_by_plane((-p[:3]).tolist(), float(p[3]))
    raw = s.to_mesh()
    mesh = trimesh.Trimesh(np.asarray(raw.vert_properties, np.float64)[:, :3],
                           np.asarray(raw.tri_verts, np.int64), process=True)  # fmt: skip
    bottom = np.asarray(mesh.face_normals)[:, 2] < -1 + 1e-6  # param-ok: the open bottom
    mesh.update_faces(~bottom)
    mesh.remove_unreferenced_vertices()
    mesh = welded(mesh)  # one point where the solid has two (0 and -0 on a mirror line)
    usable = _p(params, "roll.usable_width_mm") - 2 * _p(params, "stitching.allowance_mm")
    least = _p(params, "seams.min_piece_width_mm")
    height = float(mesh.vertices[:, 2].max()) - hem
    longest = _p(params, "seams.max_skirt_panel_mm")
    if height > usable:  # a wall higher than the roll is wide must be short instead
        longest = min(longest, usable)
    found = corners(
        plan, _p(params, "seams.corner_angle_deg"), _p(params, "seams.corner_window_mm"),
        _p(params, "seams.min_skirt_panel_mm"),
    )  # fmt: skip
    cuts = breaks(plan, found, longest, MIN_STRIPS)
    # the wall seams lie on the outline's own corners: upright edges the splitting keeps
    mesh = even(mesh)
    label = merge_slivers(mesh, follow_labels(mesh, plan, cuts, roof), least)
    splits = _wide_tops(mesh, label, usable)
    made: list[tuple[Array, Array, float]] = []  # the piece's direction, the cut's plane
    missed = 0
    n_face = np.asarray(mesh.face_normals)
    for r, across, at_ in splits:
        own = (n_face[label == r] * np.asarray(mesh.area_faces)[label == r, None]).sum(axis=0)
        own /= np.linalg.norm(own)
        for x in at_:
            # a cut through a point already there tears: a hair beside it does not
            for shift in SHIFTS_MM:
                done = cut(mesh, across, x + shift)
                if done is not mesh:
                    mesh = done
                    made.append((own, across, x + shift))
                    break
            else:
                missed += 1
    label = merge_slivers(mesh, follow_labels(mesh, plan, cuts, roof), least)
    # the wide pieces into strips along the cuts made (their seams run downhill)
    centres = np.asarray(mesh.triangles_center)[:, :2]
    normals = np.asarray(mesh.face_normals)
    for own, across, at in made:
        on = (normals @ own > SAME_FACE) & (centres @ across > at)
        label = np.where(on, label + int(label.max()) + 1, label)
    label = connected(mesh, label)  # a band across a bent piece can fall in two
    folds: list[list[list[float]]] = []
    if bool(params["seams.fold_merge"]):  # on request: top faces one piece with a fold (ADR-055)
        from coverengine.seams import facets

        n = np.zeros((int(label.max()) + 1, 3))
        np.add.at(n, label, np.asarray(mesh.face_normals) * np.asarray(mesh.area_faces)[:, None])
        is_top = np.abs(n[:, 2]) >= UPRIGHT_NZ * np.linalg.norm(n, axis=1)
        label, _, folds = facets.join(mesh, label, is_top, least, usable, longest, True)
        label = np.unique(label, return_inverse=True)[1].ravel().astype(np.int64)
    wet = water(plan, roof, hem, params)
    report = {
        "kind": "follow",
        "outline_mm": [[round(float(x), 1), round(float(y), 1)] for x, y in plan.exterior.coords],
        "top_faces": len(roof),
        "wall_seams": len(cuts),
        "split_tops": len(splits),
        "folds_mm": folds,
        "drainage": wet,
    }
    warnings = []
    if missed:
        warnings.append(f"{missed} cut(s) of a top wider than the roll could not be made")
    if not wet["drains"]:
        x, y = wet["worst_location_mm"] or (0.0, 0.0)
        warnings.append(f"water would stay on the cover near x {x:.0f}, y {y:.0f} mm")
    return Shaped(mesh, label, report, warnings)


def water(plan: Polygon, roof: list[Array], hem: float, params: EffectiveParams) -> dict[str, Any]:
    """Rule 12 on a grid: the top is the lowest of the top faces over the plan."""
    from coverengine.hull import drainage
    from coverengine.hull.plan import SLOPE_TOLERANCE_DEG, heights

    cell = _p(params, "arrange.cell_mm")
    x0, y0, x1, y1 = plan.bounds
    xs = np.arange(x0 + cell / 2, x1, cell)
    ys = np.arange(y0 + cell / 2, y1, cell)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    inside = shapely.contains_xy(plan, gx, gy)
    z = heights(roof, np.column_stack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
    zz = np.where(inside, z, hem)
    check = drainage.check(
        zz, inside, xs, ys, _p(params, "hull.min_slope_deg") - SLOPE_TOLERANCE_DEG,
        _p(params, "hull.flat_patch_mm"),
    )  # fmt: skip
    return {
        "drains": check.drains,
        "flat_area_mm2": round(check.flat_area_mm2, 1),
        "hollow_area_mm2": round(check.hollow_area_mm2, 1),
        "worst_location_mm": None
        if check.worst_xy_mm is None
        else [round(check.worst_xy_mm[0], 1), round(check.worst_xy_mm[1], 1)],
    }
