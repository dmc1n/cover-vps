"""Drawing covers Rens rejected on shape (8 Oct 2026): shapes read by a person from the drawing
(drawing_given), and the reader fixes behind them (ADR-102)."""

import json
import math
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from coverengine import drawing_given as dg
from coverengine import drawn
from coverengine.drawn import MM

SHAPES = Path(__file__).resolve().parents[2] / "testdata" / "drawing_shapes"
ROLL = 1420.0  # mm: the roll minus a stitch allowance each side


def _pts(pieces: list[drawn.Piece], name: str) -> np.ndarray:
    p = next(p for p in pieces if p.name == name)
    return np.array([q for f in p.faces for q in f])


def _blocchi() -> dict:
    rect = [[0, 0], [180, 0], [180, 120], [0, 120]]
    prof = {"back": [[0, 62], [20, 87], [400, 87]], "front": [[0, 40], [70, 87], [400, 87]],
            "side": [[0, 40], [29.2, 87], [400, 87]]}  # fmt: skip
    return {"shape": "hip", "params": {"plan_cm": rect, "edges": ["back", "side", "front", "side"],
                                       "profiles": prof}}  # fmt: skip


def test_a_hip_top_is_the_lowest_of_the_edges_profiles() -> None:
    """S26: the ends lean in 29.2 cm from 40 to 87 cm, the back has a 20 cm chamfer from 62 cm:
    the back wall's top then comes out 152.66 cm wide at 62 cm, as the drawing writes."""
    pieces = dg.build(_blocchi(), ROLL)
    back = _pts(pieces, "wall-back-1")
    top = back[np.isclose(back[:, 2], 620.0, atol=0.5)]
    assert top[:, 0].max() - top[:, 0].min() == pytest.approx(1526.6, abs=2.0)
    flat = _pts(pieces, "top-1")
    assert np.allclose(flat[:, 2], 870.0)
    assert flat[:, 0].max() - flat[:, 0].min() == pytest.approx(1216.0, abs=1.0)  # 121.6 cm
    assert {p.name for p in pieces} >= {"back-1-1", "front-1-1", "side-1-1", "side-1-2"}


def test_a_hip_profile_that_gets_steeper_again_is_refused() -> None:
    spec = _blocchi()
    spec["params"]["profiles"]["front"] = [[0, 40], [50, 50], [70, 87]]  # a hollow
    with pytest.raises(Exception, match="water"):
        dg.build(spec, ROLL)


def test_a_wide_hip_slope_is_cut_down_its_fall_line_for_the_roll() -> None:
    spec = _blocchi()
    spec["params"]["plan_cm"] = [[0, 0], [300, 0], [300, 220], [0, 220]]
    spec["params"]["profiles"]["front"] = [[0, 40], [170, 87], [400, 87]]
    pieces = dg.build(spec, ROLL)
    slopes = [p for p in pieces if p.name.startswith("front-")]
    assert len(slopes) == 3  # 300 cm along its front: three strips no wider than the roll
    xs = [np.array([q for f in p.faces for q in f])[:, 0] for p in slopes]
    assert all(x.max() - x.min() <= ROLL + 1 for x in xs)


def test_a_level_skirt_cuts_every_wall_at_one_height() -> None:
    """Rens on S43: "keep the skirt height level all round"; the domain rule 13."""
    spec = json.loads((SHAPES / "drawing-s43.json").read_text())
    pieces = dg.build(spec, ROLL, 3000.0, (3.0, 1.0))
    skirt = [p for p in pieces if p.name.startswith("skirt-")]
    assert len(skirt) >= 2  # a closed band needs a seam
    h = spec["params"]["skirt_cm"] * MM
    for p in skirt:
        z = np.array([q for f in p.faces for q in f])[:, 2]
        assert z.min() == pytest.approx(0.0) and z.max() == pytest.approx(h, abs=0.01)
    for p in pieces:
        if p.name.startswith("upper-"):
            assert np.array([q for f in p.faces for q in f])[:, 2].min() >= h - 0.01


def test_a_mirrored_shape_swaps_left_and_right() -> None:
    """S44 is S43 mirrored; 24 and 24B are mirrors of each other."""
    spec = json.loads((SHAPES / "drawing-s19.json").read_text())
    plain = dg.build({**spec, "mirror": False}, ROLL)
    flipped = dg.build({**spec, "mirror": True}, ROLL)
    a = np.vstack([np.array([q for f in p.faces for q in f]) for p in plain])
    b = np.vstack([np.array([q for f in p.faces for q in f]) for p in flipped])
    assert np.allclose(np.sort(a[:, 0]), np.sort(-b[:, 0]))
    assert [p.name for p in plain] == [p.name for p in flipped]


