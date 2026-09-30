"""Panels from a cut cover: disks, names, sizes, roll check, and the seams between them."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import igl
import numpy as np
import trimesh
from numpy.typing import NDArray
from scipy.spatial import ConvexHull

from coverengine.seams.cut import CutMesh, panels, seam_edges

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

# Panels smaller than this (mm2) are slivers left where seams meet; merged into a neighbour.
SLIVER_MM2 = 100.0  # param-ok: geometric tolerance
# Samples along a seam for the tightest-curve estimate: circle through points this far apart.
RADIUS_SPAN_MM = 50.0  # param-ok: sampling span
# A seam whose ends are closer than RADIUS_SPAN_MM / this is a closed loop.
CLOSED_FRACTION = 10  # param-ok: tolerance


@dataclass
class Panel:
    index: int
    name: str
    faces: IntArray
    mesh: trimesh.Trimesh
    area_mm2: float
    disk: bool
    width_mm: float  # flattened (LSCM), narrowest orientation
    length_mm: float
    region: str  # "top" or "skirt"
    seams: list[str] = field(default_factory=list)


@dataclass
class SeamInfo:
    id: str
    kind: str
    panels: tuple[int, int]
    length_mm: float
    lap_panel: int  # the panel that laps over the other
    min_radius_mm: float
    points: Array  # ordered polyline (n, 3)


def all_seam_edges(cut: CutMesh) -> IntArray:
    edges = [e for e in seam_edges(cut).values() if len(e)]
    return np.vstack(edges) if edges else np.zeros((0, 2), dtype=np.int64)


def panel_mesh(opened: trimesh.Trimesh, faces: IntArray) -> trimesh.Trimesh:
    """One panel from the unzipped cover (see cut.unzip)."""
    sub = opened.submesh([faces], append=True)
    assert isinstance(sub, trimesh.Trimesh)
    return sub


def labels_without_slivers(cut: CutMesh) -> IntArray:
    edges = seam_edges(cut)
    all_edges = np.vstack([e for e in edges.values() if len(e)] or [np.zeros((0, 2), np.int64)])
    lab = panels(cut.mesh, all_edges)
    area = np.bincount(lab, weights=cut.mesh.area_faces)
    pairs = np.asarray(cut.mesh.face_adjacency)
    for small in np.flatnonzero(area < SLIVER_MM2):
        faces = np.flatnonzero(lab == small)
        touching = pairs[np.isin(pairs[:, 0], faces) | np.isin(pairs[:, 1], faces)].ravel()
        others = lab[touching][lab[touching] != small]
        if len(others):
            lab[faces] = np.bincount(others).argmax()
    _, lab = np.unique(lab, return_inverse=True)
    return lab.astype(np.int64)


def flat_size(mesh: trimesh.Trimesh) -> tuple[float, float]:
    """Width and length of the panel laid flat (LSCM, scaled to the true area), with the width
    in the narrowest orientation (rotating calipers on the convex hull)."""
    clean = trimesh.Trimesh(mesh.vertices, mesh.faces, process=True)  # welds duplicates
    clean.update_faces(clean.nondegenerate_faces())
    clean.remove_unreferenced_vertices()
    v, f = np.asarray(clean.vertices, dtype=np.float64), np.asarray(clean.faces, dtype=np.int64)
    loop = igl.boundary_loop(f)
    if len(loop) < 3:
        return float("nan"), float("nan")
    far = loop[np.argmax(np.linalg.norm(v[loop] - v[loop[0]], axis=1))]
    b = np.array([loop[0], far], dtype=np.int64)
    bc = np.array([[0.0, 0.0], [float(np.linalg.norm(v[far] - v[loop[0]])), 0.0]])
    try:
        uv = np.asarray(igl.lscm(v, f, b, bc)[0], dtype=np.float64)  # returns (uv, system matrix)
    except RuntimeError:  # not a disk, or degenerate
        return _plane_size(v)
    if not np.all(np.isfinite(uv)):
        return _plane_size(v)
    tri = uv[f]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    area2d = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() / 2
    if area2d <= 0:
        return float("nan"), float("nan")
    uv *= math.sqrt(float(mesh.area) / area2d)
    hull = uv[ConvexHull(uv).vertices]
    best = (math.inf, 0.0)
    for a, bpt in zip(hull, np.roll(hull, -1, axis=0), strict=True):
        d = bpt - a
        n = np.linalg.norm(d)
        if n == 0:
            continue
        d /= n
        across = (hull - a) @ np.array([-d[1], d[0]])
        along = (hull - a) @ d
        width = float(np.ptp(across))
        if width < best[0]:
            best = (width, float(np.ptp(along)))
    return best


def _ordered(edges: IntArray) -> list[int]:
    """Vertex order along a chain of edges (open or closed)."""
    nbr: dict[int, list[int]] = {}
    for a, b in edges.tolist():
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    start = next((v for v, n in nbr.items() if len(n) == 1), next(iter(nbr)))
    order, prev, cur = [start], -1, start
    while True:
        nxt = [n for n in nbr[cur] if n != prev]
        if not nxt or nxt[0] == start:
            break
        prev, cur = cur, nxt[0]
        order.append(cur)
        if len(order) > len(nbr):
            break
    return order


def min_radius(points: Array) -> float:
    """Tightest curve along a polyline: smallest circle through points RADIUS_SPAN_MM apart."""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] < 2 * RADIUS_SPAN_MM:
        return math.inf
    closed = bool(np.linalg.norm(points[0] - points[-1]) < RADIUS_SPAN_MM / CLOSED_FRACTION)
    # an open seam's ends run into corners where it meets other seams; they do not count
    margin = 0.0 if closed else RADIUS_SPAN_MM
    samples = np.arange(margin, s[-1] - margin, RADIUS_SPAN_MM / 2)
    if len(samples) < 5:  # param-ok: three points need two steps each side
        return math.inf
    p = np.column_stack([np.interp(samples, s, points[:, k]) for k in range(3)])
    step = 2  # RADIUS_SPAN_MM apart
    a, b, c = p[: -2 * step], p[step:-step], p[2 * step :]
    ab, bc, ca = (np.linalg.norm(x, axis=1) for x in (b - a, c - b, a - c))
    cross = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = ab * bc * ca / (2 * cross)
    r = r[np.isfinite(r)]
    return float(r.min()) if len(r) else math.inf


def _plane_size(v: Array) -> tuple[float, float]:
    """Fallback: width and length of the points in their best-fitting plane."""
    c = v - v.mean(axis=0)
    _, _, axes = np.linalg.svd(c, full_matrices=False)
    uv = c @ axes[:2].T
    ext = np.ptp(uv, axis=0)
    return float(ext.min()), float(ext.max())
