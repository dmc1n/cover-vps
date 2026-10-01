"""Balloons under table covers (ADR-040)."""

import numpy as np
from coverengine.hull.balloons import points_layouts


def test_balloons_spread_evenly_along_a_long_table() -> None:
    rows = points_layouts(
        np.array([-1700.0, -500.0]), np.array([1700.0, 500.0]), (520, 510, 206), 12
    )
    by_count = {r["balloons"]: r for r in rows}
    assert by_count[1]["centres"] == [(0.0, 0.0)]
    three = by_count[3]
    assert three["grid"] == [3, 1]  # in one row along the length
    xs = [c[0] for c in three["centres"]]
    assert np.allclose(np.diff(xs), 3400 / 3)
    assert max(r["balloons"] for r in rows) <= 8
    # never more balloons side by side than fit
    assert all(r["grid"][0] <= 6 and r["grid"][1] <= 1 for r in rows)
