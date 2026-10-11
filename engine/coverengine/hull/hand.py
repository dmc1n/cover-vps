"""A box cover shaped by hand for one model (`box_shape.json`; Rens, 9 Oct 2026; ADR-117).

The box of hull/box.py is an intersection of flat half-spaces, so its edges are where the faces
happen to meet: on the SUNS sofas a wall's top edge kinks where three faces meet, and a seam can
only run along a box edge. Where the approver draws a different layout ("the top edge of each wall
straight", "a ridge along the back and a sloped seam to the front corner") and the owner chose
"by hand for these models only" (Desk questions 1, 22, 23), a person writes the pieces down once,
corner by corner, in the model's own folder:

    {"read": "how the corners were chosen",
     "pieces": {"top-front": [[[x, y, z], [x, y, z], [x, y, z], ...], ...], ...}}

mm, the model's own frame (z up, the floor at 0, the hem at hull.hem_height_mm). Each piece is
a list of faces; a face is a flat polygon, or four corners not in one plane: the ruled patch
between its opposite edges, as the fabric lies (drawn._twisted). Every piece is one panel; the
pieces are kept as drawn (hull_parts.npy). The file is per model: no model gets a special case
in the code.

The shape is checked like any cover: the furniture must stay inside it (no furniture point
outside the cover, the closest point is reported against hull.clearance_mm), water must run
off its top (rule 12, on a height grid) and the pieces must fit the roll (the usual checks after
the cut). A shape that fails says so in hull.json's warnings and in the audit.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from coverengine.errors import CoverError
from coverengine.params import EffectiveParams

HAND_FILE = "box_shape.json"
TWIST_MM = 1.0  # param-ok: a quad whose fourth corner lies further off its plane is twisted
GRID_MM = 20.0  # param-ok: the height grid of the water check
# the drainage check's slope test on a grid of straight faces: the grid's own steps cost this much
SLOPE_TOLERANCE_DEG = 0.5  # param-ok: numerical tolerance of the grid
FURNITURE_SAMPLES = 60000  # param-ok: points spread over the furniture for the inside test


def load(model_dir: Path) -> dict[str, Any] | None:
    f = model_dir / HAND_FILE
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def _off_plane(face: list[tuple[float, float, float]]) -> float:
    v = np.asarray(face, dtype=float)
    n = np.cross(v[1] - v[0], v[2] - v[0])
    if np.linalg.norm(n) < 1e-9:
        return 0.0
    return float(abs((v[3] - v[0]) @ n) / np.linalg.norm(n))


def mesh_of(spec: dict[str, Any]) -> tuple[trimesh.Trimesh, NDArray[np.int64], list[str]]:
    """The pieces as one surface, the piece of every face and the pieces' names (in order)."""
    from coverengine.drawn import Piece, _poly, _twisted, conform

    pieces = []
    for name, faces in (spec.get("pieces") or {}).items():
        mine: list[list[tuple[float, float, float]]] = []
        for f in faces:
            face = [(float(x), float(y), float(z)) for x, y, z in f]
            if len(face) < 3:  # param-ok: a face has at least three corners
                raise CoverError(f"{HAND_FILE}: a face of {name} has fewer than three corners")
            if len(face) == 4 and _off_plane(face) > TWIST_MM:  # param-ok: a quad
                mine += _twisted(str(name), face).faces
            else:
                mine.append(face)
        pieces.append(Piece(str(name), mine))
    if not pieces:
        raise CoverError(f"{HAND_FILE}: no pieces given")
    pieces = conform(pieces)
    vs, fs, part, off = [], [], [], 0
    for k, p in enumerate(pieces):
        for face in p.faces:
            v, t = _poly(face)
            vs.append(v)
            fs.append(t + off)
            part += [k] * len(t)
            off += len(v)
    mesh = trimesh.Trimesh(np.vstack(vs), np.vstack(fs), process=False)
    labels = np.asarray(part, dtype=np.int64)
    mesh.merge_vertices(digits_vertex=3)
    keep = mesh.nondegenerate_faces()
    mesh.update_faces(keep)
    labels = labels[keep]
    mesh.remove_unreferenced_vertices()
    # one winding over the whole sheet (faces given in any order), then outward: on the whole
    # away from the middle
    trimesh.repair.fix_winding(mesh)
    centre = np.append(mesh.vertices[:, :2].mean(axis=0), mesh.vertices[:, 2].max() / 3)
    out = np.einsum("ij,ij->i", mesh.face_normals, mesh.triangles_center - centre)
    f = np.asarray(mesh.faces).copy()
    if float((out * mesh.area_faces).sum()) < 0:
        f = f[:, ::-1]
    mesh = trimesh.Trimesh(mesh.vertices, f, process=False)
    return mesh, labels, [p.name for p in pieces]


