"""Exact clearance check against the model, and repair where the hull comes too close.

The grid, the smoothing and the remeshing each move the surface a little. Here the true
distance from the hull to the model's triangles is measured at every vertex, face centre and
edge midpoint. Where a sample is closer than the clearance, the vertices involved move straight
away from the nearest model point until it is not. Vertices on the hem stay at hem height.
"""

from __future__ import annotations

from dataclasses import dataclass

import igl
import numpy as np
import trimesh
from numpy.typing import NDArray

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]
# Push this much past the clearance, so float rounding cannot leave a sample just inside it.
MARGIN_MM = 1e-3


@dataclass
class Clearance:
    min_mm: float  # over vertices, face centres and edge midpoints
    mean_vertex_mm: float
    vertices_moved: int
    max_move_mm: float


def _samples(mesh: trimesh.Trimesh) -> tuple[Array, list[IntArray]]:
    """Vertices, face centres and edge midpoints, with the vertices each sample depends on."""
    v, f = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    edges = np.asarray(mesh.edges_unique)
    points = np.vstack([v, v[f].mean(axis=1), v[edges].mean(axis=1)])
    owners = [np.arange(len(v))[:, None], f, edges]
    return points, owners


def distances(mesh: trimesh.Trimesh, model_v: Array, model_f: IntArray) -> tuple[Array, Array]:
    points, _ = _samples(mesh)
    sqr, _, closest = igl.point_mesh_squared_distance(points, model_v, model_f)
    return np.sqrt(np.maximum(sqr, 0.0)), closest


def enforce(
    mesh: trimesh.Trimesh,
    model_v: Array,
    model_f: IntArray,
    clearance_mm: float,
    passes: int,
    hem_vertices: IntArray,
) -> Clearance:
    """Move vertices outward until every sample is at least the clearance from the model."""
    v = np.asarray(mesh.vertices, dtype=np.float64).copy()
    start = v.copy()
    on_hem = np.zeros(len(v), dtype=bool)
    on_hem[hem_vertices] = True
    for _ in range(passes):
        mesh.vertices = v
        points, owners = _samples(mesh)
        sqr, _, closest = igl.point_mesh_squared_distance(points, model_v, model_f)
        d = np.sqrt(np.maximum(sqr, 0.0))
        short = d < clearance_mm
        if not short.any():
            break
        away = points - closest
        length = np.linalg.norm(away, axis=1, keepdims=True)
        normals = np.vstack(
            [
                mesh.vertex_normals,
                mesh.face_normals,
                mesh.vertex_normals[mesh.edges_unique].mean(axis=1),
            ]
        )
        direction = np.where(length > MARGIN_MM, away / np.maximum(length, MARGIN_MM), normals)
        push = direction * (clearance_mm - d + MARGIN_MM)[:, None]
        # each vertex takes the largest push asked of it by any sample it belongs to
        move = np.zeros_like(v)
        size = np.zeros(len(v))
        offset = 0
        for own in owners:
            n = len(own)
            rows = np.flatnonzero(short[offset : offset + n])
            for col in range(own.shape[1]):
                idx = own[rows, col]
                amount = np.linalg.norm(push[offset + rows], axis=1)
                better = amount > size[idx]
                size[idx[better]] = amount[better]
                move[idx[better]] = push[offset + rows[better]]
            offset += n
        move[on_hem, 2] = 0.0
        v = v + move
    mesh.vertices = v
    d, _ = distances(mesh, model_v, model_f)
    shift = np.linalg.norm(v - start, axis=1)
    return Clearance(
        min_mm=float(d.min()),
        mean_vertex_mm=float(d[: len(v)].mean()),
        vertices_moved=int((shift > 0).sum()),
        max_move_mm=float(shift.max()) if len(shift) else 0.0,
    )
