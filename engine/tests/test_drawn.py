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


def _open_above_hem(pieces) -> int:  # type: ignore[no-untyped-def]
    m = trimesh.Trimesh(_mesh(pieces).vertices, _mesh(pieces).faces, process=True)
    once = trimesh.grouping.group_rows(m.edges_sorted, require_count=1)
    return int((m.vertices[m.edges_sorted[once].ravel(), 2] > 1).sum())


def test_an_l_shape_with_sloping_arm_ends_is_closed_and_comes_down_at_the_ends() -> None:
    sizes = {
        "x_length_cm": 344,
        "y_length_cm": 268,
        "x_arm_depth_cm": 85,
        "y_arm_depth_cm": 85,
        "x_back_strip_cm": 25,
        "y_back_strip_cm": 25,
        "back_height_cm": 90,
        "front_height_cm": 43,
        "end_length_cm": 40,
        "end_back_height_cm": 26.4,
        "end_front_height_cm": 17,
    }  # the owner's C2
    pieces = build("L shape", sizes, ROLL)
    names = [p.name for p in pieces]
    ends = {"top-x end strip", "top-x end slope", "top-y end strip", "top-y end slope"}
    assert ends <= set(names)
    assert _open_above_hem(pieces) == 0  # the pieces meet point to point
    end = next(p for p in pieces if p.name == "end-x")
    assert max(z for f in end.faces for _, _, z in f) == pytest.approx(264)


def test_an_l_whose_second_arm_is_only_a_corner_end_is_built() -> None:
    sizes = {
        "x_length_cm": 380,
        "y_length_cm": 110,
        "x_arm_depth_cm": 110,
        "y_arm_depth_cm": 110,
        "x_back_strip_cm": 35,
        "y_back_strip_cm": 35,
        "back_height_cm": 82,
        "front_height_cm": 37,
    }  # the owner's S18
    pieces = build("L shape", sizes, ROLL)
    assert "front-y" not in [p.name for p in pieces]  # no front on a corner end
    assert _open_above_hem(pieces) == 0


def _kidney(n: int = 60) -> list[list[float]]:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = 1 + 0.25 * np.cos(2 * t)  # a waist: concave on two sides
    return [[float(60 * r[i] * np.cos(t[i])), float(40 * r[i] * np.sin(t[i]))] for i in range(n)]


@pytest.mark.parametrize("roll", [ROLL, 500.0])
def test_a_free_outline_is_its_own_top_and_the_pieces_meet_without_gaps(roll: float) -> None:
    """S45 (ADR-072): a kidney seen from above, straight up; never a box."""
    pieces = build("outline", {"outline_cm": _kidney(), "height_cm": 45}, roll)
    tops = [p for p in pieces if p.name.startswith("top")]
    assert sum(p.name.startswith("band") for p in pieces) == 2
    assert len(tops) == (1 if roll == ROLL else 2)  # about 80 cm across: split on a narrow roll
    raw = _mesh(pieces)
    m = trimesh.Trimesh(raw.vertices, raw.faces, process=True)
    once = trimesh.grouping.group_rows(m.edges_sorted, require_count=1)
    assert np.allclose(m.vertices[m.edges_sorted[once].ravel(), 2], 0)
    top_area = sum(trimesh.Trimesh(*_tri(p)).area for p in tops)
    import shapely

    assert top_area == pytest.approx(shapely.Polygon(np.array(_kidney()) * 10).area, rel=0.002)


def _tri(p):  # type: ignore[no-untyped-def]
    from coverengine.drawn import _poly

    v, f = _poly(p.faces[0])
    return v, f


def test_an_outline_that_crosses_itself_is_refused() -> None:
    with pytest.raises(CoverError):
        build("outline", {"outline_cm": [[0, 0], [100, 100], [100, 0], [0, 100]],
                          "height_cm": 40}, ROLL)  # fmt: skip
