"""Cutting a surface mesh along seams given as zero sets of scalar fields (ADR-026).

A seam is where a field f (a distance, in mm) crosses zero, on a chosen set of faces. Faces the
seam crosses are split; each new vertex sits exactly on the seam and is shared by both faces of
its edge, so a seam is an exact edge path shared by the panels on either side. Vertices already
within `snap` of the seam count as on it, so no sliver triangles are made.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import trimesh
from numpy.typing import NDArray
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]
Field = Callable[[Array], Array]  # points (n, 3) -> signed distance (n,)
FaceFilter = Callable[["CutMesh"], NDArray[np.bool_]]
# Vertices up to this many snap distances from a seam (by field value) are checked for snapping.
SNAP_SEARCH = 10  # param-ok: search factor


@dataclass
class Seam:
    id: str
    kind: str  # "skirt" (skirt to top), "corner" (vertical in the skirt), "top", "roll"
    field: Field
    faces: FaceFilter  # which faces this seam may cut
    # (dataclasses.field: this class has an attribute called `field`)
    vertices: set[int] = dataclasses.field(default_factory=set)  # mesh vertices on the seam
    edges: set[tuple[int, int]] = dataclasses.field(default_factory=set)  # edges (a < b)


@dataclass
class CutMesh:
    mesh: trimesh.Trimesh
    seams: list[Seam]
    # region label per face (e.g. 0 = top, 1 = skirt once the skirt seam is cut); faces made by
    # splitting a face inherit its label, so later seams can be limited to one region
    region: IntArray = dataclasses.field(default_factory=lambda: np.zeros(0, dtype=np.int64))

    def __post_init__(self) -> None:
        if len(self.region) != len(self.mesh.faces):
            self.region = np.zeros(len(self.mesh.faces), dtype=np.int64)


def _split(
    mesh: trimesh.Trimesh, values: Array, faces_mask: NDArray[np.bool_]
) -> tuple[trimesh.Trimesh, dict[tuple[int, int], int], IntArray]:
    """Split the masked faces where `values` changes sign. Returns the mesh, for every cut
    edge (a, b) with a < b the index of the new vertex on it, and each face's original face."""
    v = np.asarray(mesh.vertices, dtype=np.float64)
    f = np.asarray(mesh.faces, dtype=np.int64)
    sign = np.sign(values)
    new_vertices: list[Array] = []
    on_edge: dict[tuple[int, int], int] = {}

    def cut_point(a: int, b: int) -> int:
        key = (a, b) if a < b else (b, a)
        if key not in on_edge:
            t = values[key[0]] / (values[key[0]] - values[key[1]])
            new_vertices.append(v[key[0]] + t * (v[key[1]] - v[key[0]]))
            on_edge[key] = len(v) + len(new_vertices) - 1
        return on_edge[key]

    out: list[tuple[int, int, int]] = []
    origin: list[int] = []
    keep = np.ones(len(f), dtype=bool)
    fs = sign[f]
    crossing = faces_mask & (fs.max(axis=1) > 0) & (fs.min(axis=1) < 0)
    for fi in np.flatnonzero(crossing):
        tri = f[fi]
        keep[fi] = False
        # rotate so the lone vertex (the one whose sign differs from the other two) is first
        for r in range(3):
            a, b, c = tri[r], tri[(r + 1) % 3], tri[(r + 2) % 3]
            sa, sb, sc = sign[a], sign[b], sign[c]
            if sb == 0 and sa * sc < 0:  # the seam passes through b
                m = cut_point(c, a)
                out += [(a, b, m), (m, b, c)]
                origin += [int(fi)] * 2
                break
            if sa != 0 and sb != 0 and sc != 0 and sb == sc and sa != sb:
                mab, mca = cut_point(a, b), cut_point(c, a)
                out += [(a, mab, mca), (mab, b, c), (mab, c, mca)]
                origin += [int(fi)] * 3
                break
    # faces outside the mask that share a cut edge must be split too, or the mesh would get a
    # T-junction there (a neighbour keeping the whole edge while this side has two halves)
    if on_edge:
        for fi in np.flatnonzero(keep):
            tri = [int(x) for x in f[fi]]
            pieces = [tri]
            for r in range(3):
                a, b = tri[r], tri[(r + 1) % 3]
                found = on_edge.get((a, b) if a < b else (b, a))
                if found is None:
                    continue
                m = found
                split_pieces = []
                for t in pieces:
                    for q in range(3):
                        x, y, z = t[q], t[(q + 1) % 3], t[(q + 2) % 3]
                        if {x, y} == {a, b}:
                            split_pieces += [[x, m, z], [m, y, z]]
                            break
                    else:
                        split_pieces.append(t)
                pieces = split_pieces
            if len(pieces) > 1:
                keep[fi] = False
                out += [(t[0], t[1], t[2]) for t in pieces]
                origin += [int(fi)] * len(pieces)
    faces = np.vstack([f[keep], np.array(out, dtype=np.int64).reshape(-1, 3)])
    verts = np.vstack([v, np.array(new_vertices).reshape(-1, 3)])
    parents = np.concatenate([np.flatnonzero(keep), np.array(origin, dtype=np.int64)])
    return trimesh.Trimesh(verts, faces, process=False), on_edge, parents


