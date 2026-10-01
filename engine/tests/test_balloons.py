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


def test_which_tables_have_chairs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Owner, 1 Oct 2026: dining, low dining and low bar tables; chairs on the long sides."""
    from pathlib import Path

    from coverengine.hull.chairs import chair_space, kind
    from coverengine.params import Registry

    params = Registry.load(None).resolve()
    assert kind(Path("suns-dining-table-erice-240"), 764, params) == "dining"
    assert kind(Path("suns-low-dining-table-grado-170"), 684, params) == "low_dining"
    assert kind(Path("suns-low-bar-table-basta"), 1009, params) == "low_bar"
    assert kind(Path("suns-bar-table-80x80-teak"), 1099, params) == "none"
    assert kind(Path("suns-lounge-pico-lounge-table-big"), 303, params) == "none"
    assert kind(Path("some-table"), 755, params) == "dining"  # by its height
    top = np.array([[x, y, 750.0] for x in (-1200, 1200) for y in (-500, 500)])
    legs = np.array([[x, y, 0.0] for x in (-1100, 1100) for y in (-400, 400)])
    blocks, report = chair_space(np.vstack([top, legs]), tmp_path / "dining-table-x", params)
    assert report is not None and report["cover_width_mm"] == 1000 + 2 * 330
    assert len(blocks) == 2
    for b in blocks:  # along the long sides only, the full length of the table
        assert np.ptp(b[:, 0]) == 2400 and np.ptp(b[:, 1]) == 330 and b[:, 2].max() == 870
