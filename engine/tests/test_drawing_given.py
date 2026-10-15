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
    """Rens on S43 (8 Oct): "keep the skirt height level all round"; the domain rule 13 (S44's
    shape of 8 Oct, a swept shape with `skirt_cm`)."""
    spec = {"shape": "swept", "mirror": True, "params": {
        "path": [{"line": 41.24}, {"arc": 167.1, "angle": 61.835}],
        "profile": [[0, 88.01], [33.07, 88.01], [141.86, 40.64]],
        "seams_cm": [55.4, 110.8, 166.2],
        "start_end": "square", "end_end": "round", "end_angle_deg": 0,
        "skirt_cm": 40.64}}  # fmt: skip
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
    assert len(pieces) == 9
    side = next(p for p in pieces if p.name == "side-left")
    assert len(side.faces) > 2  # the twisted half is many small flat faces


@pytest.mark.parametrize("code", ["d1", "d2"])
def test_a_flat_wall_drawn_in_one_piece_is_one_piece(code: str) -> None:
    """Rens, Desk 9 Oct 2026, D1 and D2: "crossed-out panels reduced to one panel": the front
    wall is one flat face from the hem to the top on the drawing's front view, so no level skirt
    seam across it; the 18 cm seam stays on the sides, where the wall meets the leaning strip."""
    spec = json.loads((SHAPES / f"drawing-{code}.json").read_text())
    assert "skirt_cm" not in spec["params"]
    pieces = dg.build(spec, ROLL, 3000.0)
    for name in ("wall-front", "wall-back"):
        v = _pts(pieces, name)
        assert v[:, 2].min() == pytest.approx(0.0) and v[:, 2].max() >= 400.0 - 1e-6
        assert np.ptp(v[:, 1]) < 1e-6  # one plane
    assert _pts(pieces, "wall-left")[:, 2].max() == pytest.approx(180.0)


def test_s43_seams_as_drawn() -> None:
    """Rens, Desk 14 Oct 2026, S43 and S44: "seams beter volgen zoals op tekening". The strip
    ends on a line A-B, the leaning back band runs on round the nose's back to C on the rim, the
    slope runs on to D on the front of the nose, the walls are cut below C and D; every wall
    40.64 cm high (the level seam of 9 Oct kept). S44 is the mirror. Desk 15 Oct 2026: "rare knik
    in paneel top 1 wijzigen. Ook de front skirts terugbrengen naar 1 paneel": the nose top has no
    fold inside it, and the front wall is one piece from the straight end round to D."""
    spec = json.loads((SHAPES / "drawing-s43.json").read_text())
    assert spec["shape"] == "faces"
    pieces = dg.build(spec, ROLL, 3000.0)
    names = {p.name for p in pieces}
    assert names == {"back-band", "strip", "slope", "nose", "wall-end", "wall-back",
                     "wall-front", "wall-nose"}  # fmt: skip
    pts = {p.name: _pts(pieces, p.name) for p in pieces}

    def shared(a: str, b: str) -> np.ndarray:
        ka = {tuple(np.round(q, 1)) for q in pts[a]}
        return np.array([q for q in {tuple(np.round(q, 1)) for q in pts[b]} if q in ka])

    sd = shared("slope", "nose")  # the line A-D: from the strip's inner end to the nose's front
    lo, hi = sd[sd[:, 2].argmin()], sd[sd[:, 2].argmax()]
    assert hi[2] == pytest.approx(880.1, abs=0.1) and lo[2] == pytest.approx(406.4, abs=0.1)
    assert hi[:2] == pytest.approx([1485, 1037], abs=15) and lo[:2] == pytest.approx(
        [1196, 1923], abs=15
    )
    bc = shared("back-band", "nose")  # B-C: the band's end, down to the rim behind the nose
    assert bc[:, 2].min() == pytest.approx(406.4, abs=0.1) and bc[:, 2].max() == pytest.approx(
        880.1, abs=0.1
    )
    for name, p in pts.items():
        if name.startswith("wall-") and name != "wall-end":
            assert p[:, 2].max() == pytest.approx(406.4, abs=0.1) and p[:, 2].min() == 0.0
    # the wall seams below D and C
    assert len(shared("wall-front", "wall-nose")) and len(shared("wall-nose", "wall-back"))
    assert len(shared("wall-front", "wall-end"))  # the front skirt runs from the straight end
    # no fold inside the nose top: neighbouring facets meet at no more than the rim's steps
    nose = next(p for p in pieces if p.name == "nose")
    n = [np.cross(np.subtract(f[1], f[0]), np.subtract(f[2], f[0])) for f in nose.faces]
    n = [v / np.linalg.norm(v) for v in n]
    folds = [
        math.degrees(math.acos(min(1.0, float(a @ b)))) for a, b in zip(n, n[1:], strict=False)
    ]
    assert max(folds) < 5.0
    mirrored = dg.build(json.loads((SHAPES / "drawing-s44.json").read_text()), ROLL, 3000.0)
    assert {p.name for p in mirrored} == names
    m = _pts(mirrored, "nose")
    assert sorted(np.round(-m[:, 0], 1)) == sorted(np.round(pts["nose"][:, 0], 1))


