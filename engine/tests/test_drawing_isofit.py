"""Heights fitted to the drawing's 3D view (phase 4 of the drawings plan, ADR-094): C8 and its
kind, a corner sofa drawn as a top view and a 3D picture only."""

import io
from pathlib import Path

import numpy as np
import pymupdf
import pytest
import shapely
from coverengine import drawing_isofit as fi
from coverengine.params import Registry
from PIL import Image
from scipy import ndimage

P = Registry.load(None).resolve()
ROLL_CM = 148.0
TRUE = fi.Heights(back=84.0, front=44.0, strip=30.0, end=31.0, hip=40.0)  # C8 as drawn
SIZES = [13.0, 30.0, 31.0, 40.0, 44.0, 84.0, 92.0, 282.0, 357.0]  # all C8 writes (13: a drop)


def _l_plan(arm: float = 357.0, other: float = 282.0, depth: float = 92.0) -> shapely.Polygon:
    """An L seen from above (cm, y towards the back): the outside along the top and the left."""
    return shapely.Polygon([(0, 0), (arm, 0), (arm, -depth), (depth, -depth), (depth, -other),
                            (0, -other)])  # fmt: skip


def _footprint() -> fi.Footprint:
    (fp,) = fi.footprints(_l_plan(), float(P["drawing.isofit_end_share"]))  # type: ignore[arg-type]
    return fp


def test_the_back_of_an_l_is_its_outside_and_its_arms_have_ends() -> None:
    fp = _footprint()
    assert sorted(round(x) for x in fp.back_cm) == [282, 357]
    assert len(fp.ends) == 2 and fp.depth == pytest.approx(92.0)


def test_a_straight_sofa_can_have_its_back_on_either_long_side() -> None:
    fps = fi.footprints(shapely.box(0, 0, 380, 110), float(P["drawing.isofit_end_share"]))  # type: ignore[arg-type]
    assert len(fps) == 2
    assert all(fp.back_cm == [380.0] and len(fp.ends) == 2 for fp in fps)
    assert all(fp.depth == pytest.approx(110.0) for fp in fps)


def test_the_top_falls_from_the_back_to_the_front_and_to_the_arms_ends() -> None:
    """Water runs off: going to the front, or along an arm to its end, the top never rises."""
    fp = _footprint()
    z = lambda x, y: float(fi.height(fp, TRUE, np.array([[x, y]]))[0])  # noqa: E731
    assert z(200, -1) == pytest.approx(84.0)  # the back
    assert z(200, -20) == pytest.approx(84.0)  # the flat strip
    assert z(200, -92) == pytest.approx(44.0)  # the front
    assert z(357, -46) == pytest.approx(31.0)  # an arm's end
    across = [z(200, -y) for y in np.linspace(0, 92, 40)]
    along = [z(x, -60) for x in np.linspace(200, 357, 40)]
    assert all(b <= a + 1e-9 for a, b in zip(across, across[1:], strict=False))
    assert all(b <= a + 1e-9 for a, b in zip(along, along[1:], strict=False))


def test_the_strip_can_fall_towards_the_seat_so_no_water_stays() -> None:
    best = {"fp": _footprint(), "heights": TRUE}
    flat = fi.build(best, ROLL_CM)
    fall = fi.build(best, ROLL_CM, strip_fall_deg=6.0)
    edge = lambda ps: min(  # noqa: E731 - the strip's lowest point, mm
        q[2] for p in ps if p.name.startswith("strip") for f in p.faces for q in f
    )
    assert edge(flat) == pytest.approx(840.0)
    assert edge(fall) == pytest.approx(840.0 - 300 * np.tan(np.radians(6.0)), abs=1.0)


def test_the_pieces_meet_at_the_corner_and_fit_the_roll() -> None:
    fp = _footprint()
    lay = fi.layout(fp, TRUE.strip, TRUE.hip, True, ROLL_CM)
    pieces = fi.pieces(fp, TRUE, lay)
    kinds = sorted({p.name.split("-")[0] for p in pieces})
    assert kinds == ["back", "end", "front", "hip", "slope", "strip"]
    # the corner seam splits the strip and the slope where the arms meet
    assert sum(p.name.startswith("strip") for p in pieces) == 2
    assert sum(p.name.startswith("slope") for p in pieces) == 2
    for p in pieces:
        pts = np.array([q for f in p.faces for q in f])
        c = pts - pts.mean(axis=0)
        spans = np.ptp(c @ np.linalg.svd(c, full_matrices=False)[2][:2].T, axis=0)
        assert spans.min() <= ROLL_CM * 10  # mm
    allz = np.array([q[2] for p in pieces for f in p.faces for q in f])
    assert allz.min() == pytest.approx(0.0) and allz.max() == pytest.approx(840.0)


def _picture_of(h: fi.Heights, px_cm: float = 1.2) -> fi.Picture:
    """The cover drawn as its own 3D view, as the drawing's picture would be."""
    fp = _footprint()
    v, f, _ = fi.surface(fp, h, fi.layout(fp, h.strip, h.hip, h.end is not None, ROLL_CM))
    blank = np.zeros((520, 640), dtype=bool)
    probe = fi.Picture(blank, blank, px_cm, np.array([320.0, 260.0]), 0, blank.astype(float))
    m, c = fi.render(v, f, probe, 315.0, float(P["drawing.isofit_crease_deg"]))  # type: ignore[arg-type]
    rr, cc = np.nonzero(m)
    return fi.Picture(m, c, px_cm, np.array([cc.mean(), rr.mean()]), 0,
                      ndimage.distance_transform_edt(~c))  # fmt: skip


