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
