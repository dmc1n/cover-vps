"""The chairs under a table cover (`hull.chairs`, ADR-044).

Owner, 1 October 2026: a table cover also covers the chairs pushed in along the two long sides
of the table (not the short ends), `hull.chair_room_mm` beyond the table top on each side; a
100 cm wide table gets a cover of 166 cm. The cover is as high as the chairs: one fixed height
per kind of table (dining tables 74 to 77 cm: 87 cm, as the owner's cover T1; low dining and low
bar tables have other chairs). Bar tables, lounge and side tables, fire pits: no chairs. A
round table has its chairs all round, the same 33 cm beyond its edge.

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


# A table top is round when it is as wide as long (within ROUND_ASPECT) and fills its circle
# (area within ROUND_FILL of the circle's); the chair ring has RING_POINTS corners.
ROUND_ASPECT = 0.05  # param-ok: geometric tolerance
ROUND_FILL = 0.9  # param-ok: geometric tolerance
RING_POINTS = 48  # param-ok: sampling


def _round(xy: Array) -> bool:
    from scipy.spatial import ConvexHull

    size = np.ptp(xy, axis=0)
    if abs(size[0] - size[1]) > ROUND_ASPECT * size.max():
        return False
    area = float(ConvexHull(xy).volume)
    circle = np.pi * (size.max() / 2) ** 2  # a square of the same width is 1.27 times this
    return bool(ROUND_FILL * circle <= area <= circle / ROUND_FILL)


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
    if _round(top[:, :2]):  # chairs all round a round table (owner, 1 Oct 2026)
        centre = (lo + hi) / 2
        r_table = float(np.max(np.linalg.norm(top[:, :2] - centre, axis=1)))
        r_out = r_table + room
        a = np.linspace(0, 2 * np.pi, RING_POINTS, endpoint=False)
        ring = np.column_stack([centre[0] + r_out * np.cos(a), centre[1] + r_out * np.sin(a)])
        pts = np.vstack([np.column_stack([ring, np.full(len(ring), z)]) for z in (hem, top_z)])
        return [pts], {
            "kind": k,
            "room_mm": room,
            "height_mm": top_z,
            "sides": "all round",
            "table_mm": [round(2 * r_table)] * 2,
            "cover_width_mm": round(2 * r_out),
            "ring": {
                "centre_mm": [round(float(x), 1) for x in centre],
                "table_radius_mm": round(r_table, 1),
                "radius_mm": round(r_out, 1),
                "z_mm": [hem, top_z],
            },
        }
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