def test_the_heights_are_found_among_the_written_sizes() -> None:
    res = fi.fit_picture(_l_plan(), SIZES, _picture_of(TRUE), P, ROLL_CM)
    best = res["fit"]
    assert best["heights"] == TRUE
    assert best["azimuth"] == 315.0
    assert best["iou"] > 0.99 and best["crease"] > 0.9
    assert best["lengths"]["matched"] == 3 and not fi.why_not(best, P)


def test_a_flat_block_does_not_lie_on_a_sofas_picture() -> None:
    """The views reader's block (straight up to the back height) covers the silhouette well but
    its creases are not the sofa's: the fit scores it below the sofa."""
    fp = _footprint()
    pic = _picture_of(TRUE)
    p = fi._params(P)
    ev = fi._Eval(fp, pic, p, ROLL_CM, {}, {})
    block, sofa = ev(fi.Heights(84.0, 84.0), 315.0), ev(TRUE, 315.0)
    assert block[1] > 0.9  # its silhouette alone would pass
    assert block[2] < sofa[2] - 0.3 and block[0] < sofa[0]


def test_a_fit_is_refused_on_its_silhouette_its_creases_or_unwritten_lengths() -> None:
    ok = {"iou": 0.95, "crease": 0.8, "lengths": {"matched": 3, "of": 3}}
    assert not fi.why_not(ok, P)
    assert "3D view only" in fi.why_not({**ok, "iou": 0.8}, P)[0]
    assert "creases" in fi.why_not({**ok, "crease": 0.3}, P)[0]
    assert "lengths" in fi.why_not({**ok, "lengths": {"matched": 1, "of": 3}}, P)[0]


def test_a_written_size_gives_one_height_only() -> None:
    assert fi._distinct(TRUE)
    assert not fi._distinct(fi.Heights(86.4, 40.6, 40.6))  # C31: the front height is no strip
    assert fi._distinct(fi.Heights(84.0, 84.0))  # a flat top


# --- a whole drawing: a top view and a 3D picture, nothing else (C8's sheet, simplified) --------

SCALE = 2.0  # cm per point on the test sheet


def _png(rgb: np.ndarray, mask: np.ndarray) -> bytes:
    rgba = np.dstack([rgb, np.where(mask, 255, 0).astype(np.uint8)])
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _sofa_pdf(path: Path) -> Path:
    from skimage.draw import polygon

    doc = pymupdf.open()
    page = doc.new_page()
    px_cm = 0.5  # the pictures' pixels
    plan = np.asarray(_l_plan().exterior.coords)
    cols, rows = int(357 / px_cm) + 1, int(282 / px_cm) + 1
    rr, cc = polygon(-plan[:, 1] / px_cm, plan[:, 0] / px_cm, (rows, cols))
    top = np.zeros((rows, cols), dtype=bool)
    top[rr, cc] = True
    grey = np.full((rows, cols, 3), 150, dtype=np.uint8)
    page.insert_image(pymupdf.Rect(40, 40, 40 + cols * px_cm / SCALE, 40 + rows * px_cm / SCALE),
                      stream=_png(grey, top))  # fmt: skip
    fp = _footprint()
    v, f, _ = fi.surface(fp, TRUE, fi.layout(fp, TRUE.strip, TRUE.hip, True, ROLL_CM))
    rgb, mask = fi.shaded(v, f, 315.0, px_cm, float(P["drawing.isofit_crease_deg"]))  # type: ignore[arg-type]
    h, w = mask.shape
    page.insert_image(pymupdf.Rect(250, 330, 250 + w * px_cm / SCALE, 330 + h * px_cm / SCALE),
                      stream=_png(rgb, mask))  # fmt: skip
    # the top view's two size arrows give the sheet's scale
    x1, y1 = 40 + 357 / SCALE, 40 + 282 / SCALE
    sh = page.new_shape()
    sh.draw_line((40, 30), (x1, 30))
    sh.draw_line((30, 40), (30, y1))
    for tip, d in (
        ((40, 30), (-1, 0)),
        ((x1, 30), (1, 0)),
        ((30, 40), (0, -1)),
        ((30, y1), (0, 1)),
    ):
        tx, ty = tip
        bx, by = tx - 5 * d[0], ty - 5 * d[1]
        nx, ny = -d[1] * 1.6, d[0] * 1.6
        sh.draw_polyline([(tx, ty), (bx + nx, by + ny), (bx - nx, by - ny), (tx, ty)])
    sh.finish(color=(0, 0, 0), fill=(0, 0, 0))
    sh.commit()
    page.insert_text((110, 26), "357 cm")
    page.insert_text((2, 110), "282 cm")
    for i, t in enumerate(["92 cm", "84 cm", "44 cm", "30 cm", "31 cm", "40 cm", "13 cm",
                           "7 Air Pockets"]):  # fmt: skip
        page.insert_text((60, 600 + 18 * i), t)
    doc.save(path)
    return path


def test_route_a_builds_a_corner_sofa_from_its_top_view_and_3d_picture(tmp_path: Path) -> None:
    from coverengine.drawing_route import read

    res = read(_sofa_pdf(tmp_path / "cover 20 - C8.pdf"), P)
    assert res["status"] == "built" and res["reader"] == "isofit", res["reasons"]
    got = res["info"]["isofit"]
    assert (got["back_cm"], got["front_cm"], got["strip_cm"]) == (84.0, 44.0, 30.0)
    assert (got["end_cm"], got["hip_cm"]) == (31.0, 40.0)
    assert got["score"] > got["views_shape_score"]  # better than the block straight up
    names = {p.name.split("-")[0] for p in res["pieces"]}
    assert {"strip", "slope", "hip", "back", "front", "end"} <= names
