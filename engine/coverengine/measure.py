"""Measuring a cover (ADR-110): the owner, 9 Oct 2026: "we have sewn some covers, and for
checking it is easier if we have sizes in the 3D part, for example the height of the air vents
and their placement."

- `snap_doc`: what the 3D viewer's Measure tool snaps to: every seam and every free edge (the
  hem) of the cover as a 3D polyline, the cover's lower edge and box (mm, Z up, model
  coordinates, as `panels.npz`).
- `geodesic`: the distance between two points along the fabric, as a tape measure laid on the
  sewn cover goes: the shortest path over the cover surface (geometry-central's edge-flip
  geodesics through potpourri3d, exact on the triangle mesh), next to the straight distance and
  the height difference.
- `check_points`: the numbers the workshop measures on a sewn cover: the overall size, the
  skirt height, every vent (size, height above the hem, distance to the seams beside it), the
  hem length of every piece and every seam's length. The check list (export/checklist.py) prints
  them; the Desk takes measured values against the same keys and keeps the differences.

All sizes are on the finished cover, seam to seam, without allowances, in mm.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

SNAP_FORMAT = 1
ON_COVER_MM = 30.0  # param-ok: a point farther than this from the cover is not on it
EDGE_SHARE = 0.02  # param-ok: a point this close to a triangle's edge (barycentric) is moved in
VERTEX_MM = 0.5  # param-ok: a point this close to a vertex is that vertex
LOWER_EDGE_MM = 5.0  # param-ok: a free edge this close to the lowest point is the hem


# ---- the cover's surface --------------------------------------------------------------------


def _load(model_dir: Path) -> dict[str, Any]:
    stamp = (model_dir / "panels.npz").stat().st_mtime_ns
    return _load_cached(str(model_dir), stamp)


@lru_cache(maxsize=8)  # param-ok: covers kept in memory
def _load_cached(model_dir: str, stamp: int) -> dict[str, Any]:
    d = Path(model_dir)
    data = np.load(d / "panels.npz")
    original = np.asarray(data["original_vertex"], dtype=np.int64)
    vertices = np.asarray(data["vertices"], dtype=np.float64)
    points = np.zeros((int(original.max()) + 1, 3))
    points[original] = vertices
    faces = original[np.asarray(data["faces"], dtype=np.int64)]
    cut = json.loads((d / "panels.json").read_text(encoding="utf-8"))
    return {
        "points": points,
        "faces": faces,
        "labels": np.asarray(data["labels"], dtype=np.int64),
        "seam_edges": np.asarray(data["seam_edges"], dtype=np.int64),
        "seam_index": np.asarray(data["seam_index"], dtype=np.int64),
        "seams": cut.get("seams", []),
        "names": [p["name"] for p in cut["panels"]],
    }


def _chains(edges: IntArray) -> list[list[int]]:
    """Edges joined into polylines (closed ones repeat their first vertex)."""
    nbr: dict[int, list[int]] = {}
    for a, b in edges.tolist():
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    used: set[tuple[int, int]] = set()
    out: list[list[int]] = []
    # open chains from their ends first, then the loops
    starts = sorted(v for v, n in nbr.items() if len(n) != 2) + sorted(nbr)
    for s in starts:
        for first in sorted(nbr[s]):
            if (min(s, first), max(s, first)) in used:
                continue
            path = [s, first]
            used.add((min(s, first), max(s, first)))
            while True:
                here = path[-1]
                nxt = [w for w in sorted(nbr[here]) if (min(here, w), max(here, w)) not in used]
                if len(nbr[here]) != 2 or not nxt:
                    break
                used.add((min(here, nxt[0]), max(here, nxt[0])))
                path.append(nxt[0])
            out.append(path)
    return out


def _boundary_edges(faces: IntArray) -> IntArray:
    e = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    uniq, count = np.unique(e, axis=0, return_counts=True)
    out: IntArray = uniq[count == 1]
    return out


def _r(p: Array) -> list[float]:
    return [round(float(x), 1) for x in p]


def snap_doc(model_dir: Path) -> dict[str, Any]:
    """The lines the Measure tool snaps to (see the module's docstring)."""
    c = _load(model_dir)
    pts = c["points"]
    seams = []
    for i, s in enumerate(c["seams"]):
        edges = c["seam_edges"][c["seam_index"] == i]
        for chain in _chains(edges):
            seams.append(
                {"id": s["id"], "panels": s["panels"], "points_mm": [_r(pts[k]) for k in chain]}
            )
    edges = [[_r(pts[k]) for k in chain] for chain in _chains(_boundary_edges(c["faces"]))]
    used = np.unique(c["faces"])
    lo, hi = pts[used].min(axis=0), pts[used].max(axis=0)
    return {
        "format": SNAP_FORMAT,
        "seams": seams,
        "edges": edges,
        "lower_edge_z_mm": round(float(lo[2]), 1),
        "box_mm": [_r(lo), _r(hi)],
    }


# ---- along the fabric -----------------------------------------------------------------------


def _manifold(points: Array, faces: IntArray) -> tuple[Array, IntArray]:
    """The cover as a manifold, oriented surface for geometry-central: faces glued only along
    edges that two faces share with opposite directions; every vertex split into one copy per
    fan of faces around it (a vertex where two edges of the hem touch, a seam with three
    pieces). Lengths do not change."""
    f = faces[
        (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 2] != faces[:, 0])
    ]
    f = np.unique(f, axis=0)
    n = len(f)
    # half-edges a->b of every face, corners (face, slot)
    a = f.reshape(-1)
    b = f[:, [1, 2, 0]].reshape(-1)
    face_of = np.repeat(np.arange(n), 3)
    slot = np.tile(np.arange(3), n)
    key = np.minimum(a, b) * (len(points) + 1) + np.maximum(a, b)
    order = np.argsort(key, kind="stable")
    ks = key[order]
    starts = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1]])
    counts = np.diff(np.r_[starts, len(ks)])
    pairs = starts[counts == 2]
    h1, h2 = order[pairs], order[pairs + 1]
    glue = a[h1] == b[h2]  # opposite directions: consistently oriented
    h1, h2 = h1[glue], h2[glue]
    # union the corners at both ends of every glued edge
    corner = lambda h, end: face_of[h] * 3 + (slot[h] + end) % 3  # noqa: E731
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    rows = np.concatenate([corner(h1, 0), corner(h1, 1)])
    cols = np.concatenate([corner(h2, 1), corner(h2, 0)])
    m = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(3 * n, 3 * n))
    _, label = connected_components(m, directed=False)
    new_faces = label.reshape(n, 3).astype(np.int64)
    new_points = np.zeros((int(label.max()) + 1, 3))
    new_points[label] = points[f.reshape(-1)]
    return new_points, new_faces