def test_s32_back_strip_is_one_piece() -> None:
    """Rens, Desk 9 Oct 2026, S32: the struck-through strip pieces one panel (`strip_whole`)."""
    spec = json.loads((SHAPES / "drawing-s32.json").read_text())
    whole = dg.build(spec, ROLL, 3000.0)
    cut = dg.build({**spec, "params": {**spec["params"], "strip_whole": False}}, ROLL, 3000.0)
    strip = lambda ps: [p for p in ps if p.name.startswith("top-")]  # noqa: E731
    assert len(strip(cut)) - len(strip(whole)) == 3  # four strip pieces became one
    z = np.vstack([np.array([q for f in p.faces for q in f]) for p in strip(whole)])
    assert z[:, 2].max() == pytest.approx(863.6, abs=0.1)


def test_every_shape_read_by_a_person_builds_and_fits_the_roll() -> None:
    files = sorted(SHAPES.glob("*.json"))
    assert len(files) >= 15
    for f in files:
        spec = json.loads(f.read_text())
        assert spec.get("read"), f"{f.name}: say how it was read"
        pieces = dg.build(spec, ROLL, 3000.0, (3.0, 1.0))
        assert 2 <= len(pieces) <= 40, f.name  # a flat bag: two (U1, U2)
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


def test_a_side_view_alone_is_a_flat_bag_of_the_drawn_panel() -> None:
    """U2: a parasol cover drawn from the side, 60 cm wide up to 180 cm, then narrowing to
    47 cm at 244 cm. Rens, 14 Oct 2026: "just twice the panel on the drawing, stitched all round
    except the bottom line" (no longer the round cover turned from it, ADR-102)."""
    outline = np.array([[0, 0.4], [60, 0], [60, 180], [53.5, 244], [6.5, 244], [0, 180]])
    panel = dg.side_outline(outline * 0.5, 244.0)  # drawn at half scale: the height sets it
    pts = np.array(panel)
    assert pts[:, 1].max() == pytest.approx(244.0) and pts[:, 0].max() == pytest.approx(
        60.0, abs=0.2
    )
    assert (pts[:, 1] == 0.0).sum() == 2  # one level open bottom line
    front, back = dg.flat_bag({"outline_cm": panel})
    assert len(front.faces) == len(back.faces)
    v = _pts([front], front.name)
    assert np.ptp(v[:, 2]) == pytest.approx(2440.0, abs=1.0)


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


def test_the_audit_flags_a_rebuild_that_lost_a_decided_vent_count(tmp_path: Path) -> None:
    """C24/C25 (Rens, 9 Oct 2026): 9 vents decided by a person; a cover asking for the
    reader's 7 fails the audit."""
    from coverengine.audit import drawing_checks

    model = tmp_path / "drawing-c24"
    model.mkdir()
    (model / "drawing_corrections.json").write_text(json.dumps({"vents_total": 9}))
    cover = {"parameters": {"features": {"vents_total": 7}}}
    (model / "cover.json").write_text(json.dumps(cover))
    assert not {c["check"]: c for c in drawing_checks(model)}["decided vents"]["ok"]
    cover["parameters"]["features"]["vents_total"] = 9
    (model / "cover.json").write_text(json.dumps(cover))
    assert {c["check"]: c for c in drawing_checks(model)}["decided vents"]["ok"]


def test_the_audit_flags_a_top_view_off_its_written_sizes(tmp_path: Path) -> None:
    """C4 (Rens, 9 Oct 2026): "the main size 343.6 cm becomes 344 cm". A fitted cover whose
    back runs 344.4 and 343.6 cm where the drawing writes 344 fails; the depth is not a written
    edge (C29's reaches past its 109.3 cm ends) and is left out."""
    from coverengine.audit import drawing_checks

    model = tmp_path / "drawing-c4"
    model.mkdir()
    lengths = {"lengths_cm": [344.4, 343.6, 85.3], "written_cm": [344.0, 344.0, 85.0]}
    read = {"reader": "isofit", "isofit": {"lengths": lengths}}
    (model / "drawing_read.json").write_text(json.dumps(read))
    check = {c["check"]: c for c in drawing_checks(model)}["written sizes"]
    assert not check["ok"] and "343.6 cm where the drawing writes 344" in check["detail"]
    lengths.update(lengths_cm=[344.0, 344.0, 87.0])
    (model / "drawing_read.json").write_text(json.dumps(read))
    assert {c["check"]: c for c in drawing_checks(model)}["written sizes"]["ok"]


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
    assert spec["params"]["bend_deg"] == 30.0  # Rens's choice (9 Oct, QUESTIONS 6)
    spec["params"]["bend_deg"] = 40.0  # the drawing's own lines, which its front edge belongs to
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


