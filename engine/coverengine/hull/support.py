"""Support under the cover for flat tops (tables): a balloon that lifts the fabric into a tent.

The balloon is a dome of radius `hull.support_radius_mm` centred on the largest flat patch of
the unsupported cover. Its height is `hull.support_height_mm`, or, when that is 0, the lowest
height at which the whole top sheds water (found by bisection on the drainage check).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage

from coverengine.hull import drainage
from coverengine.hull.tension import concave_envelope

Array = NDArray[np.float64]
Mask = NDArray[np.bool_]

# Bisection steps for the automatic height (resolution: range / 2^steps).
BISECTION_STEPS = 12


@dataclass
class Support:
    kind: str
    centre_mm: tuple[float, float]
    radius_mm: float
    height_mm: float  # above the cover top it lifts
    automatic: bool


def dome(
    obstacle: Array,
    xs: Array,
    ys: Array,
    centre: tuple[float, float],
    radius: float,
    base: float,
    height: float,
) -> Array:
    r2 = (xs[:, None] - centre[0]) ** 2 + (ys[None, :] - centre[1]) ** 2
    cap = np.where(r2 <= radius**2, base + height * (1 - r2 / radius**2), -np.inf)
    return np.maximum(obstacle, cap)


def balloon(
    obstacle: Array,
    inside: Mask,
    xs: Array,
    ys: Array,
    radius_mm: float,
    height_mm: float,
    min_slope_deg: float,
    patch_mm: float,
) -> tuple[Array, Support | None]:
    """The tensioned top with a balloon under the largest flat patch (unchanged if none)."""
    h = float(xs[1] - xs[0])
    top = concave_envelope(obstacle, inside, xs, ys)
    flat = drainage.flat_patches(top, inside, h, min_slope_deg, patch_mm)
    if not flat.any():
        return top, None
    labels, n = ndimage.label(flat)
    sizes = ndimage.sum(flat, labels, range(1, n + 1))
    ci, cj = ndimage.center_of_mass(flat, labels, int(np.argmax(sizes)) + 1)
    centre = (float(xs[0] + ci * h), float(ys[0] + cj * h))
    base = float(top[int(round(ci)), int(round(cj))])

    def lifted(height: float) -> Array:
        return concave_envelope(
            dome(obstacle, xs, ys, centre, radius_mm, base, height), inside, xs, ys
        )

    if height_mm > 0:
        return lifted(height_mm), Support("balloon", centre, radius_mm, height_mm, False)
    span = float(min(np.ptp(xs[np.any(inside, axis=1)]), np.ptp(ys[np.any(inside, axis=0)])))
    lo, hi = 0.0, span / 2
    for _ in range(BISECTION_STEPS):
        mid = (lo + hi) / 2
        if drainage.flat_patches(lifted(mid), inside, h, min_slope_deg, patch_mm).any():
            lo = mid
        else:
            hi = mid
    return lifted(hi), Support("balloon", centre, radius_mm, hi, True)
