"""Units, up axis, front direction and ground placement (ADR-007, ADR-022).

Canonical frame: mm, right-handed, Z up, lowest point at z = 0, bounding box centred on x = y = 0,
front of the furniture toward -Y. Unit heuristics only warn; they never change the unit.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from coverengine.errors import CoverError

Array = NDArray[np.float64]

# Millimetres per unit.
UNIT_MM: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,  # param-ok: unit conversion
    "m": 1000.0,
    "inch": 25.4,
    "ft": 304.8,
}

# Units offered for --units and in warnings (ft only appears when a CAD file declares it).
SUGGESTED_UNITS = ("mm", "cm", "m", "inch")

# STEP and IGES unit names as OpenCascade reports them -> our unit ids.
_UNIT_NAMES = {
    "mm": "mm",
    "millimetre": "mm",
    "millimeter": "mm",
    "cm": "cm",
    "centimetre": "cm",
    "centimeter": "cm",
    "m": "m",
    "metre": "m",
    "meter": "m",
    "in": "inch",
    "inch": "inch",
    "ft": "ft",
    "foot": "ft",
}


def unit_id(name: str) -> str | None:
    """Our unit id for a unit name found in a file, or None if unknown."""
    return _UNIT_NAMES.get(name.strip().strip(".").lower())


# Rotation taking the given file axis to +Z, the smallest turn that does so (proper rotations).
_UP: dict[str, list[list[float]]] = {
    "z": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "y": [[1, 0, 0], [0, 0, -1], [0, 1, 0]],  # glTF: +Z (front) becomes -Y
    "x": [[0, 0, -1], [0, 1, 0], [1, 0, 0]],
    "-z": [[1, 0, 0], [0, -1, 0], [0, 0, -1]],
    "-y": [[1, 0, 0], [0, 0, 1], [0, -1, 0]],
    "-x": [[0, 0, 1], [0, 1, 0], [-1, 0, 0]],
}

# Rotation about Z taking the given horizontal direction to -Y.
_FRONT: dict[str, list[list[float]]] = {
    "-y": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "y": [[-1, 0, 0], [0, -1, 0], [0, 0, 1]],
    "x": [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
    "-x": [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
}


def rotation(up_axis: str, front: str) -> Array:
    if up_axis not in _UP:
        raise CoverError(f"unknown up axis {up_axis!r}; use one of {' | '.join(_UP)}")
    if front not in _FRONT:
        raise CoverError(f"unknown front {front!r}; use one of {' | '.join(_FRONT)}")
    return np.array(_FRONT[front], dtype=np.float64) @ np.array(_UP[up_axis], dtype=np.float64)


@dataclass
class Placement:
    scale: float  # file values -> mm
    rotation: Array  # 3x3
    translation_mm: Array  # applied after scale and rotation

    def matrix(self) -> Array:
        m = np.eye(4)
        m[:3, :3] = self.rotation * self.scale
        m[:3, 3] = self.translation_mm
        return m


def ground_translation(bounds: tuple[Array, Array]) -> Array:
    """Translation that puts the lowest point on z = 0 and centres the box on x = y = 0."""
    lo, hi = bounds
    return np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])


def plausibility_warning(
    size_mm: Sequence[float],
    units_used: str,
    min_mm: float,
    max_mm: float,
    mm_per_unit: float | None = None,
) -> str | None:
    """Warn when the model's largest dimension is implausible, naming the units that would fit.

    `mm_per_unit` is what one number in the file became (default: the size of `units_used`).
    """
    largest = max(size_mm)
    if min_mm <= largest <= max_mm:
        return None
    here = mm_per_unit if mm_per_unit is not None else UNIT_MM[units_used]
    fits = [
        u
        for u in SUGGESTED_UNITS
        if not math.isclose(UNIT_MM[u], here) and min_mm <= largest * UNIT_MM[u] / here <= max_mm
    ]
    dims = " x ".join(f"{s:.0f}" for s in size_mm)
    what = "small" if largest < min_mm else "large"
    msg = f"model is {dims} mm with units {units_used}, which looks too {what} for furniture"
    for u in fits:
        alt = " x ".join(f"{s * UNIT_MM[u] / here:.0f}" for s in size_mm)
        msg += f"; in {u} it would be {alt} mm (--units {u})"
    return msg