def test_a_free_round_front_follows_the_slope() -> None:
    """D5 (Rens, 9 Oct 2026: "the outline does not match the drawing at all"): a 198 x 94 cm
    plan with a half round of radius 99 cm, one slope from the strip to the 40.01 cm front, the
    round front without a profile of its own (`free`): its rim is 40.01 cm in the middle and
    62.35 cm where the leaning end faces stop, 110.22 cm from the back; the back wall's top is
    193.99 cm wide and the strip 177.98 cm, as the drawing writes."""
    spec = json.loads((SHAPES / "drawing-d5.json").read_text())
    pieces = dg.build(spec, ROLL)
    rim = _pts(pieces, "wall-round-3")
    top = rim[rim[:, 2] > 1.0]
    assert top[:, 1].max() == pytest.approx(1930.0, abs=1.0)  # 193 cm deep
    assert top[np.argmax(top[:, 1]), 2] == pytest.approx(400.1, abs=1.0)
    assert top[:, 2].max() == pytest.approx(623.5, abs=3.0)
    side = _pts(pieces, "side-1-1")
    assert side[:, 1].max() == pytest.approx(1102.2, abs=5.0)
    back = _pts(pieces, "wall-back-1")
    high = back[np.isclose(back[:, 2], 640.1, atol=0.5)]
    assert high[:, 0].max() - high[:, 0].min() == pytest.approx(1939.9, abs=2.0)
    strip = _pts(pieces, "top-1")
    assert strip[:, 0].max() - strip[:, 0].min() == pytest.approx(1779.8, abs=2.0)


def test_arms_followed_and_the_seat_spanned_by_one_slope() -> None:
    """S20 and S48 (Rens, 9 Oct 2026, QUESTIONS 5 and 11): the arms are followed, the seat
    between them is one panel falling from the top of the back to the seat's front edge, so
    water runs off to the front (rule 12); the arm insides meet it in a line that falls too."""
    for name, back_z, front_z in (("drawing-s20-bora-not-ordered", 840.0, 400.0),
                                  ("drawing-s48", 890.0, 430.0)):  # fmt: skip
        spec = json.loads((SHAPES / f"{name}.json").read_text())
        pieces = dg.build(spec, ROLL)
        seat = _pts(pieces, "seat")
        assert seat[:, 2].max() == pytest.approx(back_z, abs=1.0)
        assert seat[:, 2].min() == pytest.approx(front_z, abs=1.0)
        front = seat[np.isclose(seat[:, 1], seat[:, 1].max())]
        assert np.allclose(front[:, 2], front_z, atol=1.0)  # the front edge level
        inside = _pts(pieces, "arm-inside-left")
        low = inside[np.argmin(inside[:, 2])]
        assert low[1] == pytest.approx(seat[:, 1].max(), abs=1.0)  # its lowest point at the front


def test_a_front_wall_whose_top_runs_at_a_slant() -> None:
    """S38/S39 (Rens, 9 Oct 2026, QUESTIONS 8): the front wall's top falls from 59.9 cm to
    40.1 cm at the slanted side, so the top panel tilts out to two sides; S39 is the mirror."""
    for name in ("drawing-s38", "drawing-s39"):
        spec = json.loads((SHAPES / f"{name}.json").read_text())
        pieces = dg.build(spec, ROLL)
        front = _pts(pieces, "front")
        top = front[front[:, 2] > 1.0]
        assert (round(top[:, 2].min() / MM, 1), round(top[:, 2].max() / MM, 1)) == (40.1, 59.9)
        assert any(p.name == "slope" for p in pieces)  # one panel, a ruled patch