def _closed(mesh: trimesh.Trimesh, hem: float) -> trimesh.Trimesh:
    """The cover with a floor at the hem (for the inside test): the open rim fanned to its
    middle."""
    from trimesh.grouping import group_rows

    edges = mesh.edges_sorted
    rim = edges[group_rows(edges, require_count=1)]
    v = np.vstack([mesh.vertices, [[*mesh.vertices[np.unique(rim), :2].mean(axis=0), hem]]])
    c = len(v) - 1
    # each rim edge with the face it belongs to, so the floor is wound the other way round
    fe = {
        tuple(sorted(e)): tuple(e)
        for t in mesh.faces
        for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))
    }
    floor = [[fe[(int(a), int(b))][1], fe[(int(a), int(b))][0], c] for a, b in rim]
    return trimesh.Trimesh(v, np.vstack([mesh.faces, floor]), process=False)


def furniture_check(
    mesh: trimesh.Trimesh, model: trimesh.Trimesh, hem: float
) -> tuple[float, int, list[float] | None]:
    """The closest furniture point above the hem to the cover (mm), how many sampled furniture
    points lie outside the cover, and the worst one."""
    import igl

    above = model.submesh([np.flatnonzero(model.triangles_center[:, 2] > hem)], append=True)
    assert isinstance(above, trimesh.Trimesh)
    if len(above.faces) == 0:
        return math.inf, 0, None
    pts, _ = trimesh.sample.sample_surface(above, FURNITURE_SAMPLES, seed=0)
    pts = pts[pts[:, 2] > hem]
    closed = _closed(mesh, hem)
    w = igl.winding_number(np.asarray(closed.vertices, np.float64),
                           np.asarray(closed.faces, np.int64),
                           np.asarray(pts, np.float64))  # fmt: skip
    d2, _, _ = igl.point_mesh_squared_distance(
        np.asarray(pts, np.float64), np.asarray(mesh.vertices, np.float64),
        np.asarray(mesh.faces, np.int64),
    )  # fmt: skip
    outside = np.abs(w) < 0.5  # param-ok: a winding number rounds to 0 outside, 1 inside
    d = np.sqrt(d2)
    worst = None
    if outside.any():
        i = int(np.flatnonzero(outside)[np.argmax(d[outside])])
        worst = [round(float(c), 1) for c in pts[i]]
    inside_d = d[~outside]
    return (float(inside_d.min()) if len(inside_d) else 0.0), int(outside.sum()), worst


def _heights(
    mesh: trimesh.Trimesh, xs: NDArray[np.float64], ys: NDArray[np.float64]
) -> NDArray[np.float64]:
    """The cover's highest point over each grid point (-inf where there is none), triangle by
    triangle (barycentric), for the faces that look up."""
    z = np.full((len(xs), len(ys)), -np.inf)
    tri = np.asarray(mesh.vertices)[np.asarray(mesh.faces)]
    up = np.asarray(mesh.face_normals)[:, 2] > 1e-6  # param-ok: walls have no height to give
    for t in tri[up]:
        (x0, y0), (x1, y1) = t[:, :2].min(axis=0), t[:, :2].max(axis=0)
        i = np.flatnonzero((xs >= x0) & (xs <= x1))
        j = np.flatnonzero((ys >= y0) & (ys <= y1))
        if not len(i) or not len(j):
            continue
        gx, gy = np.meshgrid(xs[i], ys[j], indexing="ij")
        a, b, c = t
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(det) < 1e-9:  # param-ok: a triangle seen edge-on from above
            continue
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / det
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / det
        l3 = 1 - l1 - l2
        eps = -1e-9  # param-ok: a point on a shared edge counts for both triangles
        hit = (l1 >= eps) & (l2 >= eps) & (l3 >= eps)
        h = l1 * a[2] + l2 * b[2] + l3 * c[2]
        sub = z[np.ix_(i, j)]
        z[np.ix_(i, j)] = np.where(hit, np.maximum(sub, h), sub)
    return z