def _surface_step(
    mesh: trimesh.Trimesh, idx: IntArray, fld: Field, values: Array
) -> tuple[Array, Array]:
    """For vertices `idx`: the move along the surface onto the field's zero set, and the surface
    distance to it. The gradient is taken along the surface (on a steep surface a floor-plane
    distance changes slowly, so the seam is further away than the field value suggests)."""
    step = 1e-3
    p = np.asarray(mesh.vertices)[idx]
    g = np.column_stack([(fld(p + e) - fld(p - e)) / (2 * step) for e in np.eye(3) * step])
    n = np.asarray(mesh.vertex_normals)[idx]
    gs = g - (g * n).sum(axis=1, keepdims=True) * n  # gradient along the surface
    g2 = np.maximum((gs**2).sum(axis=1), 1e-12)
    move = -values[:, None] * gs / g2[:, None]
    return move, np.abs(values) / np.sqrt(g2)


def apply(cut: CutMesh, seam: Seam, snap_mm: float) -> CutMesh:
    """Cut the mesh along one more seam and record the vertices on it."""
    mesh = cut.mesh
    mask = seam.faces(cut)
    if not mask.any():
        return CutMesh(mesh, [*cut.seams, seam], cut.region)
    involved = np.unique(np.asarray(mesh.faces)[mask])
    verts = np.asarray(mesh.vertices, dtype=np.float64).copy()
    values = np.full(len(verts), np.nan)
    values[involved] = seam.field(verts[involved])
    # vertices closer than the snap distance move onto the seam (in the floor plane, where all
    # seam fields live), so no slivers form and every other vertex is clearly on one side
    candidates = involved[
        (np.abs(values[involved]) < snap_mm * SNAP_SEARCH) & (values[involved] != 0.0)
    ]
    if len(candidates):
        move, dist = _surface_step(mesh, candidates, seam.field, values[candidates])
        near = dist < snap_mm
        if near.any():
            chosen = candidates[near]
            verts[chosen] += move[near]
            values[chosen] = 0.0
            mesh = trimesh.Trimesh(verts, mesh.faces, process=False)
    new_mesh, on_edge, parents = _split(mesh, np.nan_to_num(values, nan=0.0), mask)
    # values on the new mesh: the cut vertices lie exactly on the seam
    vals = np.concatenate([values, np.zeros(len(new_mesh.vertices) - len(values))])
    seam.vertices = {int(i) for i in np.flatnonzero(vals == 0.0)}
    seam.edges = _edges_on_zero_set(new_mesh, vals, cut.region[parents], seam, cut)
    # earlier seams: an edge split by this cut becomes two edges through the new vertex
    for earlier in cut.seams:
        for (a, b), m in on_edge.items():
            if (a, b) in earlier.edges:
                earlier.edges.discard((a, b))
                earlier.edges |= {(min(a, m), max(a, m)), (min(m, b), max(m, b))}
                earlier.vertices.add(m)
    return CutMesh(new_mesh, [*cut.seams, seam], cut.region[parents])