@lru_cache(maxsize=4)  # param-ok: covers kept in memory
def _manifold_cached(model_dir: str, stamp: int) -> tuple[Array, IntArray]:
    c = _load_cached(model_dir, stamp)
    return _manifold(c["points"], c["faces"])


def _insert(points: Array, faces: IntArray, p: Array) -> tuple[Array, IntArray, int, float]:
    """`p` put on the surface as a vertex (its triangle split in three); the vertex, and how far
    `p` was from the surface."""
    import igl

    d2, fi, q = igl.point_mesh_squared_distance(p[None], points, faces.astype(np.int64))
    k = int(fi[0])
    q = np.asarray(q[0], dtype=np.float64)
    tri = points[faces[k]]
    near = np.linalg.norm(tri - q, axis=1)
    if near.min() <= VERTEX_MM:
        return points, faces, int(faces[k][int(np.argmin(near))]), float(math.sqrt(d2[0]))
    w = np.asarray(igl.barycentric_coordinates(q[None], tri[0:1], tri[1:2], tri[2:3]))[0]
    w = np.clip(w, EDGE_SHARE, None)
    w = w / w.sum()
    q = w @ tri
    i = len(points)
    points = np.vstack([points, q])
    x, y, z = faces[k]
    faces = np.vstack([np.delete(faces, k, axis=0), [[x, y, i], [y, z, i], [z, x, i]]])
    return points, faces, i, float(math.sqrt(d2[0]))