def test_a_twisted_four_cornered_face_is_a_ruled_patch() -> None:
    """D1's sides lean in 22 cm along the whole length while the top falls from 82 to 40 cm."""
    spec = json.loads((SHAPES / "drawing-d1.json").read_text())
    pieces = dg.build(spec, ROLL, 3000.0)
    assert len(pieces) == 11
    side = next(p for p in pieces if p.name == "side-left")
    assert len(side.faces) > 2  # the twisted half is many small flat faces


def test_every_shape_read_by_a_person_builds_and_fits_the_roll() -> None:
    files = sorted(SHAPES.glob("*.json"))
    assert len(files) >= 15
    for f in files:
        spec = json.loads(f.read_text())
        assert spec.get("read"), f"{f.name}: say how it was read"
        pieces = dg.build(spec, ROLL, 3000.0, (3.0, 1.0))
        assert 3 <= len(pieces) <= 40, f.name
        for p in pieces:
            v = np.array([q for fc in p.faces for q in fc])
            assert np.isfinite(v).all() and v[:, 2].min() >= -1e-6, f.name


def test_a_sloped_top_narrower_than_the_roll_across_is_one_piece() -> None:
    """S16: 114 cm across, 250 cm down the slope: one piece, not two."""
    p = {"length_cm": 114.0, "depth_cm": 250.01, "back_height_cm": 87.0,
         "front_height_cm": 51.99, "back_strip_cm": 0, "front_strip_cm": 0}  # fmt: skip
    tops = [x for x in drawn.build("sloped box", p, ROLL) if x.name.startswith("top")]
    assert len(tops) == 1


def test_one_arm_of_an_l_alone_may_come_down() -> None:
    p = {"x_length_cm": 345.44, "y_length_cm": 210.8, "x_arm_depth_cm": 104.1,
         "y_arm_depth_cm": 132.08, "x_back_strip_cm": 27.9, "y_back_strip_cm": 20.3,
         "back_height_cm": 83.8, "front_height_cm": 43.2, "y_end_length_cm": 100.0,
         "end_back_height_cm": 17.8, "end_front_height_cm": 43.2}  # fmt: skip
    names = [x.name for x in drawn.build("L shape", p, ROLL)]
    assert "top-y end slope" in names and "top-x end slope" not in names


def test_a_side_view_alone_is_turned_into_a_round_cover() -> None:
    """U2: a parasol cover drawn from the side, 60 cm wide up to 180 cm, then narrowing to
    47 cm at 244 cm: a cylinder and a cone, closed by a disc."""
    outline = np.array([[0, 0], [60, 0], [60, 180], [53.5, 244], [6.5, 244], [0, 180]])
    prof = dg.side_profile(outline * 0.5, 244.0)  # drawn at half scale: the height sets it
    assert prof[0] == pytest.approx([30.0, 0.0], abs=0.1)
    assert prof[1] == pytest.approx([30.0, 180.0], abs=0.5)
    assert prof[-1] == [0.0, 244.0]
    pieces = dg.revolve({"profile": prof}, ROLL)
    bands = [p for p in pieces if p.name.startswith("band-1-")]
    assert len(bands) == 2  # the cylinder in two gores: 188 cm round, 180 cm high
    assert any(p.name.startswith("top") for p in pieces)


def _lines_pdf(path: Path, angle_deg: float) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    c = pymupdf.Point(300, 100)
    half = math.radians((180 - angle_deg) / 2)
    a = pymupdf.Point(c.x - 250 * math.cos(half), c.y + 250 * math.sin(half))
    b = pymupdf.Point(c.x + 250 * math.cos(half), c.y + 250 * math.sin(half))
    page.draw_line(a, c)
    page.draw_line(c, b)
    page.draw_line(pymupdf.Point(100, 500), pymupdf.Point(160, 500))  # a short line
    doc.save(path)
    return path


def test_the_angle_of_an_angled_sofa_is_read_from_the_top_view(tmp_path: Path) -> None:
    """S21: the back arms meet at 140 degrees, not 90."""
    from coverengine.drawing_vectors import back_angle

    got = back_angle(_lines_pdf(tmp_path / "s21.pdf", 140.0))
    assert got is not None and got["inside_deg"] == pytest.approx(140.0, abs=0.2)
    assert got["bend_deg"] == pytest.approx(40.0, abs=0.2)


