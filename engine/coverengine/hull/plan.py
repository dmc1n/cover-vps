"""Box covers over furniture placed together that follow the members' plan (ADR-095).

The owner, 7 October 2026, on the Portofino corner (a chaise longue and a 2-seater as an L):
"you drew a sloping side instead of an L shape with a sharp corner; the cover must follow the
product and not draw diagonal lines". The box cover of ADR-038 is convex by construction (an
intersection of half-spaces), so over an L it cut the empty inner corner with a slanted wall and
spanned the whole L with one top. Here the cover is built from the plan instead:

1. The plan (`outline`): each member's plan rectangle; sides of neighbours closer than
   `arrange.align_mm` lined up; gaps closed up to the arrangement's gap plus `arrange.close_mm`;
   offset by `hull.clearance_mm` with mitred corners. So an L stays an L, its inner corner a
   right angle, and every wall stands straight down from the top to the hem. `box`: the one
   rectangle round everything.
2. The top over each member (`roofs`): flat faces tangent to that member alone, tilted only along
   the member's own axes (front to back, side to side), so every seam on the top runs square to
   the furniture: the flat top, then the faces that take away the most room (a slope from the
   front edge to the top of the back), up to `arrange.top_faces`, each worth at least
   `arrange.top_gain_pct` of the room. A face flatter than `hull.min_slope_deg` is tilted towards
   an outside edge (water runs off, rule 12); neighbours' faces that nearly agree are made equal,
   so no step of a few mm appears between two members.
3. The solid: per member its part of the plan pushed up and cut by its top faces; the union of
   these is the cover. Where one member's top is higher, its wall continues above the other's
   top (a step); nothing spans the inner corner.
4. Pieces: every flat face is a piece; a top face wider than the roll (rule 5) is cut into strips
   whose seams run downhill, so no seam lies across the flow of water.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import shapely
import trimesh
from numpy.typing import NDArray
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import ConvexHull
from shapely.geometry import Polygon
from shapely.geometry import box as plan_box

from coverengine.errors import CoverError
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

PERCENT = 100.0  # param-ok: ratio to percent
MITRE = "mitre"
# A face steeper than this |normal z| is a wall; candidates for the top are flatter.
UPRIGHT_NZ = 0.1  # param-ok: geometric constant (as hull/box.py)
# Candidate top faces whose directions are closer than this are one candidate (degrees).
SPACING_DEG = 3.0  # param-ok: geometric tolerance
# A flat face whose middle is within this share of the member's half-size of its middle is a
# table top: it becomes a gable along the long side (as hull/box.py).
CENTRAL_SHARE = 0.35  # param-ok: as hull/box.py
# Two faces are one flat piece when they turn less than this (radians) and lie this close (mm).
COPLANAR_RAD = 1e-3  # param-ok: geometric tolerance
COPLANAR_MM = 0.5  # param-ok: geometric tolerance
# A member's turn is square (0, 90, 180, 270 degrees) within this (degrees).
SQUARE_DEG = 0.01  # param-ok: geometric tolerance
QUARTER_DEG = 90.0  # param-ok: a right angle
# Box faces are split into triangles of at most this size (mm), as hull/box.py.
EDGE_MM = 40.0  # param-ok: geometric constant
# The water check passes a face tilted exactly to the minimum slope.
SLOPE_TOLERANCE_DEG = 1e-6  # param-ok: numerical tolerance
# Gaps that stay open after closing: closed further, this many times at most.
CLOSE_TRIES = 8  # param-ok: loop guard


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


@dataclass
class Member:
    """One member's part of the cover: its plan rectangle, its axes, its furniture points above
    the hem, its part of the plan and its top faces (planes n·p + d <= 0 under the top)."""

    rect: Polygon
    angle: float
    points: Array
    area: shapely.Geometry | None = None
    planes: list[Array] = field(default_factory=list)

    def axes(self) -> list[Array]:
        c, s = math.cos(self.angle), math.sin(self.angle)
        u, v = np.array([c, s]), np.array([-s, c])
        return [u, v, -u, -v]


def _square(angle: float) -> bool:
    q = math.degrees(angle) % QUARTER_DEG
    return min(q, QUARTER_DEG - q) < SQUARE_DEG


def rect_angle(corners: list[list[float]]) -> float:
    a, b = np.asarray(corners[0], float), np.asarray(corners[1], float)
    return math.atan2(float(b[1] - a[1]), float(b[0] - a[0]))


def aligned(rects: list[Polygon], angles: list[float], align_mm: float) -> list[Polygon]:
    """Square members' sides that nearly line up are lined up, outward (the cover gets at most
    align_mm looser): the back of a chaise longue 5 mm behind the sofa's back gives no 5 mm jog
    in the back wall."""
    square = [i for i, a in enumerate(angles) if _square(a)]
    bounds = [list(r.bounds) for r in rects]
    for k in range(4):  # param-ok: the four sides minx, miny, maxx, maxy
        outward = k >= 2  # param-ok: maxx, maxy
        order = sorted(square, key=lambda i: bounds[i][k], reverse=outward)
        group: list[int] = []
        for i in [*order, None]:
            if i is not None and group and abs(bounds[i][k] - bounds[group[0]][k]) <= align_mm:
                group.append(i)
                continue
            for j in group[1:]:
                bounds[j][k] = bounds[group[0]][k]
            group = [] if i is None else [i]
    return [plan_box(*bounds[i]) if i in square else r for i, r in enumerate(rects)]


def _one_piece(shape: shapely.Geometry) -> Polygon:
    polys = [p for p in getattr(shape, "geoms", [shape]) if isinstance(p, Polygon)]
    return Polygon(max(polys, key=lambda p: p.area).exterior)


def outline(
    rects: list[Polygon], footprint: str, close_mm: float, clearance_mm: float
) -> tuple[Polygon, list[str]]:
    """The cover's plan at the hem: the members' rectangles joined (follow) or the rectangle
    round them (box), offset by the clearance, corners kept sharp."""
    union = shapely.union_all(rects)
    warnings = []
    if footprint == "box":
        joined: shapely.Geometry = plan_box(*union.bounds)
    else:
        close = max(close_mm, 0.0)
        joined = union.buffer(close / 2, join_style=MITRE).buffer(-close / 2, join_style=MITRE)
        for _ in range(CLOSE_TRIES):
            if isinstance(joined, Polygon):
                break
            close = max(close * 2, clearance_mm * 2)
            joined = union.buffer(close / 2, join_style=MITRE).buffer(-close / 2, join_style=MITRE)
        if not isinstance(joined, Polygon):
            raise CoverError("the members stand too far apart for one cover")
        if close > close_mm:
            warnings.append(
                f"the members stand up to {close:.0f} mm apart: the cover spans the gap "
                "between them"
            )
    plan = _one_piece(joined.buffer(clearance_mm, join_style=MITRE))
    return Polygon(plan.exterior), warnings


def regions(members: list[Member], plan: Polygon, clearance_mm: float) -> None:
    """Each member's part of the plan: its rectangle plus the clearance, and the closed gaps it
    touches. Parts overlap where members meet; the higher top wins there."""
    near = [m.rect.buffer(clearance_mm, join_style=MITRE).intersection(plan) for m in members]
    rest = plan.difference(shapely.union_all(near))
    for m, own in zip(members, near, strict=True):
        m.area = own
    for gap in getattr(rest, "geoms", [rest]):
        if gap.is_empty or gap.area <= 0:
            continue
        for m, own in zip(members, near, strict=True):
            if own.distance(gap) <= clearance_mm:
                m.area = shapely.union_all([m.area, gap])


def _plane(n: Array, points: Array, clearance: float) -> Array:
    n = n / np.linalg.norm(n)
    return np.append(n, -(float((points @ n).max()) + clearance))


def heights(planes: list[Array], xy: Array) -> Array:
    """The top's height over plan points: the lowest of the planes."""
    out = np.full(len(xy), np.inf)
    for p in planes:
        out = np.minimum(out, (-p[3] - xy @ p[:2]) / p[2])
    return out


