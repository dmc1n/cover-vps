"""ADR-068: free-form covers from the drawings, a cross-section swept along a path."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from coverengine import drawn, swept
from coverengine.errors import CoverError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import drawing_swept as ds  # noqa: E402

QUARTER = {
    "path": [{"arc": 176.57, "angle": 90}],
    "profile": [[0, 62.94], [20.33, 87.93], [60.2, 87.93], [81.8, 87.93], [120, 40.01]],
}


def test_a_quarter_ring_has_the_drawings_arc_lengths() -> None:
    """S24: the outer arc 277.35 cm, the inner 88.86 cm, 120 cm apart: a quarter ring."""
    ls = ds.lengths(QUARTER)
    assert abs(ls["line 0 along the cover"] - 277.35) < 0.5
    assert abs(ls["line 4 along the cover"] - 88.86) < 0.5
    assert len(drawn.build("swept", QUARTER, 1450)) == 4 + 2 + 2  # 4 top bands, 2 walls, 2 ends


def test_a_hip_stops_the_lines_on_top_early_at_both_ends() -> None:
    p = {**QUARTER, "line_lengths_cm": [None, 185.55, 138.21, 112.6, None]}
    ls = ds.lengths(p)
    for j, want in ((1, 185.55), (2, 138.21), (3, 112.6)):
        assert abs(ls[f"line {j} along the cover"] - want) < 0.6
    names = [pc.name for pc in drawn.build("swept", p, 1450)]
    assert "start-hip" in names and "end-hip" in names


def test_a_piece_too_wide_both_ways_gets_a_seam_a_long_one_does_not() -> None:
    long_top = {"path": [{"line": 400}], "profile": [[0, 80], [130, 40]]}  # 1.36 m across: 1 piece
    assert sum(pc.name.startswith("top") for pc in drawn.build("swept", long_top, 1450)) == 1
    deep = {"path": [{"line": 400}], "profile": [[0, 80], [200, 40]]}  # 2 m deep, 4 m long
    assert sum(pc.name.startswith("top") for pc in drawn.build("swept", deep, 1450)) == 2
    short = {"path": [{"line": 120}], "profile": [[0, 80], [195, 40]]}  # 1.95 m deep, 1.2 m long
    assert sum(pc.name.startswith("top") for pc in drawn.build("swept", short, 1450)) == 1
    capped = {**deep, "max_piece_mm": 2500}  # a length limit only when one is set
    tops = [pc for pc in drawn.build("swept", capped, 1450) if pc.name.startswith("top")]
    assert len(tops) == 4
    for pc in tops:
        assert np.ptp(np.array([v for f in pc.faces for v in f])[:, 0]) <= 2500 + 1


def test_a_u_shape_with_round_ends() -> None:
    p = {
        "path": [{"line": 100}, {"arc": 120, "angle": 180}, {"line": 100}],
        "profile": [[0, 86], [20, 86], [99, 38]],
        "start_end": "round",
        "end_end": "round",
    }
    names = [pc.name for pc in drawn.build("swept", p, 1450)]
    assert "start-round-top" in names and "end-round-wall" in names
    assert abs(ds.lengths(p)["line 0 along the cover"] - (200 + math.pi * 120)) < 0.5


def test_a_bad_path_is_said_so() -> None:
    with pytest.raises(CoverError):
        swept.build({"path": [{"bend": 3}], "profile": [[0, 1], [2, 1]]}, 1450, 2950)


def test_a_bend_tighter_than_the_cover_is_deep_is_refused() -> None:
    """C26: the inside of a U cannot fold over itself; the AI is told and corrects it."""
    p = {
        "path": [{"line": 50}, {"arc": 60, "angle": 180}, {"line": 50}],
        "profile": [[0, 86], [99, 38]],
    }
    with pytest.raises(CoverError, match="cross itself"):
        swept.build(p, 1450, math.inf)
