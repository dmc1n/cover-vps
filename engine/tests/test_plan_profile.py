"""A cover from the exact top view and a profile from the back edge (ADR-084, C27)."""

import numpy as np
import pytest
import shapely
from coverengine import plan_profile as pp


def _c_shape() -> dict:  # type: ignore[type-arg]
    """A C: a half ring 99 cm deep, outer radius 250 cm, back strip 20 cm at 86 cm, front 38."""
    outer = [(250 * np.cos(t), 250 * np.sin(t)) for t in np.linspace(0, np.pi, 60)]
    inner = [(151 * np.cos(t), 151 * np.sin(t)) for t in np.linspace(np.pi, 0, 60)]
    return {"plan_cm": outer + inner, "back_cm": outer,
            "profile": [[0, 86.0], [20.0, 86.0], [99.0, 38.0]],
            "seams_at_cm": [250 * np.pi / 3, 250 * 2 * np.pi / 3]}  # fmt: skip


def test_the_top_follows_the_profile_from_the_back_edge() -> None:
    pieces = pp.build(_c_shape())
    names = sorted(p.name.split("-")[0] for p in pieces)
    assert names.count("top") == 3 and names.count("slope") == 3  # cut at the two seams
    assert names.count("back") == 3 and names.count("front") == 3
    pts = np.array([q for p in pieces if p.name.startswith(("top", "slope"))
                    for f in p.faces for q in f])  # fmt: skip
    assert pts[:, 2].max() == pytest.approx(860, abs=1)  # the back strip, mm
    assert pts[:, 2].min() == pytest.approx(380, abs=5)  # the front edge
    r = np.hypot(pts[:, 0], pts[:, 1]) / 10
    strip = pts[r > 232, 2]  # within 20 cm of the back: flat at 86 cm
    assert np.allclose(strip, 860, atol=1)


def test_the_walls_stand_on_the_outline_up_to_the_top() -> None:
    pieces = pp.build(_c_shape())
    back = [q for p in pieces if p.name.startswith("back") for f in p.faces for q in f]
    assert max(z for _, _, z in back) == pytest.approx(860, abs=1)
    front = [q for p in pieces if p.name.startswith("front") for f in p.faces for q in f]
    assert min(z for _, _, z in front if z > 0) <= 400


def _nearly_closed_c() -> dict:  # type: ignore[type-arg]
    """A C open to the right (30°..330°): a seam square to the back at the top (90°) points
    straight at the bottom arm (270°)."""
    t = np.radians(np.linspace(30, 330, 120))
    outer = [(250 * np.cos(a), 250 * np.sin(a)) for a in t]
    inner = [(151 * np.cos(a), 151 * np.sin(a)) for a in t[::-1]]
    at = 250 * np.radians(90 - 30)
    return {"plan_cm": outer + inner, "back_cm": outer,
            "profile": [[0, 86.0], [20.0, 86.0], [99.0, 38.0]], "seams_at_cm": [at]}  # fmt: skip


def _area(piece: pp.Piece) -> float:
    tot = 0.0
    for f in piece.faces:
        q = np.asarray(f, float)
        for i in range(1, len(q) - 1):
            tot += float(np.linalg.norm(np.cross(q[i] - q[0], q[i + 1] - q[0]))) / 2
    return tot


def test_a_drawn_seam_crosses_its_own_section_only() -> None:
    """C27 (ADR-097): a seam line reaching on cut the opposite arm, one piece too many."""
    pieces = pp.build(_nearly_closed_c())
    names = [p.name.split("-")[0] for p in pieces]
    assert names.count("top") == 2 and names.count("slope") == 2


def test_the_slope_reaches_the_front_height_all_along_the_front_edge() -> None:
    """Measured by the distance from the back alone, the slope ran out flat where the cover is
    deeper than drawn (the noses) and could not lie flat (C26 4.4 %, ADR-097)."""
    pieces = pp.build(_nearly_closed_c())
    pts = np.array([q for p in pieces if p.name.startswith("slope") for f in p.faces for q in f])
    r = np.hypot(pts[:, 0], pts[:, 1]) / 10
    front = pts[np.abs(r - 151) < 0.5, 2]
    assert len(front) > 20 and np.allclose(front, 380, atol=6)
    assert pts[:, 2].min() >= 380 - 6  # never below the front height


def test_the_hidden_back_wall_is_one_band_cut_only_for_its_length() -> None:
    shape = _c_shape()
    per_section = pp.build(shape)
    banded = pp.build(shape, wall_max_mm=6000.0)
    backs = [p for p in banded if p.name.startswith("back")]
    assert len([p for p in per_section if p.name.startswith("back")]) == 3
    assert len(backs) == 2  # the half ring's outer wall is ~7.9 m: two runs of at most 6 m
    for p in backs:
        run = sum(float(np.hypot(f[1][0] - f[0][0], f[1][1] - f[0][1])) for f in p.faces)
        assert run <= 6000.0
    total = lambda ps: sum(_area(p) for p in ps if p.name.startswith("back"))  # noqa: E731
    assert total(banded) == pytest.approx(total(per_section), rel=1e-6)
    rest = lambda ps: [p.name for p in ps if not p.name.startswith("back")]  # noqa: E731
    assert rest(banded) == rest(per_section)


def test_the_back_edge_is_the_outside_of_the_c() -> None:
    plan = shapely.Polygon(_c_shape()["plan_cm"])
    back = pp.back_edge(plan)
    # the outer arc, and the two square ends that also lie on the outside (as C27's noses do);
    # never the inner arc
    assert 250 * np.pi <= back.length <= 250 * np.pi + 2 * 99 + 1


def test_written_lengths_trust_the_shape_and_find_a_typo(monkeypatch: pytest.MonkeyPatch) -> None:
    """C27: 235.1 cm is written beside 96.5 in (= 245.1 cm); the measured 245 matches the inch."""
    written = [{"cm": 178.2, "in_cm": 178.2}, {"cm": 235.1, "in_cm": 245.1},
               {"cm": 166.2, "in_cm": 166.2}]  # fmt: skip
    monkeypatch.setattr(pp, "_written_lengths", lambda pdf: written)
    got = pp.check_lengths(None, {"seams_at_cm": [0, 178.7, 423.7, 590.0]})
    assert got["trusted"] and got["matched"] == 3
    assert got["typos"] == [{"written_cm": 235.1, "inch_gives_cm": 245.1, "measured_cm": 245.0}]
