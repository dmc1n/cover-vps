"""Cover surfaces built from the owner's drawings (ADR-046)."""

import numpy as np
import pytest
import trimesh
from coverengine.drawn import build, scene
from coverengine.errors import CoverError

ROLL = 1450.0


def _mesh(pieces):  # type: ignore[no-untyped-def]
    sc = scene(pieces)
    return trimesh.util.concatenate(list(sc.geometry.values()))


def test_a_wide_box_top_is_split_into_strips_the_roll_can_take() -> None:
    pieces = build("box", {"length_cm": 350, "depth_cm": 166, "height_cm": 87}, ROLL)
    assert [p.name for p in pieces][:2] == ["top-1", "top-2"]
    assert len(pieces) == 6


def test_a_sloped_box_has_strip_slope_walls_and_ends() -> None:
    sizes = {"length_cm": 380, "depth_cm": 104, "back_height_cm": 88, "front_height_cm": 61,
             "back_strip_cm": 30}  # fmt: skip
    pieces = build("sloped box", sizes, ROLL)
    assert [p.name for p in pieces] == [
        "top-back strip", "top-slope", "back", "front", "left", "right"]  # fmt: skip
    m = _mesh(pieces)
    assert np.allclose(m.bounds, [[0, -1040, 0], [3800, 0, 880]])  # front is -y


def test_the_pieces_of_a_round_cover_meet_without_gaps() -> None:
    pieces = build("round", {"diameter_cm": 240, "height_cm": 87, "band_pieces": 1}, ROLL)
    assert sum(p.name.startswith("band") for p in pieces) == 2  # a band needs a seam
    assert sum(p.name.startswith("top") for p in pieces) == 2  # 240 cm: two strips
    m = trimesh.Trimesh(_mesh(pieces).vertices, _mesh(pieces).faces, process=True)
    edges = m.edges_sorted
    once = trimesh.grouping.group_rows(edges, require_count=1)
    assert np.allclose(m.vertices[edges[once].ravel(), 2], 0)  # the only open edge is the hem


def test_an_l_shape_whose_sizes_do_not_fit_is_refused() -> None:
    sizes = {"x_length_cm": 100, "y_length_cm": 100, "x_arm_depth_cm": 120,
             "y_arm_depth_cm": 50, "back_height_cm": 80, "front_height_cm": 40}  # fmt: skip
    with pytest.raises(CoverError):
        build("L shape", sizes, ROLL)
