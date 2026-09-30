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
    """Fill every gap and recess a ball of the radius cannot enter (bridging).

    The outline seen from above is closed too: where a gap meets the edge (slat gaps at the end
    of a table), the ball dips a little into its mouth, which on the grid would leave a notch a
    cell deep. Those cells take the height of their neighbours."""
    closed = erode(dilate(z, radius_mm, h), radius_mm, h)
    if radius_mm <= 0:
        return closed
    # closing along straight lines in four directions: a cell with the furniture within the
    # radius on both sides along some line is inside, which fills a gap's mouth flush with
    # the edge (a round closing leaves the mouth open by the ball's dip)
    n = int(np.floor(radius_mm / h))
    footprint = np.isfinite(z)
    outline = np.zeros_like(footprint)
    eye = np.eye(2 * n + 1, dtype=bool)
    for line in (np.ones((2 * n + 1, 1), bool), np.ones((1, 2 * n + 1), bool), eye, eye[::-1]):
        outline |= ndimage.binary_closing(footprint, structure=line, border_value=0)
    missing = outline & ~np.isfinite(closed)
    for _ in range(2 * n + 1):  # at most the radius in cells
        if not missing.any():
            break
        grown = ndimage.grey_dilation(closed, size=(3, 3), mode="constant", cval=-np.inf)
        fill = missing & np.isfinite(grown)
        closed = np.where(fill, grown, closed)
        missing &= ~fill
    return closed


def dilate_cylinder(z: Array, radius_mm: float, h: float) -> Array:
    """Height map of the solid grown by a vertical cylinder of the radius and height: every
    point rises by the radius and the footprint grows by it, with sharp top edges (no rounded
    rim). The gap to a surface sloping at angle a is radius * (cos a + sin a), never less than
    the radius (ADR-027)."""
    if radius_mm <= 0:
        return z.copy()
    _, disk = hemisphere(radius_mm, h)
    grown = ndimage.grey_dilation(z, footprint=disk, mode="constant", cval=-np.inf)
    return grown + radius_mm