def _edges_on_zero_set(
    mesh: trimesh.Trimesh, vals: Array, region: IntArray, seam: Seam, cut: CutMesh
) -> set[tuple[int, int]]:
    """Edges with both ends exactly on the seam whose two faces lie on opposite sides.

    Values are exact here: vertices near the seam were moved onto it, and every other vertex is
    at least the snap distance away, so the sign of a face's vertex off the edge is reliable."""
    pairs = np.asarray(mesh.face_adjacency)
    shared = np.asarray(mesh.face_adjacency_edges)
    opposite = np.asarray(mesh.face_adjacency_unshared)
    both_on = (vals[shared[:, 0]] == 0.0) & (vals[shared[:, 1]] == 0.0)
    # side of each face: its vertex off the edge, or, for a small face lying entirely on the
    # seam, the field at its centre
    centres = np.asarray(mesh.triangles_center)
    s1 = np.sign(vals[opposite[:, 0]])
    s2 = np.sign(vals[opposite[:, 1]])
    for side, col in ((s1, 0), (s2, 1)):
        flat = both_on & (side == 0)
        if flat.any():
            side[flat] = np.sign(seam.field(centres[pairs[flat, col]]))
    ok = both_on & (s1 * s2 < 0)  # nan (not involved) never passes
    del region, cut
    return {(int(min(a, b)), int(max(a, b))) for a, b in shared[ok]}


def seam_edges(cut: CutMesh) -> dict[str, IntArray]:
    """The mesh edges of every seam."""
    return {
        seam.id: np.array(sorted(seam.edges), dtype=np.int64).reshape(-1, 2) for seam in cut.seams
    }


def panels(mesh: trimesh.Trimesh, cut_edges: IntArray) -> IntArray:
    """Panel label per face: faces connected across edges that are not seams."""
    adjacency = np.asarray(mesh.face_adjacency)
    shared = np.sort(np.asarray(mesh.face_adjacency_edges), axis=1)
    if len(cut_edges):
        cut_set = {tuple(e) for e in np.sort(cut_edges, axis=1).tolist()}
        crossing = np.array([tuple(e) not in cut_set for e in shared.tolist()], dtype=bool)
    else:
        crossing = np.ones(len(adjacency), dtype=bool)
    a = adjacency[crossing]
    n = len(mesh.faces)
    graph = coo_matrix((np.ones(len(a)), (a[:, 0], a[:, 1])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    # number panels in order of their first face, so labels are deterministic
    _, first = np.unique(labels, return_index=True)
    rank = np.empty(len(first), dtype=np.int64)
    rank[np.argsort(first)] = np.arange(len(first))
    return rank[labels]


def is_disk(mesh: trimesh.Trimesh) -> bool:
    """One boundary loop and Euler characteristic 1."""
    edges = np.sort(np.asarray(mesh.edges), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = np.unique(edges, axis=0)[counts == 1]
    if len(boundary) == 0:
        return False
    nv = len(np.unique(boundary))
    size = len(mesh.vertices)
    graph = coo_matrix(
        (np.ones(len(boundary)), (boundary[:, 0], boundary[:, 1])), shape=(size, size)
    )
    _, labels = connected_components(graph, directed=False)
    used = np.unique(boundary)
    loops = len(np.unique(labels[used]))
    euler = len(mesh.vertices) - len(np.unique(edges, axis=0)) + len(mesh.faces)
    return loops == 1 and euler == 1 and nv == len(boundary)


def unzip(mesh: trimesh.Trimesh, cut_edges: IntArray) -> trimesh.Trimesh:
    """The same surface with every seam opened: faces on opposite sides of a seam edge no longer
    share its vertices. (A skirt ring cut by one seam belongs to one panel; without unzipping
    its two sides would join again.) Face order and positions are unchanged."""
    f = np.asarray(mesh.faces, dtype=np.int64)
    n = len(f)
    cut_set = {tuple(e) for e in np.sort(np.asarray(cut_edges, dtype=np.int64), axis=1).tolist()}
    pairs = np.asarray(mesh.face_adjacency)
    shared = np.sort(np.asarray(mesh.face_adjacency_edges), axis=1)
    keep = np.array([tuple(e) not in cut_set for e in shared.tolist()], dtype=bool)
    rows, cols = [], []
    for (fa, fb), (u, w) in zip(pairs[keep].tolist(), shared[keep].tolist(), strict=True):
        for vert in (u, w):
            ca = int(np.flatnonzero(f[fa] == vert)[0])
            cb = int(np.flatnonzero(f[fb] == vert)[0])
            rows.append(fa * 3 + ca)
            cols.append(fb * 3 + cb)
    graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(3 * n, 3 * n))
    _, comp = connected_components(graph, directed=False)
    # one new vertex per group of face corners joined across non-seam edges
    _, first, new_index = np.unique(comp, return_index=True, return_inverse=True)
    corners = f.ravel()
    vertices = np.asarray(mesh.vertices)[corners[first]]
    opened = trimesh.Trimesh(vertices, new_index.reshape(n, 3), process=False)
    opened.metadata["original_vertex"] = corners[first]  # opened vertex -> vertex before
    return opened
