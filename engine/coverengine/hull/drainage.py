"""Does water run off the cover top? (CLAUDE.md rule 12)

Two ways water can stay on a cover:
- a hollow: a spot lower than everything around it. Found by filling the top from its edge
  (priority flood): wherever the filled level is above the surface, water would collect.
- a flat area: a patch too flat for water to run off (slope below `hull.min_slope_deg`). Thin
  flat strips such as the crest of a backrest, and flat spots near the edge, shed water; only
  patches at least `hull.flat_patch_mm` across and not at the edge count.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage

Array = NDArray[np.float64]
Mask = NDArray[np.bool_]

# A hollow deeper than this (mm) holds water.
HOLLOW_MM = 1.0


@dataclass
class Drainage:
    drains: bool
    hollow_area_mm2: float
    flat_area_mm2: float
    worst_xy_mm: tuple[float, float] | None  # centre of the largest problem area
    flat: Mask  # cells of the flat patches (for supports)
    problem: Mask  # cells where water would stay: hollows and flat patches

    def summary(self) -> dict[str, object]:
        return {
            "drains": self.drains,
            "hollow_area_mm2": round(self.hollow_area_mm2, 1),
            "flat_area_mm2": round(self.flat_area_mm2, 1),
            "worst_location_mm": None
            if self.worst_xy_mm is None
            else [round(self.worst_xy_mm[0], 1), round(self.worst_xy_mm[1], 1)],
        }


def filled(z: Array, inside: Mask) -> Array:
    """Water level after rain: the surface raised to the lowest spill height (priority flood)."""
    level = np.where(inside, np.inf, -np.inf)
    edge = inside & ~ndimage.binary_erosion(inside, border_value=0)
    heap = [(float(z[i, j]), int(i), int(j)) for i, j in zip(*np.nonzero(edge), strict=True)]
    heapq.heapify(heap)
    for _, i, j in heap:
        level[i, j] = z[i, j]
    nx, ny = z.shape
    while heap:
        h, i, j = heapq.heappop(heap)
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if 0 <= a < nx and 0 <= b < ny and inside[a, b] and level[a, b] == np.inf:
                level[a, b] = max(z[a, b], h)
                heapq.heappush(heap, (level[a, b], a, b))
    return level


def _disk(radius_cells: int) -> Mask:
    r = np.arange(-radius_cells, radius_cells + 1)
    return (r[:, None] ** 2 + r[None, :] ** 2) <= radius_cells**2


def flat_patches(z: Array, inside: Mask, h: float, min_slope_deg: float, patch_mm: float) -> Mask:
    """Flat patches at least `patch_mm` across and not at the edge."""
    zf = np.where(inside, z, 0.0)
    gx, gy = np.gradient(zf, h)
    slope = np.hypot(gx, gy)
    core = ndimage.binary_erosion(inside, iterations=2)  # gradients at the edge are one-sided
    flat = core & (slope < math.tan(math.radians(min_slope_deg)))
    radius = max(int(round(patch_mm / 2 / h)), 1)
    away_from_edge = ndimage.distance_transform_edt(inside) * h > patch_mm / 2
    seeds = ndimage.binary_erosion(flat, structure=_disk(radius)) & away_from_edge
    return ndimage.binary_dilation(seeds, structure=_disk(radius)) & flat


def check(
    z: Array, inside: Mask, xs: Array, ys: Array, min_slope_deg: float, patch_mm: float
) -> Drainage:
    h = float(xs[1] - xs[0])
    hollow = inside & (filled(z, inside) - np.where(inside, z, 0.0) > HOLLOW_MM)
    flat = flat_patches(z, inside, h, min_slope_deg, patch_mm)
    problem = hollow | flat
    worst = None
    if problem.any():
        labels, n = ndimage.label(problem)
        sizes = ndimage.sum(problem, labels, range(1, n + 1))
        ci, cj = ndimage.center_of_mass(problem, labels, int(np.argmax(sizes)) + 1)
        worst = (float(xs[0] + ci * h), float(ys[0] + cj * h))
    return Drainage(
        drains=not problem.any(),
        hollow_area_mm2=float(hollow.sum()) * h * h,
        flat_area_mm2=float(flat.sum()) * h * h,
        worst_xy_mm=worst,
        flat=flat,
        problem=problem,
    )
