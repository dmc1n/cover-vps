"""Fewer pieces on drawing covers: joined where there is no crease (ADR-076)."""

import numpy as np
import trimesh
from coverengine.drawn_merge import merge


def _quad(a, b, c, d):  # type: ignore[no-untyped-def]
    return trimesh.Trimesh(np.array([a, b, c, d], float), [[0, 1, 2], [0, 2, 3]])


def test_strips_of_one_flat_top_become_one_piece_but_a_crease_stays() -> None:
    """S43: a flat top cut into 4 strips (from profile points cm apart) plus a slope."""
    parts = [(f"top-{i}", _quad((i * 100, 0, 800), ((i + 1) * 100, 0, 800),
                                ((i + 1) * 100, 300, 800), (i * 100, 300, 800)))
             for i in range(4)]  # fmt: skip
    # a slope down from the strip's front edge (y = 0) at 25°: a real crease
    drop = 300 * np.tan(np.radians(25))
    parts.append(("slope", _quad((0, -300, 800 - drop), (400, -300, 800 - drop), (400, 0, 800),
                                 (0, 0, 800))))  # fmt: skip
    out = merge(parts, 1420.0, 15.0, 1.0)
    assert len(out) == 2
    areas = sorted(m.area for _, m in out)  # the slope's drop is rounded to the weld grid
    assert areas[0] == 120000 and abs(areas[1] - 400 * 300 / np.cos(np.radians(25))) < 5


def test_a_piece_is_never_joined_past_the_roll() -> None:
    parts = [(f"top-{i}", _quad((0, i * 1000, 800), (900, i * 1000, 800),
                                (900, (i + 1) * 1000, 800), (0, (i + 1) * 1000, 800)))
             for i in range(2)]  # fmt: skip
    assert len(merge(parts, 800.0, 15.0, 1.0)) == 2  # 900 wide in its narrowest: over the roll
