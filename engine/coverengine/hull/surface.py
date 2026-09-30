"""Mesh of the swept, bridged and offset solid (ADR-024).

The solid is described by a 3D field g = min(top(x, y) - z, wall(x, y)), positive inside:
- top: the height map after bridging and clearance (grey morphology, `morphology.py`);
- wall: clearance minus the 2D distance to the bridged footprint. That distance is exact
  (point-to-triangle in the floor plane) where the footprint is the model's own, so skirts sit
  at the clearance to within floating point instead of half a grid cell. Where bridging added
  footprint (filled gaps) the grid distance is used.
Marching cubes then gives the surface; the grid is left open at the bottom, below the hem.
"""

from __future__ import annotations

import igl
import numpy as np
import trimesh
from numpy.typing import NDArray
from scipy import ndimage
from skimage.measure import marching_cubes

from coverengine.errors import CoverError
from coverengine.hull.heightmap import HeightMap
from coverengine.hull.morphology import dilate

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]
# Stand-in for "no solid here" in the field (finite, so marching cubes can interpolate).
FAR_MM = 1e7
# Grid layers below the hem, so the later cut at the hem is clean.
BELOW_HEM_CELLS = 2
# Cells beyond the clearance where the top is still defined, so the wall field decides the edge.
BAND_CELLS = 2
# Exact zeros in the field are moved this fraction of a cell outward.
ZERO_NUDGE = 1e-4
# Triangles whose floor-plane area is below this (mm2) are seen edge-on: left to the grid distance.
MIN_FOOTPRINT_AREA_MM2 = 1e-6


def exact_floor_distance(
    vertices: Array, faces: IntArray, xs: Array, ys: Array, where: NDArray[np.bool_]
) -> Array:
    """Distance in the floor plane from grid centres (only where `where`) to the model's
    footprint (0 inside it); +inf elsewhere."""
    out = np.full(where.shape, np.inf)
    flat = np.column_stack([vertices[:, 0], vertices[:, 1], np.zeros(len(vertices))])
    tri = flat[faces]
    area = np.abs(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])[:, 2]) / 2
    keep = faces[area > MIN_FOOTPRINT_AREA_MM2]
    ii, jj = np.nonzero(where)
    if len(keep) == 0 or len(ii) == 0:
        return out
    points = np.column_stack([xs[ii], ys[jj], np.zeros(len(ii))])
    sqr, _, _ = igl.point_mesh_squared_distance(points, flat, keep)
    out[ii, jj] = np.sqrt(np.maximum(sqr, 0.0))
    return out


def solid_field(
    bridged: HeightMap, clearance_mm: float, vertices: Array, faces: IntArray
) -> tuple[Array, Array]:
    """(top, wall) maps of the offset solid, on the bridged height map's grid."""
    h = bridged.h
    top = dilate(bridged.z, clearance_mm, h)
    band = dilate(bridged.z, clearance_mm + BAND_CELLS * h, h)
    top = np.where(np.isfinite(top), top, np.where(np.isfinite(band), band, -FAR_MM))
    grid_distance = ndimage.distance_transform_edt(~bridged.footprint, sampling=h)
    near = grid_distance <= clearance_mm + (BAND_CELLS + 1) * h
    exact = exact_floor_distance(vertices, faces, bridged.xs, bridged.ys, near)
    wall = clearance_mm - np.minimum(exact, grid_distance)
    return top, wall


def mesh_solid(
    top: Array, wall: Array, x0: float, y0: float, h: float, hem_mm: float
) -> trimesh.Trimesh:
    """Marching cubes on min(top - z, wall); open at the bottom, faces pointing outward."""
    covered = (top > hem_mm) & (wall > 0)
    if not covered.any():
        raise CoverError(f"nothing of the model is higher than the hem ({hem_mm:g} mm)")
    z0 = hem_mm - BELOW_HEM_CELLS * h
    highest = float(np.max(top[covered]))
    zs = z0 + h * np.arange(int(np.ceil((highest - z0) / h)) + BELOW_HEM_CELLS + 1)
    field = np.minimum(top[:, :, None] - zs[None, None, :], wall[:, :, None]).astype(np.float32)
    # a value of exactly 0 puts a vertex on a grid point shared by several cubes, which gives
    # zero-area and non-manifold triangles; models in whole mm hit this all the time
    field[field == 0] = -ZERO_NUDGE * h
    # closed at the sides and the top, open at the bottom
    field = np.pad(field, ((1, 1), (1, 1), (0, 1)), constant_values=-FAR_MM)
    verts, faces, _, _ = marching_cubes(field, level=0.0, spacing=(h, h, h))
    verts += np.array([x0 - h, y0 - h, z0])
    # marching cubes winds faces towards the higher values (inside); outward is the reverse
    mesh = trimesh.Trimesh(verts.astype(np.float64), faces[:, ::-1].astype(np.int64), process=True)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    return mesh