def water(mesh: trimesh.Trimesh, params: EffectiveParams) -> dict[str, Any]:
    """Rule 12 on a grid: the cover's highest point over each grid point (a ray from above)."""
    from coverengine.hull import drainage

    hem = float(params["hull.hem_height_mm"])  # type: ignore[arg-type]
    lo, hi = mesh.bounds
    xs = np.arange(lo[0] + GRID_MM / 2, hi[0], GRID_MM)
    ys = np.arange(lo[1] + GRID_MM / 2, hi[1], GRID_MM)
    z = _heights(mesh, xs, ys)
    inside = np.isfinite(z)
    zz = np.where(inside, z, hem)
    got = drainage.check(
        zz, inside, xs, ys, float(params["hull.min_slope_deg"]) - SLOPE_TOLERANCE_DEG,  # type: ignore[arg-type]
        float(params["hull.flat_patch_mm"]),  # type: ignore[arg-type]
    )  # fmt: skip
    return {
        "drains": got.drains,
        "flat_area_mm2": round(got.flat_area_mm2, 1),
        "hollow_area_mm2": round(got.hollow_area_mm2, 1),
        "worst_location_mm": None
        if got.worst_xy_mm is None
        else [round(got.worst_xy_mm[0], 1), round(got.worst_xy_mm[1], 1)],
    }


def hand_cover(
    spec: dict[str, Any], model: trimesh.Trimesh, params: EffectiveParams
) -> tuple[trimesh.Trimesh, NDArray[np.int64], dict[str, Any], list[str]]:
    """The hand-shaped cover: its surface (in small triangles), the piece of every face, a
    report and warnings."""
    from coverengine.hull.box import EDGE_MM

    mesh, labels, names = mesh_of(spec)
    hem = float(params["hull.hem_height_mm"])  # type: ignore[arg-type]
    clearance = float(params["hull.clearance_mm"])  # type: ignore[arg-type]
    warnings: list[str] = []
    low = float(mesh.vertices[:, 2].min())
    if abs(low - hem) > 1.0:  # param-ok: mm
        warnings.append(f"{HAND_FILE}: the cover's lowest edge is at {low:.0f} mm, the hem at "
                        f"{hem:.0f} mm")  # fmt: skip
    closest, out_n, worst = furniture_check(mesh, model, hem)
    if out_n:
        warnings.append(f"{HAND_FILE}: {out_n} furniture point(s) outside the cover, the worst "
                        f"at {worst}")  # fmt: skip
    elif closest < clearance - 1.0:  # param-ok: mm, the grid of the sampling
        warnings.append(f"{HAND_FILE}: the furniture comes {closest:.0f} mm close to the cover "
                        f"(clearance {clearance:g} mm)")  # fmt: skip
    wet = water(mesh, params)
    if not wet["drains"]:
        x, y = wet["worst_location_mm"] or (0.0, 0.0)
        warnings.append(f"water would stay on the cover near x {x:.0f}, y {y:.0f} mm")
    nv, nf, idx = trimesh.remesh.subdivide_to_size(
        mesh.vertices, mesh.faces, max_edge=EDGE_MM, return_index=True
    )
    small = trimesh.Trimesh(nv, nf, process=True)
    parts = labels[idx]
    report = {
        "kind": "hand",
        "file": HAND_FILE,
        "read": spec.get("read"),
        "pieces": names,
        "furniture_outside_points": out_n,
        "furniture_closest_mm": round(closest, 1),
        "drainage": wet,
    }
    return small, parts, report, warnings


# --- straight wall tops ----------------------------------------------------------------------

UPRIGHT_NZ = 0.1  # param-ok: a face steeper than this is a wall (as hull/box.py)
ON_MM = 1.0  # param-ok: mm, a point this close is on the hem, on the chord, a corner of a face


