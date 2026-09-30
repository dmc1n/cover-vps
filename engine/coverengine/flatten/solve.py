"""Flattening a panel: a length-preserving map from the 3D panel to the plane (ADR-027).

Start: the conformal map (LSCM, scaled to the true area), which is already exact for
developable panels; if it folds anywhere, the Tutte map (boundary on a circle), which never
folds. Then SLIM iterations on the symmetric Dirichlet energy (or ARAP for comparison), which
pull every triangle towards its true shape without letting any fold, until the energy stops
improving. Finally "up" on the furniture points to +Y and the panel starts at the origin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import igl
import numpy as np
import trimesh
from numpy.typing import NDArray

from coverengine.errors import CoverError

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

# Simplification keeps the outline: weight of boundary edges in the quadric error.
BOUNDARY_WEIGHT = 1000.0  # param-ok: pymeshlab weight
# Symmetric Dirichlet energy of a perfect isometry.
ISOMETRY = 4.0  # param-ok: s1^2 + s1^-2 + s2^2 + s2^-2 at s = 1
# SLIM iterations per convergence check.
ITERATIONS_PER_CHECK = 3
# A panel counts as horizontal (no "up" along the fabric) below this mean height gradient.
FLAT_GRADIENT = 0.1  # param-ok: geometric threshold


@dataclass
class Flat:
    vertices: Array  # 3D
    faces: IntArray
    uv: Array  # 2D, mm
    iterations: int
    energy: float


def _signed_areas(uv: Array, f: IntArray) -> Array:
    e1, e2 = uv[f[:, 1]] - uv[f[:, 0]], uv[f[:, 2]] - uv[f[:, 0]]
    return (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2


def _start(v: Array, f: IntArray) -> Array:
    loop = igl.boundary_loop(f.astype(np.int32))
    if len(loop) < 3:
        raise CoverError("a panel has no boundary; it cannot be flattened")
    far = loop[int(np.argmax(np.linalg.norm(v[loop] - v[loop[0]], axis=1)))]
    b = np.array([loop[0], far], dtype=np.int32)
    bc = np.array([[0.0, 0.0], [float(np.linalg.norm(v[far] - v[loop[0]])), 0.0]])
    area3 = float(
        np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1).sum() / 2
    )
    try:
        uv = np.asarray(igl.lscm(v, f.astype(np.int32), b, bc)[0], dtype=np.float64)
        signed = _signed_areas(uv, f)
        if signed.sum() < 0:
            uv[:, 1] *= -1
            signed = -signed
        if np.all(signed > 0) and np.all(np.isfinite(uv)):
            return uv * math.sqrt(area3 / signed.sum())
    except RuntimeError:
        pass
    circle = igl.map_vertices_to_circle(v, loop.astype(np.int32))
    uv = np.asarray(
        igl.harmonic(v, f.astype(np.int32), loop.astype(np.int32), circle, 1), dtype=np.float64
    )
    signed = _signed_areas(uv, f)
    if signed.sum() < 0:
        uv[:, 1] *= -1
        signed = -signed
    return uv * math.sqrt(area3 / signed.sum())


def _energy(v: Array, f: IntArray, uv: Array) -> float:
    """Area-weighted symmetric Dirichlet energy (4 for a perfect isometry)."""
    s1, s2, area = singular_values(v, f, uv)
    return float(((s1**2 + s1**-2 + s2**2 + s2**-2) * area).sum() / area.sum())


def singular_values(v: Array, f: IntArray, uv: Array) -> tuple[Array, Array, Array]:
    """Per triangle: the principal stretches of the 3D -> 2D map (larger first), and the 3D area."""
    p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    x = e1 / np.linalg.norm(e1, axis=1, keepdims=True)
    n = np.cross(e1, e2)
    area = np.linalg.norm(n, axis=1) / 2
    y = np.cross(n / np.linalg.norm(n, axis=1, keepdims=True), x)
    # 3D triangle in its own plane, and the same triangle in the flat pattern
    local = np.stack(
        [
            np.stack([(e1 * x).sum(1), (e1 * y).sum(1)], 1),
            np.stack([(e2 * x).sum(1), (e2 * y).sum(1)], 1),
        ],
        2,
    )
    flat = np.stack([uv[f[:, 1]] - uv[f[:, 0]], uv[f[:, 2]] - uv[f[:, 0]]], 2)
    jac = flat @ np.linalg.inv(local)
    s = np.linalg.svd(jac, compute_uv=False)
    return s[:, 0], s[:, 1], area


def simplify(mesh: trimesh.Trimesh, max_triangles: int) -> trimesh.Trimesh:
    """Fewer triangles for a very dense panel, with its outline kept exactly (a pattern needs
    no more detail; flattening time grows with the triangle count)."""
    if len(mesh.faces) <= max_triangles:
        return mesh
    import pymeshlab

    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(np.asarray(mesh.vertices), np.asarray(mesh.faces)))
    ms.meshing_decimation_quadric_edge_collapse(
        targetfacenum=int(max_triangles),
        preserveboundary=True,
        boundaryweight=BOUNDARY_WEIGHT,
        preservenormal=True,
        preservetopology=True,
        planarquadric=True,
    )
    out = ms.current_mesh()
    return trimesh.Trimesh(out.vertex_matrix(), out.face_matrix(), process=False)


def flatten(
    mesh: trimesh.Trimesh,
    solver: str,
    max_iterations: int,
    tolerance: float,
    max_triangles: int | None = None,
) -> Flat:
    if max_triangles is not None:
        mesh = simplify(mesh, max_triangles)
    v = np.asarray(mesh.vertices, dtype=np.float64)
    f = np.asarray(mesh.faces, dtype=np.int64)
    uv = _start(v, f)
    energy = {"slim": igl.MappingEnergyType.SYMMETRIC_DIRICHLET, "arap": igl.MappingEnergyType.ARAP}
    if solver not in energy:
        raise CoverError(f"unknown flatten.solver {solver!r}; use slim or arap")
    done, last = 0, _energy(v, f, uv)
    if last - ISOMETRY <= tolerance * ISOMETRY:  # the start is already exact (developable)
        return Flat(v, f, _orient(v, f, uv), 0, last)
    data = igl.slim_precompute(
        v, f.astype(np.int32), uv, energy[solver], np.zeros(0, np.int32), np.zeros((0, 2))
    )
    while done < max_iterations:
        step = min(ITERATIONS_PER_CHECK, max_iterations - done)
        uv = np.asarray(igl.slim_solve(data, step), dtype=np.float64)[:, :2]
        done += step
        now = _energy(v, f, uv)
        if abs(last - now) <= tolerance * max(last, 1.0):
            last = now
            break
        last = now
    return Flat(v, f, _orient(v, f, uv), done, last)


def _orient(v: Array, f: IntArray, uv: Array) -> Array:
    """Rotate so the direction that is up on the furniture points to +Y (for a horizontal
    panel: the direction towards the back), and move the panel to start at the origin."""

    def gradient(values: Array) -> Array:
        e1, e2 = uv[f[:, 1]] - uv[f[:, 0]], uv[f[:, 2]] - uv[f[:, 0]]
        d = np.stack([values[f[:, 1]] - values[f[:, 0]], values[f[:, 2]] - values[f[:, 0]]], 1)
        m = np.stack([e1, e2], 1)  # rows: edges in 2D
        g = np.linalg.solve(m, d[:, :, None])[:, :, 0]
        area = np.abs(_signed_areas(uv, f))
        return (g * area[:, None]).sum(0) / area.sum()

    g = gradient(v[:, 2])
    if np.linalg.norm(g) < FLAT_GRADIENT:
        g = gradient(v[:, 1])
    angle = math.atan2(g[1], g[0])
    turn = math.pi / 2 - angle
    rot = np.array([[math.cos(turn), -math.sin(turn)], [math.sin(turn), math.cos(turn)]])
    out = uv @ rot.T
    return out - out.min(axis=0)