def grid(shape: shapely.Geometry, cell: float) -> Array:
    x0, y0, x1, y1 = shape.bounds
    xs = np.arange(x0 + cell / 2, x1, cell)
    ys = np.arange(y0 + cell / 2, y1, cell)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    inside = shapely.contains_xy(shape, gx, gy)
    return np.column_stack([gx[inside], gy[inside]])


def candidates(m: Member, any_way: bool) -> list[Array]:
    """Top faces tangent to the member and tilted only along its own axes: down to its front
    (-y in its own frame), or (any_way) also down to its back and sides."""
    out: list[Array] = []
    axes = m.axes()
    for a in axes if any_way else axes[-1:]:
        flat = np.column_stack([m.points[:, :2] @ a, m.points[:, 2]])
        try:
            hull = ConvexHull(flat)
        except Exception:  # noqa: BLE001 - too few points or all in a line
            continue
        for e in hull.equations:
            ns, nz = float(e[0]), float(e[1])
            if ns <= 0 or nz < UPRIGHT_NZ:
                continue
            n = np.array([ns * a[0], ns * a[1], nz])
            n /= np.linalg.norm(n)
            if all(
                math.degrees(math.acos(float(np.clip(n @ c, -1, 1)))) > SPACING_DEG for c in out
            ):
                out.append(n)
    return out


