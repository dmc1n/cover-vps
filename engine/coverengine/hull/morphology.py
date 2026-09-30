"""Ball morphology of a swept solid, done on its height map (ADR-024).

The swept solid is everything below the height map. Dilating, eroding or closing that solid
with a ball of radius r equals grey dilation, erosion or closing of the height map with a
hemisphere of radius r (umbra theorem), which is a 2D operation.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage

Array = NDArray[np.float64]


def hemisphere(radius_mm: float, h: float) -> tuple[Array, NDArray[np.bool_]]:
    """Heights of a hemisphere sampled on the grid, and the disk it stands on."""
    n = int(np.floor(radius_mm / h))
    d = h * np.arange(-n, n + 1)
    r2 = d[:, None] ** 2 + d[None, :] ** 2
    disk = r2 <= radius_mm**2 + 1e-9
    heights = np.sqrt(np.clip(radius_mm**2 - r2, 0.0, None))
    return np.where(disk, heights, 0.0), disk


def dilate(z: Array, radius_mm: float, h: float) -> Array:
    """Height map of the solid grown by a ball of the radius (Minkowski sum)."""
    if radius_mm <= 0:
        return z.copy()
    heights, disk = hemisphere(radius_mm, h)
    return ndimage.grey_dilation(
        z, footprint=disk, structure=heights, mode="constant", cval=-np.inf
    )


def erode(z: Array, radius_mm: float, h: float) -> Array:
    if radius_mm <= 0:
        return z.copy()
    heights, disk = hemisphere(radius_mm, h)
    return ndimage.grey_erosion(z, footprint=disk, structure=heights, mode="constant", cval=-np.inf)


def close(z: Array, radius_mm: float, h: float) -> Array:
    """Fill every gap and recess a ball of the radius cannot enter (bridging)."""
    return erode(dilate(z, radius_mm, h), radius_mm, h)
