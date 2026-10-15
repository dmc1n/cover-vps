"""QUESTIONS 59 (Rens, 15 Oct 2026): an arrangement's roof also slopes down to the sides
("ja, ook naar de zijkanten"), `arrange.side_slopes`: only to a member's outside sides (never
into a neighbour, so no valley between two members), both outside sides alike, water still runs
off (rule 12); off, the roofs slope to the front only as before."""

from __future__ import annotations

import numpy as np
import pytest
from coverengine.hull import plan as hp
from coverengine.params import Registry

NumPts = np.ndarray


def _box(x0: float, x1: float, y0: float, y1: float, z: float) -> NumPts:
    xs, ys = np.linspace(x0, x1, 9), np.linspace(y0, y1, 9)
    gx, gy = np.meshgrid(xs, ys)
    return np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, z)])


def _sofa(x0: float) -> NumPts:
    """A 2000 x 900 seat 450 high (front at y 0) with a back 850 high in its middle only:
    the roof has room to slope down to both ends."""
    return np.vstack([
        _box(x0, x0 + 2000, 0, 900, 450),
        _box(x0 + 900, x0 + 1100, 700, 900, 850),
    ])  # fmt: skip


def _rect(x0: float) -> list[list[float]]:
    return [[x0, 0.0], [x0 + 2000, 0.0], [x0 + 2000, 900.0], [x0, 900.0]]


def _sides(cover: hp.PlanCover) -> tuple[bool, bool]:
    """Does the top slope down to -x anywhere, and to +x? (walls excluded)"""
    n = np.asarray(cover.mesh.face_normals)
    top = n[:, 2] > hp.UPRIGHT_NZ
    return bool((n[top, 0] < -0.05).any()), bool((n[top, 0] > 0.05).any())


@pytest.fixture(scope="module")
def params() -> object:
    return Registry.load().resolve()


def test_the_company_default_has_side_slopes_on_for_arrangements(params: object) -> None:
    assert params["arrange.side_slopes"] is True  # type: ignore[index]
    assert params["arrange.top_slopes"] == "front"  # type: ignore[index] # no slopes to the back


def test_one_sofa_slopes_to_both_sides_alike(params: object) -> None:
    on = hp.build(_sofa(0), [_rect(0)], "follow", 0.0, params, side_slopes=True)  # type: ignore[arg-type]
    off = hp.build(_sofa(0), [_rect(0)], "follow", 0.0, params, side_slopes=False)  # type: ignore[arg-type]
    assert _sides(on) == (True, True)  # both ends, mirrored
    assert _sides(off) == (False, False)  # as before: front only
    assert on.report["side_slopes"] and on.report["drainage"]["drains"]
    assert on.report["top_faces"][0] > off.report["top_faces"][0]
    # the sides keep a wall at least as high as the front's (no slope down to the hem), and
    # the plan stays the member's rectangle plus the clearance
    v = np.asarray(on.mesh.vertices)
    lo, hi = on.mesh.bounds
    front = v[np.abs(v[:, 1] - lo[1]) < 1.0][:, 2].max()
    for x in (lo[0], hi[0]):
        assert v[np.abs(v[:, 0] - x) < 1.0][:, 2].max() >= front - 1.0
    assert (hi - lo)[:2] == pytest.approx((off.mesh.bounds[1] - off.mesh.bounds[0])[:2], abs=1.0)
    # the mirror image: the side faces are each other's mirror
    n = np.asarray(on.mesh.face_normals)
    left = n[(n[:, 2] > hp.UPRIGHT_NZ) & (n[:, 0] < -0.05)][0]
    right = n[(n[:, 2] > hp.UPRIGHT_NZ) & (n[:, 0] > 0.05)][0]
    assert left[0] == pytest.approx(-right[0], abs=1e-6)
    assert left[2] == pytest.approx(right[2], abs=1e-6)


def test_two_sofas_side_by_side_slope_only_to_their_outside_ends(params: object) -> None:
    pts = np.vstack([_sofa(0), _sofa(2000)])
    cover = hp.build(pts, [_rect(0), _rect(2000)], "follow", 0.0, params, side_slopes=True)  # type: ignore[arg-type]
    assert cover.report["drainage"]["drains"]  # rule 12: no valley at the join
    n = np.asarray(cover.mesh.face_normals)
    c = np.asarray(cover.mesh.triangles_center)
    top = n[:, 2] > hp.UPRIGHT_NZ
    to_left, to_right = top & (n[:, 0] < -0.05), top & (n[:, 0] > 0.05)
    assert to_left.any() and to_right.any()
    assert (c[to_left, 0] < 1000).all()  # the left sofa's outside end only
    assert (c[to_right, 0] > 3000).all()  # the right sofa's outside end only
    # the cover stays 4000 + 2 clearances wide, walls straight down
    clear = float(params["hull.clearance_mm"])  # type: ignore[index]
    lo, hi = cover.mesh.bounds
    assert hi[0] - lo[0] == pytest.approx(4000 + 2 * clear, abs=1.0)


def test_a_side_against_a_neighbour_is_not_outside() -> None:
    from shapely.geometry import Polygon

    m = hp.Member(Polygon(_rect(0)), 0.0, _sofa(0))
    sides = hp.outside_sides(m, [Polygon(_rect(2000))], 60.0)
    assert [float(d[0]) for d in sides] == [-1.0]  # only -x: the neighbour stands at +x
    assert len(hp.outside_sides(m, [], 60.0)) == 2