def roofs(m: Member, hem: float, clearance: float, params: EffectiveParams) -> None:
    """The member's top faces: the flat top, then greedily the face that takes away the most
    room, while it takes away at least arrange.top_gain_pct of it."""
    assert m.area is not None
    cell = _p(params, "arrange.cell_mm")
    xy = grid(m.area, cell)
    planes = [_plane(np.array([0.0, 0.0, 1.0]), m.points, clearance)]
    if not len(xy):
        m.planes = planes
        return

    def room(ps: list[Array]) -> float:
        return float(np.clip(heights(ps, xy) - hem, 0, None).sum())

    now = room(planes)
    gain = _p(params, "arrange.top_gain_pct") / PERCENT
    any_way = params["arrange.top_slopes"] == "any"
    options = [_plane(n, m.points, clearance) for n in candidates(m, any_way)]
    for _ in range(int(params["arrange.top_faces"])):
        scored = [(room([*planes, o]), k) for k, o in enumerate(options)]
        if not scored:
            break
        best, k = min(scored)
        if now - best < gain * now:
            break
        planes.append(options.pop(k))
        now = best
    # faces that are nowhere the lowest are not part of the top
    h = np.stack([(-p[3] - xy @ p[:2]) / p[2] for p in planes])
    used = np.unique(np.argmin(h, axis=0))
    m.planes = [planes[i] for i in sorted(used)]