def test_a_flat_bag_is_two_panels_stitched_round_but_the_bottom() -> None:
    """Rens, Desk 14 Oct 2026, U1/U2 (parasol covers): "just twice the panel on the drawing, the
    two stitched together all round except the bottom line". Two panels of the drawn outline,
    sharing every point of the stitched edges, apart only inside and along the open bottom."""
    spec = json.loads((SHAPES / "drawing-u1.json").read_text())
    assert spec["shape"] == "flat-bag" and spec["no_vents"]
    front, back = dg.build(spec, ROLL, 3000.0)
    a, b = _pts([front], front.name), _pts([back], back.name)
    assert np.ptp(a[:, 0]) == pytest.approx(600.0) and np.ptp(a[:, 2]) == pytest.approx(2690.0)
    # the same outline in plan (x, z), each panel standing off the middle by at most a little
    assert np.allclose(a[:, [0, 2]], b[:, [0, 2]]) and np.abs(a[:, 1]).max() <= dg.BAG_STAND_MM
    shared = np.isclose(a[:, 1], b[:, 1])  # the points the two panels have in common
    left, right = np.isclose(a[:, 0], 0.0), np.isclose(a[:, 0], 600.0) & (a[:, 2] < 1800.0)
    assert shared[left].all() and shared[right].all()  # the stitched sides
    bottom = np.isclose(a[:, 2], 0.0) & (a[:, 0] > 100.0) & (a[:, 0] < 500.0)
    assert bottom.any() and not shared[bottom].any()  # the bottom is open
    # each panel lies flat as drawn: its 3D area is the outline's area (R10 and the small round)
    tri = np.array(front.faces)
    area = (
        0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum()
    )
    ring = dg.filleted(spec["params"]["outline_cm"], spec["params"]["round_cm"]) * MM
    x, z = ring[:, 0], ring[:, 1]
    plan = 0.5 * abs(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1)))
    assert area == pytest.approx(plan, rel=1e-3)


def test_a_rounded_corner_keeps_its_radius() -> None:
    ring = dg.filleted([[0, 0], [100, 0], [100, 100], [0, 100]], [[2, 10]])
    corner = ring[(ring[:, 0] > 90) & (ring[:, 1] > 90)]
    assert np.allclose(np.hypot(corner[:, 0] - 90, corner[:, 1] - 90), 10)
    assert len(dg.filleted([[0, 0], [10, 0], [10, 10]], [[1, 50]])) == 3  # no room: left sharp


def test_the_audit_flags_two_pieces_left_unjoined(tmp_path: Path) -> None:
    """S43, 14 Oct 2026: two arcs sampled at other angles left the back band and the back wall
    unjoined along 163 cm: two free edges in one place, above the hem."""
    from coverengine.audit import open_seam_checks
    from coverengine.params import Registry

    # a wall (0..400 mm high) and a roof piece above it, meeting along z = 400
    v = np.array([[0, 0, 0], [1000, 0, 0], [1000, 0, 400], [0, 0, 400],  # the wall
                  [0, 0, 400], [1000, 0, 400], [1000, 500, 600], [0, 500, 600]], float)  # fmt: skip
    f = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])
    labels = np.array([0, 0, 1, 1])
    (tmp_path / "panels.json").write_text(json.dumps({"panels": [{"name": "skirt-back"},
                                                                 {"name": "top-1"}]}))  # fmt: skip
    params = Registry.load(None).resolve()
    joined = np.array([0, 1, 2, 3, 3, 2, 6, 7])  # the seam's points are one point each
    np.savez(tmp_path / "panels.npz", vertices=v, faces=f, labels=labels, original_vertex=joined)
    assert open_seam_checks(tmp_path, params)[0]["ok"]
    apart = np.arange(8)  # the same places, but two points each: not joined
    np.savez(tmp_path / "panels.npz", vertices=v, faces=f, labels=labels, original_vertex=apart)
    (check,) = open_seam_checks(tmp_path, params)
    assert not check["ok"] and "skirt-back / top-1" in check["detail"]


def test_the_audit_flags_a_sharp_fold_inside_a_piece(tmp_path: Path) -> None:
    """S43's nose top, 15 Oct 2026 ("rare knik in paneel top 1"): a triangle folded 62 degrees
    against the rest of its piece; a gentle bend passes."""
    from coverengine.audit import kink_checks
    from coverengine.params import Registry

    params = Registry.load(None).resolve()

    def piece(rise: float) -> None:
        # one top piece of two 2 m x 1 m halves meeting along y = 1000, the second rising
        v = np.array([[0, 0, 0], [2000, 0, 0], [2000, 1000, 0], [0, 1000, 0],
                      [2000, 2000, rise], [0, 2000, rise]], float)  # fmt: skip
        f = np.array([[0, 1, 2], [0, 2, 3], [3, 2, 4], [3, 4, 5]])
        np.savez(tmp_path / "panels.npz", vertices=v, faces=f, labels=np.zeros(4, int),
                 original_vertex=np.arange(6))  # fmt: skip

    (tmp_path / "panels.json").write_text(json.dumps({"panels": [{"name": "top-1"}]}))
    (tmp_path / "hull.json").write_text(json.dumps({"top": "given"}))
    piece(100.0)  # about 6 degrees
    assert kink_checks(tmp_path, params)[0]["ok"]
    piece(1880.0)  # about 62 degrees, over 2 m
    (check,) = kink_checks(tmp_path, params)
    assert not check["ok"] and "top-1" in check["detail"]