def test_the_audit_flags_an_angled_drawing_built_as_a_square_l(tmp_path: Path) -> None:
    from coverengine.audit import drawing_checks

    model = tmp_path / "drawing-s21"
    model.mkdir()
    _lines_pdf(model / "reference.pdf", 140.0)
    (model / "cover.json").write_text(json.dumps({"notes": "Drawing S21: L shape, built ..."}))
    pieces = [{"name": f"p{i}", "quantity": 1} for i in range(10)]
    (model / "finished.json").write_text(json.dumps({"pieces": pieces}))
    checks = {c["check"]: c for c in drawing_checks(model)}
    assert not checks["angle"]["ok"] and checks["piece count"]["ok"]
    (model / "drawing_shape.json").write_text(json.dumps({"shape": "swept"}))
    assert {c["check"]: c for c in drawing_checks(model)}["angle"]["ok"]
    many = [{"name": f"p{i}", "quantity": 1} for i in range(7846)]
    (model / "finished.json").write_text(json.dumps({"pieces": many}))
    assert not {c["check"]: c for c in drawing_checks(model)}["piece count"]["ok"]


def test_heights_are_read_from_upright_sizes_when_the_drawing_does_not_name_them(
    tmp_path: Path,
) -> None:
    """C28 and S32 write "86.4cm", "38.1cm", "99.0cm", "20.3cm" without "Height" or "Depth":
    upright beside the vertical arrows are the heights, slanted ones close by the depth and the
    strip; the top view's own upright 192.4 cm is not a height (S44)."""
    from coverengine.plan_profile import _profile_from_arrows

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((400, 600), "86.4cm", rotate=90)
    page.insert_text((300, 620), "38.1cm", rotate=90)
    page.insert_text((350, 680), "99.0cm")
    page.insert_text((420, 520), "20.3cm")
    page.insert_text((60, 200), "192.4cm", rotate=90)
    page.insert_text((60, 100), "178.4cm Length")
    pdf = tmp_path / "c28.pdf"
    doc.save(pdf)
    got = _profile_from_arrows(pdf, (197.0, 192.4))
    assert got is not None
    assert (got["back"], got["front"], got["depth"], got["strip"]) == (86.4, 38.1, 99.0, 20.3)


def test_the_route_builds_a_shape_a_person_read(tmp_path: Path) -> None:
    """drawing_shape.json in the model: reader "given", built like any route-A cover."""
    from coverengine.drawing_route import build
    from coverengine.params import Registry

    doc = pymupdf.open()
    doc.new_page().insert_text((60, 500), "Cover 52, 4 Air Pockets at Middle")
    pdf = tmp_path / "cover 52 - S16.pdf"
    doc.save(pdf)
    model = tmp_path / "drawing-s16"
    model.mkdir()
    (model / dg.GIVEN_FILE).write_text((SHAPES / "drawing-s16.json").read_text())
    out = build(pdf, model, Registry.load(None).resolve(), code="S16", log=lambda s: None)
    assert out["status"] == "built" and out["reader"] == "given"
    assert out["pieces"] == 5 and out["vents"] == 4
    assert "read by a person" in json.loads((model / "cover.json").read_text())["notes"]


def test_an_angled_sofa_meets_on_the_mitre_with_its_front_inside_the_bend() -> None:
    """S21: two 188 cm arms meeting at 140 degrees, 105 cm deep: the front edge of each arm is
    188 - 105 tan 20 = 149.78 cm, as the drawing writes; nothing folds over at the corner."""
    spec = json.loads((SHAPES / "drawing-s21.json").read_text())
    pieces = dg.build(spec, ROLL)
    front = _pts(pieces, "a-wall-front-1")
    top = front[np.isclose(front[:, 2], 400.1, atol=0.5)]
    run = np.linalg.norm(top[:, :2].max(axis=0) - top[:, :2].min(axis=0))
    assert run == pytest.approx(1497.8, abs=2.0)
    for p in pieces:  # every face has area: no folded or flat-pressed triangles
        for f in p.faces:
            v = np.asarray(f)
            area = 0.5 * np.linalg.norm(np.cross(v[1] - v[0], v[2] - v[0]))
            assert area > 1.0


def test_the_skirt_is_cut_where_one_wall_meets_the_next() -> None:
    """Rens's short vertical lines on S43: the skirt seams where the walls meet, not anywhere."""
    spec = {
        "shape": "box",
        "params": {"length_cm": 100, "depth_cm": 80, "height_cm": 60, "skirt_cm": 20},
    }
    pieces = dg.build(spec, ROLL, 3000.0)
    skirt = [p for p in pieces if p.name.startswith("skirt-")]
    assert len(skirt) == 2  # 3.6 m round: whole walls packed in runs of at most 3 m
    corners = {(0.0, 0.0), (1000.0, 0.0), (1000.0, 800.0), (0.0, 800.0)}
    for p in skirt:
        floor = {(round(q[0], 3), round(q[1], 3)) for f in p.faces for q in f if q[2] == 0}
        assert len(floor & corners) >= 2  # it starts and ends at a corner
    upper = [p for p in pieces if p.name.startswith("upper-")]
    assert len(upper) == 4
    for p in upper:
        assert min(q[2] for f in p.faces for q in f) == pytest.approx(200.0)