def drain(
    m: Member, plan: Polygon, others: list[Polygon], clearance: float, params: EffectiveParams
) -> None:
    """Rule 12: a face flatter than hull.min_slope_deg is tilted towards an outside edge of
    the member (one with no neighbour beyond it); a flat face in the middle of the member (a
    table top) becomes a gable along its long side."""
    assert m.area is not None
    tilt = math.radians(_p(params, "hull.min_slope_deg"))
    xy = grid(m.area, _p(params, "arrange.cell_mm"))
    u, v = m.axes()[:2]
    centre = np.asarray(m.rect.centroid.coords[0])
    corners = np.asarray(m.rect.exterior.coords)[:-1] - centre
    half = np.array([np.abs(corners @ u).max(), np.abs(corners @ v).max()])
    h = np.stack([(-p[3] - xy @ p[:2]) / p[2] for p in m.planes]) if len(xy) else None
    out: list[Array] = []
    for k, p in enumerate(m.planes):
        if p[2] < math.cos(tilt) - 1e-9:  # param-ok: numerical tolerance
            out.append(p)
            continue
        if h is not None and (np.argmin(h, axis=0) == k).any():
            mid = xy[np.argmin(h, axis=0) == k].mean(axis=0)
        else:
            mid = centre
        off = np.array([(mid - centre) @ u, (mid - centre) @ v]) / np.maximum(half, 1.0)
        if np.abs(off).max() < CENTRAL_SHARE:  # a table top: a gable along the long side
            across = v if half[0] >= half[1] else u
            dirs = [across, -across]
        else:
            ranked = sorted(
                [(abs(off[0]), u * np.sign(off[0] or 1.0), half[0]),
                 (abs(off[1]), v * np.sign(off[1] or 1.0), half[1])],
                key=lambda r: -r[0],
            )  # fmt: skip
            pick = ranked[0][1]
            for _, d, reach in ranked:
                beyond = shapely.Point(*(centre + d * (reach + clearance * 2)))
                if not any(o.contains(beyond) for o in others) or not plan.contains(beyond):
                    pick = d
                    break
            dirs = [pick]
        for d in dirs:
            n = np.array([d[0] * math.sin(tilt), d[1] * math.sin(tilt), math.cos(tilt)])
            out.append(_plane(n, m.points, clearance))
    m.planes = out


def harmonise(members: list[Member], align_mm: float) -> None:
    """Neighbours' top faces that point the same way and lie within align_mm of each other are
    made one plane (the higher), so the top runs on without a step of a few mm."""
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            assert a.area is not None and b.area is not None
            if a.area.distance(b.area) > align_mm:
                continue
            for p in a.planes:
                for q in b.planes:
                    if (
                        np.allclose(p[:3], q[:3], atol=1e-9) and abs(p[3] - q[3]) <= align_mm
                    ):  # param-ok: tolerance
                        p[3] = q[3] = min(p[3], q[3])


def _solid(area: shapely.Geometry, planes: list[Array], hem: float, height: float) -> Any:
    from manifold3d import CrossSection, Manifold

    contours = []
    for poly in getattr(area, "geoms", [area]):
        if not isinstance(poly, Polygon) or poly.area <= 0:
            continue
        poly = shapely.geometry.polygon.orient(poly, 1.0)
        contours.append(np.asarray(poly.exterior.coords)[:-1])
        contours += [np.asarray(r.coords)[:-1] for r in poly.interiors]
    s = Manifold.extrude(CrossSection(contours), height).translate((0.0, 0.0, hem))
    for p in planes:
        s = s.trim_by_plane((-p[:3]).tolist(), float(p[3]))
    return s


def flat_parts(mesh: trimesh.Trimesh) -> IntArray:
    """Faces joined into flat pieces: neighbours in one plane."""
    n = np.asarray(mesh.face_normals)
    off = (np.asarray(mesh.triangles_center) * n).sum(axis=1)
    pairs = np.asarray(mesh.face_adjacency)
    same = (np.asarray(mesh.face_adjacency_angles) < COPLANAR_RAD) & (
        np.abs(off[pairs[:, 0]] - off[pairs[:, 1]]) < COPLANAR_MM
    )
    k = len(mesh.faces)
    graph = coo_matrix((np.ones(int(same.sum())), (pairs[same, 0], pairs[same, 1])), shape=(k, k))
    _, label = connected_components(graph, directed=False)
    return np.unique(label, return_inverse=True)[1].ravel().astype(np.int64)


