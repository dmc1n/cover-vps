"""The cover built from the drawing's own views (ADR-075)."""

from pathlib import Path

import numpy as np
import pymupdf
import pytest
from coverengine import drawing_solid as ds
from coverengine import drawing_views as dv


def _view(kind: str, pts: list[tuple[float, float]], scale: float = 1.0) -> dv.View:
    v = dv.View(0, (0, 0, 1, 1), np.array(pts, dtype=float), kind)
    v.meta["scale"] = scale
    return v


TRAPEZOID = [(0, 0), (150, 0), (190, 110), (0, 110)]  # a plan, cm (scale 1)
PROFILE = [(0, 0), (110, 0), (110, 60), (80, 84), (0, 84)]  # a side: back 84, front 60


def test_a_plan_and_a_side_make_the_solid_a_drawer_built() -> None:
    read = {"views": [_view("plan", TRAPEZOID), _view("side", PROFILE)]}
    cands = ds.candidates(read)
    assert cands  # the side seen from either end
    ext = sorted(np.round(cands[0]["solid"].extents / 10, 1))
    assert ext == pytest.approx(sorted([190.0, 110.0, 84.0]), abs=1.0)


def test_the_3d_view_picks_the_right_way_round() -> None:
    """Built one way, drawn isometrically: that way fits (almost) exactly, the mirror less."""
    read = {"views": [_view("plan", TRAPEZOID), _view("side", PROFILE)]}
    cands = ds.candidates(read)
    truth = cands[0]["solid"]
    sil = ds._iso_silhouette(truth, 45.0)
    iso = _view("iso", list(np.asarray(sil.exterior.coords)[:-1]))
    scores = [ds.iso_fit(c["solid"], iso)[0] for c in cands]
    assert scores[0] > 0.99 and min(scores) < scores[0]


def test_the_pieces_are_split_at_the_folds_and_a_ring_is_cut() -> None:
    read = {"views": [_view("plan", TRAPEZOID), _view("side", PROFILE)]}
    solid = ds.candidates(read)[0]["solid"]
    names = sorted(p.name.rsplit("-", 1)[0] for p in ds.pieces(solid, 1450.0))
    assert names.count("wall") == 4 and "top" in names and "slope" in names
    # a lens straight up: one top, its curved band cut in two
    t = np.linspace(0, 2 * np.pi, 90, endpoint=False)
    lens = [(90 * np.cos(a), 45 * np.sin(a)) for a in t]
    solid = ds._from(_view("plan", lens), [], 38.1)[0]["solid"]
    names = sorted(p.name.rsplit("-", 1)[0] for p in ds.pieces(solid, 1450.0))
    assert names == ["top", "wall", "wall"]


def test_a_piece_wider_than_the_roll_is_cut_across() -> None:
    sq = [(0, 0), (300, 0), (300, 250), (0, 250)]
    solid = ds._from(_view("plan", sq), [], 40.0)[0]["solid"]
    tops = [p for p in ds.pieces(solid, 1450.0) if p.name.startswith("top")]
    assert len(tops) == 2  # 250 cm across: two strips


def _arrow(shape: pymupdf.Shape, tip: tuple[float, float], d: tuple[float, float]) -> None:
    tx, ty = tip
    bx, by = tx - 5 * d[0], ty - 5 * d[1]
    nx, ny = -d[1] * 1.6, d[0] * 1.6
    shape.draw_polyline([(tx, ty), (bx + nx, by + ny), (bx - nx, by - ny), (tx, ty)])


def test_a_size_is_linked_to_its_arrows(tmp_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    sh = page.new_shape()
    sh.draw_line((100, 300), (300, 300))
    _arrow(sh, (100, 300), (-1, 0))
    _arrow(sh, (300, 300), (1, 0))
    sh.finish(color=(0, 0, 0), fill=(0, 0, 0))
    sh.commit()
    page.insert_text((180, 292), "150.0cm")
    doc.save(tmp_path / "d.pdf")
    (d,) = dv.dimensions(tmp_path / "d.pdf")
    assert d.value_cm == 150.0 and d.length_pt == pytest.approx(200.0, abs=0.5)


def test_inches_count_when_no_cm_is_written(tmp_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 100), "74.80in")
    page.insert_text((60, 300), "45.0cm 17.7in")
    doc.save(tmp_path / "w.pdf")
    assert dv.written_cm(tmp_path / "w.pdf") == [45.0, 190.0]