def _faces_of_solid(solid: Any) -> list[tuple[NDArray[np.float64], NDArray[np.float64]]]:
    """A convex solid's faces (not its open bottom): (outward normal, corners in order)."""
    groups: dict[tuple[float, ...], list[int]] = {}
    for simplex, e in zip(solid.simplices, solid.equations, strict=True):
        if e[2] < -1 + 1e-6:  # param-ok: the open bottom
            continue
        groups.setdefault(tuple(np.round(e, 6)), []).extend(int(i) for i in simplex)
    out = []
    for key, idx in groups.items():
        n = np.asarray(key[:3])
        pts = np.unique(np.round(solid.points[sorted(set(idx))], 6), axis=0)
        c = pts.mean(axis=0)
        steep = abs(n[2]) < 0.9  # param-ok: any helper axis not along n will do
        helper = np.array([0.0, 0.0, 1.0]) if steep else np.array([1.0, 0.0, 0.0])
        u = np.cross(helper, n)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        order = np.argsort(np.arctan2((pts - c) @ v, (pts - c) @ u))
        out.append((n, pts[order]))
    return out


def straight_tops(solid: Any, hem: float) -> dict[str, Any]:
    """The box's pieces with the top edge of every wall one straight line from corner to corner
    (Rens, 9 Oct 2026, Desk questions 22 and 23: "the top edge of the long wall straight, one
    line from corner to corner"). A wall's top edge kinks where it meets two roof faces; the
    part of the wall above the straight line goes to the roof pieces as flaps (folded down),
    split by an upright seam under every kink. The shape does not change: every piece is flat
    faces joined along their edges, so it lies flat exactly."""
    faces = _faces_of_solid(solid)
    walls = [(n, p) for n, p in faces if abs(n[2]) < UPRIGHT_NZ]
    roofs = [(n, p) for n, p in faces if abs(n[2]) >= UPRIGHT_NZ]
    roof_faces: list[list[list[list[float]]]] = [[p.tolist()] for _, p in roofs]
    pieces: dict[str, list[list[list[float]]]] = {}
    for k, (n, p) in enumerate(walls):
        u = np.cross([0.0, 0.0, 1.0], n)
        u /= np.linalg.norm(u)
        top = p[p[:, 2] > hem + ON_MM]
        top = top[np.argsort(top @ u)]
        a, b = top[0], top[-1]

        def chord(q: NDArray[np.float64], a: NDArray[np.float64] = a,
                  b: NDArray[np.float64] = b, u: NDArray[np.float64] = u,
                  ) -> NDArray[np.float64]:  # fmt: skip
            t = float((q - a) @ u) / max(float((b - a) @ u), 1e-9)
            return a + t * (b - a)

        above = [float(q[2] - chord(q)[2]) for q in top[1:-1]]
        if not above or max(above) <= ON_MM:
            pieces[f"wall-{k + 1}"] = [p.tolist()]
            continue
        base = sorted((q for q in p if q[2] <= hem + ON_MM), key=lambda q: float(q @ u))
        # the wall below the chord: its bottom from end to end, then the chord back
        pieces[f"wall-{k + 1}"] = [[base[0].tolist(), base[-1].tolist(), b.tolist(), a.tolist()]]
        for q0, q1 in zip(top[:-1], top[1:], strict=True):
            flap = [q0.tolist(), q1.tolist()]
            c1, c0 = chord(q1), chord(q0)
            if float(np.linalg.norm(c1 - q1)) > ON_MM:
                flap.append(c1.tolist())
            if float(np.linalg.norm(c0 - q0)) > ON_MM:
                flap.append(c0.tolist())
            for r, (_, rp) in enumerate(roofs):  # the roof face that has this top edge
                if all(float(np.min(np.linalg.norm(rp - q, axis=1))) < ON_MM for q in (q0, q1)):
                    roof_faces[r].append(flap)
                    break
    for r, fs in enumerate(roof_faces):
        pieces[f"top-{r + 1}"] = fs
    return {"read": "the box with a straight top edge on every wall (seams.straight_wall_tops)",
            "pieces": pieces}  # fmt: skip