def _merge_slivers(mesh: trimesh.Trimesh, label: IntArray, least_mm: float) -> IntArray:
    """A piece narrower than seams.min_piece_width_mm goes into the neighbour it shares the
    longest edge with (a fold, not a seam)."""
    from coverengine.seams import facets

    pairs = np.asarray(mesh.face_adjacency)
    edge_len = np.linalg.norm(
        np.diff(mesh.vertices[mesh.face_adjacency_edges], axis=1)[:, 0], axis=1
    )
    for _ in range(int(label.max()) + 1):
        narrow = None
        for r in np.unique(label):
            faces = np.flatnonzero(label == r)
            f = facets._facet(mesh, int(r), faces, True)
            if facets.size_on_roll(facets._shape(mesh, f))[0] < least_mm:
                narrow = int(r)
                break
        if narrow is None:
            break
        la, lb = label[pairs[:, 0]], label[pairs[:, 1]]
        touch = ((la == narrow) & (lb != narrow)) | ((lb == narrow) & (la != narrow))
        if not touch.any():
            break
        other = np.where(la[touch] == narrow, lb[touch], la[touch])
        shared = np.bincount(other, weights=edge_len[touch])
        label = np.where(label == narrow, int(np.argmax(shared)), label)
    return np.unique(label, return_inverse=True)[1].ravel().astype(np.int64)


def _wide_tops(
    mesh: trimesh.Trimesh, label: IntArray, limit: float
) -> list[tuple[int, Array, list[float]]]:
    """Top pieces wider than the roll: the direction across their slope and the cut positions
    along it that leave strips no wider than the roll."""
    from coverengine.seams import facets

    out = []
    for r in np.unique(label):
        faces = np.flatnonzero(label == r)
        n = (mesh.face_normals[faces] * mesh.area_faces[faces, None]).sum(axis=0)
        n /= np.linalg.norm(n)
        if abs(n[2]) < UPRIGHT_NZ:
            continue
        f = facets._facet(mesh, int(r), faces, True)
        if facets.size_on_roll(facets._shape(mesh, f))[0] <= limit:
            continue
        down = -n[:2]
        if np.linalg.norm(down) < 1e-9:  # param-ok: numerical tolerance
            down = np.array([1.0, 0.0])
        down /= np.linalg.norm(down)
        across = np.array([-down[1], down[0]])
        s = mesh.vertices[np.unique(mesh.faces[faces])][:, :2] @ across
        lo, hi = float(s.min()), float(s.max())
        k = math.ceil((hi - lo) / limit)
        out.append((int(r), across, [lo + (hi - lo) * j / k for j in range(1, k)]))
    return out


def _insert(mesh: trimesh.Trimesh, across: Array, at: float) -> trimesh.Trimesh:
    """The mesh with edges along the vertical plane across·p = at (both sides kept)."""
    normal = np.array([across[0], across[1], 0.0])
    origin = normal * at
    a = trimesh.intersections.slice_mesh_plane(mesh, normal, origin, cap=False)
    b = trimesh.intersections.slice_mesh_plane(mesh, -normal, origin, cap=False)
    out = trimesh.Trimesh(
        np.vstack([a.vertices, b.vertices]),
        np.vstack([a.faces, b.faces + len(a.vertices)]),
        process=True,
    )
    out.update_faces(out.nondegenerate_faces())
    out.remove_unreferenced_vertices()
    return out


@dataclass
class PlanCover:
    mesh: trimesh.Trimesh
    parts: IntArray
    report: dict[str, Any]
    warnings: list[str]