def geodesic(model_dir: Path, a: list[float], b: list[float]) -> dict[str, Any]:
    """Between two points (mm, Z up): the straight distance, the height difference and the
    distance along the fabric with its path. `surface_mm` is None when a point is not on the
    cover (the furniture clicked) or the two lie on parts of the cover that do not join."""
    pa, pb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    out: dict[str, Any] = {
        "straight_mm": round(float(np.linalg.norm(pb - pa)), 1),
        "height_mm": round(float(pb[2] - pa[2]), 1),
        "surface_mm": None,
        "path_mm": [],
    }
    stamp = (model_dir / "panels.npz").stat().st_mtime_ns
    points, faces = _manifold_cached(str(model_dir), stamp)
    points, faces, ia, da = _insert(points, faces, pa)
    points, faces, ib, db = _insert(points, faces, pb)
    out["off_cover_mm"] = [round(da, 1), round(db, 1)]
    if max(da, db) > ON_COVER_MM:
        out["why"] = "a point is not on the cover"
        return out
    if ia == ib:
        out |= {"surface_mm": 0.0, "path_mm": [_r(points[ia])]}
        return out
    # the part of the cover holding both points (the solver wants one connected surface)
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]]])
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(points), len(points)))
    _, comp = connected_components(g, directed=False)
    if comp[ia] != comp[ib]:
        out["why"] = "the two points are on parts of the cover that do not join"
        return out
    keep = comp[faces[:, 0]] == comp[ia]
    sub = faces[keep]
    used = np.unique(sub)
    remap = -np.ones(len(points), dtype=np.int64)
    remap[used] = np.arange(len(used))
    import potpourri3d as pp3d

    try:
        solver = pp3d.EdgeFlipGeodesicSolver(points[used], remap[sub])
        path = np.asarray(solver.find_geodesic_path(int(remap[ia]), int(remap[ib])))
    except (RuntimeError, ValueError) as exc:
        out["why"] = f"the surface path could not be found ({exc})"
        return out
    length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
    out |= {"surface_mm": round(length, 1), "path_mm": [_r(p) for p in path]}
    return out


# ---- the check list's points ----------------------------------------------------------------


def lower_edge_length(model_dir: Path) -> float:
    """The hem all round: the free edges of the cover at its lower edge (not a free edge higher
    up, such as an opening or a drawing cover's open inner edge)."""
    c = _load(model_dir)
    pts = c["points"]
    e = _boundary_edges(c["faces"])
    low = float(pts[np.unique(c["faces"]), 2].min())
    at = (pts[e[:, 0], 2] <= low + LOWER_EDGE_MM) & (pts[e[:, 1], 2] <= low + LOWER_EDGE_MM)
    return float(np.linalg.norm(pts[e[at, 0]] - pts[e[at, 1]], axis=1).sum())


