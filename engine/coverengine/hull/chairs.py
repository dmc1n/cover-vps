"""The chairs under a table cover (`hull.chairs`, ADR-044).

Owner, 1 October 2026: a table cover also covers the chairs pushed in along the two long sides
of the table (not the short ends), `hull.chair_room_mm` beyond the table top on each side; a
100 cm wide table gets a cover of 166 cm. The cover is as high as the chairs: one fixed height
per kind of table (dining tables 74 to 77 cm: 87 cm, as the owner's cover T1; low dining and low
bar tables have other chairs). Bar tables, lounge and side tables, fire pits: no chairs.

The program adds a block of chair space beside each long side of the table top, from the floor
to the chair height, and makes the cover round table, chairs and balloons together.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
KINDS = ("dining", "low_dining", "low_bar")
# The table top: the furniture within this distance of its highest point (mm).
TOP_MM = 30.0  # param-ok: geometric tolerance
MM_PER_CM = 10.0  # param-ok: unit conversion
# Names of tables without chairs (lounge, side and coffee tables, fire pits, picnic tables).
NO_CHAIRS = ("lounge", "side", "fire-pit", "picnic", "coffee")


def kind(model_dir: Path, height_mm: float, params: EffectiveParams) -> str:
    """Which chairs a table has: dining | low_dining | low_bar | none."""
    setting = str(params["hull.chairs"])
    if setting != "auto":
        return setting
    name = model_dir.name.lower()
    if "low-bar" in name:
        return "low_bar"
    if "low-dining" in name:
        return "low_dining"
    if "bar" in name or any(w in name for w in NO_CHAIRS):
        return "none"
    lo = float(params["hull.dining_table_min_mm"])  # type: ignore[arg-type]
    hi = float(params["hull.dining_table_max_mm"])  # type: ignore[arg-type]
    if "dining" in name or lo <= height_mm <= hi:
        return "dining"
    return "none"


def chair_space(
    v: Array, model_dir: Path, params: EffectiveParams
) -> tuple[list[Array], dict[str, Any] | None]:
    """The chair blocks beside the long sides of the table top (each as its 8 corners), and the
    report; nothing for a table without chairs."""
    height = float(v[:, 2].max())
    k = kind(model_dir, height, params)
    if k == "none":
        return [], None
    room = float(params["hull.chair_room_mm"])  # type: ignore[arg-type]
    top_z = float(params[f"hull.chair_height_{k}_mm"])  # type: ignore[arg-type]
    hem = float(params["hull.hem_height_mm"])  # type: ignore[arg-type]
    top = v[v[:, 2] > height - TOP_MM]
    lo, hi = top[:, :2].min(axis=0), top[:, :2].max(axis=0)
    long_axis = int(np.argmax(hi - lo))
    across = 1 - long_axis
    blocks = []
    for side in (-1, 1):
        a0 = hi[across] if side > 0 else lo[across] - room
        a1 = a0 + room
        b_lo, b_hi = np.array([0.0, 0.0, hem]), np.array([0.0, 0.0, top_z])
        b_lo[long_axis], b_hi[long_axis] = lo[long_axis], hi[long_axis]
        b_lo[across], b_hi[across] = a0, a1
        corners = np.array(
            [[x, y, z] for x in (b_lo[0], b_hi[0]) for y in (b_lo[1], b_hi[1])
             for z in (b_lo[2], b_hi[2])]
        )  # fmt: skip
        blocks.append(corners)
    width = float(hi[across] - lo[across])
    report = {
        "kind": k,
        "room_mm": room,
        "height_mm": top_z,
        "sides": "long sides",
        "table_mm": [round(float(x)) for x in hi - lo],
        "cover_width_mm": round(width + 2 * room),
        "blocks": [[[round(float(x), 1) for x in c.min(axis=0)],
                    [round(float(x), 1) for x in c.max(axis=0)]] for c in blocks],
    }  # fmt: skip
    return blocks, report