def build(
    points: Array,
    rects: list[list[list[float]]],
    footprint: str,
    gap_mm: float,
    params: EffectiveParams,
) -> PlanCover:
    """The cover over an arrangement whose plan follows its members (footprint follow) or is
    one rectangle round them (box). points: the furniture above the hem (mm, Z up), rects: each
    member's plan rectangle (four corners)."""
    from manifold3d import Manifold, OpType

    hem = _p(params, "hull.hem_height_mm")
    c = _p(params, "hull.clearance_mm")
    align = _p(params, "arrange.align_mm")
    polys = [Polygon(r) for r in rects]
    angles = [rect_angle(r) for r in rects]
    polys = aligned(polys, angles, align)
    plan, warnings = outline(polys, footprint, gap_mm + _p(params, "arrange.close_mm"), c)
    if footprint == "box":
        members = [Member(plan_box(*shapely.union_all(polys).bounds), 0.0, points)]
    else:
        members = []
        for poly, angle in zip(polys, angles, strict=True):
            inside = shapely.contains_xy(
                poly.buffer(align, join_style=MITRE), points[:, 0], points[:, 1]
            )
            if inside.any():
                members.append(Member(poly, angle, points[inside]))
        if not members:
            raise CoverError("no furniture inside the members' rectangles")
    regions(members, plan, c)
    for m in members:
        roofs(m, hem, c, params)
    for i, m in enumerate(members):
        drain(m, plan, [o.rect for k, o in enumerate(members) if k != i], c, params)
    harmonise(members, align)

    top = float(points[:, 2].max()) + 2 * c - hem
    solids = [_solid(m.area, m.planes, hem, top) for m in members]
    whole = Manifold.batch_boolean(solids, OpType.Add) if len(solids) > 1 else solids[0]
    raw = whole.to_mesh()
    v = np.asarray(raw.vert_properties, np.float64)[:, :3]
    f = np.asarray(raw.tri_verts, np.int64)
    mesh = trimesh.Trimesh(v, f, process=True)
    bottom = np.asarray(mesh.face_normals)[:, 2] < -1 + 1e-6  # param-ok: the open bottom
    mesh.update_faces(~bottom)
    mesh.remove_unreferenced_vertices()

    usable = _p(params, "roll.usable_width_mm") - 2 * _p(params, "stitching.allowance_mm")
    least = _p(params, "seams.min_piece_width_mm")
    label = _merge_slivers(mesh, flat_parts(mesh), least)
    splits = _wide_tops(mesh, label, usable)
    for _, across, cuts in splits:
        for t in cuts:
            mesh = _insert(mesh, across, t)
    sv, sf = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=EDGE_MM)
    mesh = trimesh.Trimesh(sv, sf, process=True)
    label = _merge_slivers(mesh, flat_parts(mesh), least)
    # the wide top pieces into strips (seams downhill)
    centres = np.asarray(mesh.triangles_center)[:, :2]
    nxt = int(label.max()) + 1
    for r, across, cuts in _wide_tops(mesh, label, usable):
        faces = np.flatnonzero(label == r)
        band = np.searchsorted(np.asarray(cuts), centres[faces] @ across)
        for b in np.unique(band)[1:]:
            label[faces[band == b]] = nxt
            nxt += 1
    label = np.unique(label, return_inverse=True)[1].ravel().astype(np.int64)

    water = _water(members, plan, hem, params)
    if not water["drains"]:
        x, y = water["worst_location_mm"] or (0.0, 0.0)
        warnings.append(f"water would stay on the cover near x {x:.0f}, y {y:.0f} mm")
    report = {
        "footprint": footprint,
        "outline_mm": [[round(float(x), 1), round(float(y), 1)] for x, y in plan.exterior.coords],
        "members": len(members),
        "top_faces": [len(m.planes) for m in members],
        "split_tops": len(splits),
        "drainage": water,
    }
    return PlanCover(mesh, label, report, warnings)


def _water(
    members: list[Member], plan: Polygon, hem: float, params: EffectiveParams
) -> dict[str, Any]:
    """Rule 12 on a grid: the top's height (the highest member top over each point)."""
    from coverengine.hull import drainage

    cell = _p(params, "arrange.cell_mm")
    x0, y0, x1, y1 = plan.bounds
    xs = np.arange(x0 + cell / 2, x1, cell)
    ys = np.arange(y0 + cell / 2, y1, cell)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    xy = np.column_stack([gx.ravel(), gy.ravel()])
    z = np.full(len(xy), -np.inf)
    for m in members:
        assert m.area is not None
        here = shapely.contains_xy(m.area, xy[:, 0], xy[:, 1])
        z[here] = np.maximum(z[here], heights(m.planes, xy[here]))
    inside = np.isfinite(z).reshape(gx.shape)
    zz = np.where(inside, z.reshape(gx.shape), hem)
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