def check_points(model_dir: Path, params: Any = None) -> dict[str, Any]:
    """The numbers to check on a sewn cover, each with a stable key (the Desk stores measured
    values against them):

        {"points": [{"key", "group", "label", "mm"}], "vents": [...vents.json...],
         "rotation_deg": r, "warnings": [...]}

    Overall sizes are in the size drawing's plan (`drawing.plan_rotation_deg`), as sizes.pdf."""
    from coverengine.export import drawing
    from coverengine.finish.vents3d import ensure_vents

    if params is None:
        from coverengine.params.registry import Registry, resolve_model

        params = resolve_model(model_dir, {}, Registry.load(None), None)
    doc = json.loads((model_dir / "pattern.json").read_text(encoding="utf-8"))
    cover = drawing.load_cover(model_dir, doc, params)
    lower = float(cover.vertices[:, 2].min())
    cover.hem_z = lower  # the cover's own lower edge (hull.json's is the surface's design value)
    v = cover.vertices
    pts: list[dict[str, Any]] = []

    def add(group: str, key: str, label: str, mm: float | None) -> None:
        if mm is not None and math.isfinite(mm):
            pts.append({"key": key, "group": group, "label": label, "mm": round(float(mm), 1)})

    add("Overall", "size.length", "Length (across the front)", float(np.ptp(v[:, 0])))
    add("Overall", "size.depth", "Depth (front to back)", float(np.ptp(v[:, 1])))
    add("Overall", "size.height", "Height (lower edge to top)", float(v[:, 2].max() - lower))
    add("Overall", "hem.length", "Hem, all round", lower_edge_length(model_dir))
    for name, region in zip(cover.names, cover.regions, strict=True):
        if region == "skirt":
            add("Skirt", f"skirt.{name}", f"Skirt height, middle of {name}",
                drawing.skirt_height(cover, name))  # fmt: skip
    vents_doc: dict[str, Any] = {"vents": []}
    path = ensure_vents(model_dir)
    if path is not None:
        vents_doc = json.loads(path.read_text(encoding="utf-8"))
    for x in vents_doc.get("vents", []):
        n = x.get("number")
        w, h = x["size_mm"]
        tag = f"V{n} ({x['piece']})"
        add("Air vents", f"vent.{n}.width", f"{tag} opening width", w)
        add("Air vents", f"vent.{n}.height", f"{tag} opening height", h)
        add("Air vents", f"vent.{n}.above_hem", f"{tag} bottom edge above the hem",
            x.get("above_hem_mm"))  # fmt: skip
        for side in ("left", "right"):
            s = (x.get("sides") or {}).get(side)
            if s:
                to = {"seam": f"seam to {s['name']}", "corner": "corner", "edge": "edge"}[s["to"]]
                add("Air vents", f"vent.{n}.{side}", f"{tag} {side} side to the {to}", s["mm"])
    for p in doc["panels"]:
        hem = sum(float(e["length_3d_mm"]) for e in p["edges"] if e["kind"] == "hem")
        if hem > 0:
            add("Pieces", f"piece.{p['name']}.hem", f"{p['name']}: hem, seam to seam", hem)
        add("Pieces", f"piece.{p['name']}.flat", f"{p['name']}: flat piece, length",
            float(p["flat_length_mm"]))  # fmt: skip
        add("Pieces", f"piece.{p['name']}.flat_width", f"{p['name']}: flat piece, width",
            float(p["flat_width_mm"]))  # fmt: skip
    for s in cover.seams:
        add("Seams", f"seam.{s['id']}", f"Seam {s['id']}", float(s["length_mm"]))
    return {
        "points": pts,
        "vents": vents_doc.get("vents", []),
        "lower_edge_z_mm": round(lower, 1),
        "rotation_deg": cover.rotation_deg,
        "warnings": list(vents_doc.get("warnings", [])),
    }


def deviations(points: list[dict[str, Any]], measured: dict[str, float]) -> list[dict[str, Any]]:
    """Measured values (mm) against the check points: key, label, expected, measured,
    difference (measured - expected). Keys not on the check list are left out."""
    by_key = {p["key"]: p for p in points}
    out = []
    for key, value in measured.items():
        p = by_key.get(key)
        if p is None or not isinstance(value, int | float) or not math.isfinite(value):
            continue
        out.append({"key": key, "label": p["label"], "expected_mm": p["mm"],
                    "measured_mm": round(float(value), 1),
                    "diff_mm": round(float(value) - float(p["mm"]), 1)})  # fmt: skip
    return out
