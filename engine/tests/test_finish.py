from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely
from coverengine.export.cut import roll_length, write_export
from coverengine.finish.finish import Piece, finish, finished_set, place_vents, vent_count
from coverengine.params import Registry
from coverengine.params.registry import load_yaml_layer, presets_dir

FINISH = {
    "construction.method": "double_stitch",
    "stitching.allowance_mm": 15,
    "stitching.sides": "both",
    "welding.overlap_mm": 30,
    "welding.guide_line": True,
    "hem.type": "drawcord_channel",
    "hem.allowance_mm": 50,
    "hem.cord_exits": 2,
    "features.vent_width_mm": 250,
    "features.vent_height_mm": 220,
    "features.vent_above_hem_mm": 50,
    "features.vents_per_metre": 1,
    "features.vents_min": 1,
    "features.vent_seam_clearance_mm": 100,
    "features.vent_hood_depth_mm": 80,
    "pen.label_height_mm": 15,
    "export.sheet_spacing_mm": 20,
    "roll.usable_width_mm": 1480,
}


def params(**overrides: Any) -> Any:
    return Registry.load().resolve(trial={**FINISH, **overrides})


def square(name: str, size: float, kinds: list[str], lap: list[bool]) -> dict[str, Any]:
    """A square panel; edges bottom, right, top, left (counter-clockwise)."""
    outline = [[0.0, 0.0], [size, 0.0], [size, size], [0.0, size]]
    edges = []
    for k, (kind, is_lap) in enumerate(zip(kinds, lap, strict=True)):
        e: dict[str, Any] = {"range": [k, (k + 1) % 4], "kind": kind, "length_2d_mm": size}
        if kind == "seam":
            e.update({"seam": f"{name}/x{k}", "mate": f"x{k}", "lap_side": name if is_lap else "x"})
        edges.append(e)
    return {
        "id": "P1",
        "name": name,
        "quantity": 1,
        "outline_mm": outline,
        "edges": edges,
        "pen": [],
    }


def doc(*panels: dict[str, Any]) -> dict[str, Any]:
    return {"model_id": "test", "parameter_hash": "0" * 64, "panels": list(panels)}


def cut_size(pieces: list[Piece], name: str) -> tuple[float, float, float, float]:
    c = next(p for p in pieces if p.name == name).cut
    return float(c[:, 0].min()), float(c[:, 1].min()), float(c[:, 0].max()), float(c[:, 1].max())


def test_stitched_square_grows_on_every_side() -> None:
    pieces, _ = finish(doc(square("top", 100, ["seam"] * 4, [True, False] * 2)), params())
    assert cut_size(pieces, "top") == pytest.approx((-15, -15, 115, 115), abs=0.01)
    c = next(p for p in pieces if p.name == "top").cut
    assert shapely.Polygon(c).area == pytest.approx(130 * 130, rel=1e-6)  # square corners


def test_welded_overlap_on_the_lap_side_only() -> None:
    d = doc(square("top", 100, ["seam"] * 4, [True, False, True, False]))
    pieces, _ = finish(d, params(**{"construction.method": "welded"}))
    # bottom and top lap over: 30 mm there, nothing on the right and left
    assert cut_size(pieces, "top") == pytest.approx((0, -30, 100, 130), abs=0.01)
    top = next(p for p in pieces if p.name == "top")
    assert len(top.pen_lines) >= 2 + 2  # stitch lines on the lap edges, weld guides on the others


def test_hem_allowance_with_fold_line() -> None:
    d = doc(square("skirt-front", 1000, ["hem", "seam", "seam", "seam"], [False] * 4))
    pieces, _ = finish(d, params(**{"features.vents_min": 0, "features.vents_per_metre": 0}))
    assert cut_size(pieces, "skirt-front") == pytest.approx((-15, -50, 1015, 1015), abs=0.01)
    fold = next(p for p in pieces if p.name == "skirt-front").pen_lines[0]
    assert np.allclose(fold[:, 1], 0.0)  # the fold line on the hem line


@pytest.mark.parametrize(("hem", "count"), [(900, 1), (1000, 1), (1999, 1), (2000, 2), (6300, 6)])
def test_vent_count(hem: float, count: int) -> None:
    assert vent_count(hem, params()) == count


def test_vents_spread_and_clear_of_seams() -> None:
    d = doc(square("skirt-front", 2000, ["hem", "seam", "seam", "seam"], [False] * 4))
    vents, warnings = place_vents(d["panels"], params())
    assert not warnings
    rects = vents["skirt-front"]
    assert len(rects) == 2
    xs = sorted(float(r[:, 0].mean()) for r in rects)
    assert xs == pytest.approx([500, 1500], abs=1.0)  # evenly along the hem
    for r in rects:
        assert r[:, 1].min() == pytest.approx(50.0)  # 5 cm above the hem
        assert np.ptp(r[:, 0]) == pytest.approx(250.0) and np.ptp(r[:, 1]) == pytest.approx(220.0)


def test_vents_on_an_inner_wall_by_the_switch(tmp_path: Path) -> None:
    """`features.vent_inner_walls`: on (the company default, owner 9 Oct 2026, QUESTIONS 71,
    ADR-110) the front (inner) walls of an L get vents too; off, none (the old reading of 7 Oct,
    ADR-093)."""
    import json

    from coverengine.finish.finish import inner_skirts

    # an L of upright walls, 0.4 m high: outer walls and the two inner walls at the corner
    ring = [(0, 0), (3000, 0), (3000, 1000), (1000, 1000), (1000, 3000), (0, 3000)]
    names = ["skirt-front", "skirt-right", "skirt-front-2", "skirt-right-2", "skirt-back",
             "skirt-left"]  # fmt: skip
    verts, faces, labels = [], [], []
    for i, (a, b) in enumerate(zip(ring, ring[1:] + ring[:1], strict=True)):
        k = len(verts)
        verts += [(*a, 0), (*b, 0), (*b, 400), (*a, 400)]
        faces += [(k, k + 1, k + 2), (k, k + 2, k + 3)]
        labels += [i, i]
    np.savez(tmp_path / "panels.npz", vertices=np.array(verts, dtype=float),
             faces=np.array(faces), labels=np.array(labels))  # fmt: skip
    (tmp_path / "panels.json").write_text(json.dumps({"panels": [{"name": n} for n in names]}))
    inner = inner_skirts(tmp_path, params())
    assert inner == {"skirt-front-2", "skirt-right-2"}
    d = doc(square("skirt-front-2", 2000, ["hem", "seam", "seam", "seam"], [False] * 4))
    assert Registry.load().resolve()["features.vent_inner_walls"] is True  # the default
    vents, _ = place_vents(d["panels"], params(), inner)
    assert sorted(vents) == ["skirt-front-2"] and len(vents["skirt-front-2"]) == 2  # 1 per m
    vents, _ = place_vents(d["panels"], params(**{"features.vent_inner_walls": False}), inner)
    assert not vents


def test_a_low_skirt_gets_a_lower_vent_or_none() -> None:
    """Owner, 1 Oct 2026: same width, lower opening down to 10 cm; lower sides get none."""
    d = doc(square("skirt-front", 250, ["hem", "seam", "seam", "seam"], [False] * 4))
    d["panels"][0]["outline_mm"] = [[0, 0], [1200, 0], [1200, 250], [0, 250]]
    vents, warnings = place_vents(d["panels"], params())
    (rect,) = vents["skirt-front"]
    assert np.allclose(np.ptp(rect, axis=0), [250, 180])  # 25 - 5 - 1.5 cm, whole cm
    d["panels"][0]["outline_mm"] = [[0, 0], [1200, 0], [1200, 150], [0, 150]]
    vents, warnings = place_vents(d["panels"], params())
    assert not vents and any("lower than 16.5 cm" in w for w in warnings)


def test_roll_length_rows_across_the_roll() -> None:
    piece = Piece("P1", "a", 3, np.array([[0, 0], [700, 0], [700, 400], [0, 400.0]]), None)
    # 400 wide across the roll: three side by side (400 + 20 + 400 + 20 + 400 <= 1480)
    assert roll_length([piece], 1480, 20) == pytest.approx(700)


def test_export_files_are_deterministic(tmp_path: Path) -> None:
    d = doc(square("skirt-front", 1200, ["hem", "seam", "seam", "seam"], [False] * 4))
    d["panels"][0]["outline_mm"] = [[0, 0], [1200, 0], [1200, 400], [0, 400]]
    for out in ("a", "b"):
        (tmp_path / out).mkdir()
        pieces, warnings = finish(d, params())
        write_export(tmp_path / out, pieces, finished_set(d, pieces, warnings, params()), params())
    for f in ("cut.dxf", "cut.svg", "cutting-list.pdf"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f


def test_vents_one_per_full_metre_of_each_side() -> None:
    """Owner, 1 Oct 2026: each side separately, one per full metre, at least one."""
    from coverengine.finish.finish import per_side, side_of

    assert side_of("skirt-front-2") == "skirt-front" and side_of("skirt-left") == "skirt-left"
    sides = {"a": 2100, "b": 2900, "c": 3100, "d": 1400, "e": 340}
    assert per_side(sides, params()) == {"a": 2, "b": 2, "c": 3, "d": 1, "e": 1}


def test_the_number_on_the_drawing_always_wins_spread_by_length() -> None:
    """Owner, 5 Oct 2026: "4 Air Pocket" on the drawing beats one per metre. Rens, 8 Oct 2026
    (S22, D4): one on every side first, then the longest sides get more (ADR-099)."""
    from coverengine.finish.finish import per_side

    sides = {"back": 3000, "front": 3000, "left": 900, "right": 900}
    assert sum(per_side(sides, params()).values()) == 8
    four = per_side(sides, params(**{"features.vents_total": 4}))
    assert four == {"back": 1, "front": 1, "left": 1, "right": 1}
    six = per_side(sides, params(**{"features.vents_total": 6}))
    assert six == {"back": 2, "front": 2, "left": 1, "right": 1}
    assert sum(per_side(sides, params(**{"features.vents_total": 7})).values()) == 7


def test_a_short_side_still_gets_its_vent() -> None:
    """Owner, 1 Oct 2026: a short side (a 34 cm chair side) needs a vent too."""
    d = doc(square("skirt-left", 340, ["hem", "seam", "seam", "seam"], [False] * 4))
    d["panels"][0]["outline_mm"] = [[0, 0], [340, 0], [340, 400], [0, 400]]
    vents, warnings = place_vents(d["panels"], params())
    (rect,) = vents["skirt-left"]
    assert np.isclose(rect[:, 0].min(), 45) and np.isclose(rect[:, 0].max(), 295)  # centred
    d["panels"][0]["outline_mm"] = [[0, 0], [260, 0], [260, 400], [0, 400]]
    vents, warnings = place_vents(d["panels"], params())
    assert not vents and any("a vent needs 28 cm" in w for w in warnings)


def test_table_covers_get_a_middle_cord_line_and_every_hood_a_logo() -> None:
    """Owner, 1 Oct 2026: two drawcords on table covers; a logo on every air vent."""
    d = doc(square("skirt-front", 1200, ["hem", "seam", "seam", "seam"], [False] * 4))
    d["panels"][0]["outline_mm"] = [[0, 0], [1200, 0], [1200, 870], [0, 870]]
    pieces, _ = finish(d, params(**{"features.middle_cord": True}))
    side = next(p for p in pieces if p.name == "skirt-front")
    assert any("MIDDLE CORD 43.5 CM UP" in t for t, _, _ in side.pen_text)
    level = [ln for ln in side.pen_lines if len(ln) >= 2 and np.allclose(ln[:, 1], 435)]
    assert level  # halfway up, level
    hood = next(p for p in pieces if p.name == "vent-hood")
    assert any(t == "LOGO" for t, _, _ in hood.pen_text)


def wall(
    name: str, length: float, high: float, z0: float = 50.0, top: str = "seam", mate: str = "x"
) -> dict[str, Any]:
    """An upright skirt-like piece with its edges' heights (`z_mm`): bottom hem, right seam, top
    (`top`: seam to `mate`, or a free edge, kind hem), left seam."""
    p = square(name, length, ["hem", "seam", top, "seam"], [False] * 4)
    p["outline_mm"] = [[0.0, 0.0], [length, 0.0], [length, high], [0.0, high]]
    zs = [[z0, z0], [z0, z0 + high], [z0 + high, z0 + high], [z0, z0 + high]]
    for e, z in zip(p["edges"], zs, strict=True):
        e["z_mm"] = z
    if top == "seam":
        p["edges"][2]["mate"] = mate
    return p


def test_a_vent_on_a_too_short_piece_moves_to_a_roomy_one() -> None:
    """C27 (6 Oct 2026): a share of the drawing's vents fell on a 16 cm end piece and was lost;
    it goes to a piece with room instead, so the count is kept."""
    d = doc(wall("skirt-front-1", 160, 400), wall("skirt-front-2", 2000, 400))
    vents, warnings = place_vents(d["panels"], params(**{"features.vents_total": 2}))
    assert len(vents["skirt-front-2"]) == 2 and "skirt-front-1" not in vents
    assert any("a vent needs 28 cm" in w for w in warnings)


def test_a_too_short_piece_may_simply_go_without_a_vent() -> None:
    """Owner, 12 Oct 2026 (QUESTIONS 81): on a BBQ cover with side tables the 25 cm strip beside
    the front has no room for a vent; that side has one vent fewer and it is no warning."""
    d = doc(wall("skirt-front-1", 1000, 400), wall("skirt-front-2", 250, 400),
            wall("skirt-front-3", 1000, 400))  # fmt: skip
    warned = place_vents(d["panels"], params())
    accepted = place_vents(d["panels"], params(**{"features.vent_short_piece_ok": True}))
    assert any("a vent needs 28 cm" in w for w in warned[1])
    assert not accepted[1] and "skirt-front-2" not in accepted[0]
    assert {k: len(v) for k, v in accepted[0].items()} == {k: len(v) for k, v in warned[0].items()}
    bbq = load_yaml_layer(presets_dir() / "bbq.yaml")
    assert Registry.load().resolve(preset=bbq)["features.vent_short_piece_ok"] is True
    assert params()["features.vent_short_piece_ok"] is False


def test_vents_go_round_every_side_first_in_the_middle_of_each_piece() -> None:
    """Rens, 8 Oct 2026 (S18, D4, C1-C31): "the right number, but too many at the back": one on
    every side first, in the middle of the piece, a side not served yet before a second piece
    facing the same way; the drawing's number kept (ADR-099)."""
    from coverengine.finish.finish import Walls

    d = doc(wall("skirt-back", 3800, 800), wall("skirt-front-2", 2700, 370),
            wall("skirt-front-1", 1100, 800), wall("skirt-left", 1100, 800),
            wall("skirt-right", 1100, 800))  # fmt: skip
    walls = Walls(facing={"skirt-back": (0.0, 1.0), "skirt-front-2": (0.0, -1.0),
                          "skirt-front-1": (0.0, -1.0), "skirt-left": (-1.0, 0.0),
                          "skirt-right": (1.0, 0.0)})  # fmt: skip
    vents, _ = place_vents(d["panels"], params(**{"features.vents_total": 4}), walls)
    assert sorted(vents) == ["skirt-back", "skirt-front-2", "skirt-left", "skirt-right"]
    (back,) = vents["skirt-back"]
    assert back[:, 0].mean() == pytest.approx(1900.0)  # the middle of the piece
    vents, _ = place_vents(d["panels"], params(**{"features.vents_total": 6}), walls)
    assert len(vents["skirt-back"]) == 2 and len(vents["skirt-front-1"]) == 1
    bottoms = {round(float(r[:, 1].min())) for rs in vents.values() for r in rs}
    assert bottoms == {50}  # all at one height


def test_no_vent_hangs_from_a_free_top_edge() -> None:
    """C24 and S25 (Rens, 8 Oct 2026: "upside down"): an open top edge is a hem too; a vent
    goes only on the bottom hem, at the cover's lower end."""
    d = doc(wall("skirt-back", 2940, 900, top="hem"))
    vents, _ = place_vents(d["panels"], params(**{"features.vents_total": 2}))
    assert len(vents["skirt-back"]) == 2
    assert all(r[:, 1].max() < 450 for r in vents["skirt-back"])


def test_a_skirt_too_low_hands_its_vents_to_the_piece_above() -> None:
    """Rens, 8 Oct 2026 (Kota, Evora, Portofino daybed: "2 per side, 8 in total"): a box
    cover's 12 cm band has no room for a vent; the piece above it gets them, over the seam."""
    band = wall("skirt-right", 2100, 120, mate="top-2")
    side = wall("top-2", 2100, 700, z0=170.0)
    side["edges"][0].update({"kind": "seam", "mate": "skirt-right", "seam": "s", "lap_side": "x"})
    vents, warnings = place_vents(doc(band, side)["panels"], params())
    assert len(vents["top-2"]) == 2 and "skirt-right" not in vents
    assert not any("lower than" in w for w in warnings)
    vents, warnings = place_vents(
        doc(band, side)["panels"], params(**{"features.vent_above_low_skirt": False})
    )
    assert not vents and any("lower than 16.5 cm" in w for w in warnings)


def test_a_vent_by_hand_one_panel_up_over_the_low_wall() -> None:
    """Rens on D1/D2 (15 Oct 2026): "the side vents one panel up, on the sloping panels". The
    18 cm side wall had a vent shrunk to 11 cm by the rule (owner, 1 Oct: a low side gets a
    lower opening); named in `features.vent_positions`, the piece above gets a full vent over
    its seam with that wall. The rule alone keeps the lower opening (ADR-142)."""
    band = wall("skirt-left", 2200, 180, z0=0.0, mate="top-4")
    side = wall("top-4", 2200, 480, z0=180.0, top="hem")
    side["edges"][0].update({"kind": "seam", "mate": "skirt-left", "seam": "s", "lap_side": "x"})
    panels = doc(band, side)["panels"]
    vents, _ = place_vents(panels, params(**{"features.vents_total": 1}))
    (low,) = vents["skirt-left"]
    assert float(np.ptp(low[:, 1])) == pytest.approx(110.0)  # the rule: a lower opening
    vents, warnings = place_vents(panels, params(**{"features.vent_positions": "top-4@0.5"}))
    assert "skirt-left" not in vents and not warnings
    (up,) = vents["top-4"]
    assert float(np.ptp(up[:, 1])) == pytest.approx(220.0)  # full size
    assert float(up[:, 1].min()) == pytest.approx(50.0)  # 5 cm over the seam, not the free top
    assert float(up[:, 0].mean()) == pytest.approx(1100.0)


def test_a_vent_by_hand_at_a_height_off_the_fold() -> None:
    """Rens on L3 (15 Oct 2026): the vent onto the chamfer, above the 7.6 cm band, while band and
    chamfer are one piece. "piece@fraction@cm" sets the vent's bottom that far above the edge;
    without it the usual 5 cm; a negative or unreadable height is warned (ADR-144)."""
    d = doc(wall("top-2", 2200, 800))
    plain, _ = place_vents(d["panels"], params(**{"features.vent_positions": "top-2@0.5"}))
    assert float(plain["top-2"][0][:, 1].min()) == pytest.approx(50.0)
    by_hand = params(**{"features.vent_positions": "top-2@0.25@12.6"})
    vents, warnings = place_vents(d["panels"], by_hand)
    (rect,) = vents["top-2"]
    assert not warnings
    assert float(rect[:, 1].min()) == pytest.approx(126.0)  # 7.6 cm band + 5 cm
    assert float(np.ptp(rect[:, 1])) == pytest.approx(220.0)  # full size
    assert float(rect[:, 0].mean()) == pytest.approx(550.0)
    top = params(**{"features.vent_positions": "top-2@0.5@12.6", "features.vent_align": "top"})
    (rect,) = place_vents(d["panels"], top)[0]["top-2"]
    assert float(rect[:, 1].min()) == pytest.approx(126.0)  # the height by hand wins
    bad = params(**{"features.vent_positions": "top-2@0.5@-3, top-2@0.5@x"})
    vents, warnings = place_vents(d["panels"], bad)
    assert not vents and len(warnings) == 2


def test_inner_walls_on_request_and_positions_by_hand() -> None:
    """The front (inner) walls get vents by default as Rens marked (ADR-110); off, ADR-093's
    outer walls only; `features.vent_positions` places them where the rule cannot reach."""
    d = doc(wall("skirt-front-2", 2000, 400), wall("skirt-back", 3000, 800))
    inner = frozenset({"skirt-front-2"})
    vents, _ = place_vents(
        d["panels"],
        params(**{"features.vents_total": 2, "features.vent_inner_walls": False}),
        inner,
    )
    assert sorted(vents) == ["skirt-back"]
    vents, _ = place_vents(d["panels"], params(**{"features.vents_total": 2}), inner)
    assert sorted(vents) == ["skirt-back", "skirt-front-2"]
    by_hand = params(**{"features.vent_positions": "skirt-back@0.25, skirt-back@0.75, nope@1"})
    vents, warnings = place_vents(d["panels"], by_hand, inner)
    xs = sorted(float(r[:, 0].mean()) for r in vents["skirt-back"])
    assert xs == pytest.approx([750.0, 2250.0]) and "skirt-front-2" not in vents
    assert any("nope" in w for w in warnings)


def test_vents_at_the_top_of_the_skirt_on_request() -> None:
    """R1-R3 ("4 Air Pockets at Top"; QUESTIONS 66): `features.vent_align` top or middle."""
    d = doc(wall("skirt-front", 3000, 870))
    top = params(**{"features.vents_total": 1, "features.vent_align": "top"})
    ((rect,),) = place_vents(d["panels"], top)[0].values()
    assert rect[:, 1].max() == pytest.approx(870 - 50) and np.ptp(rect[:, 1]) == 220
    mid = params(**{"features.vents_total": 1, "features.vent_align": "middle"})
    ((rect,),) = place_vents(d["panels"], mid)[0].values()
    assert rect[:, 1].mean() == pytest.approx(435)


def test_vent_walls_face_out_of_the_cover(tmp_path: Path) -> None:
    """The way each piece faces, out of the cover, also on an L's inner walls (ADR-099)."""
    import json

    from coverengine.finish.finish import vent_walls

    ring = [(0, 0), (3000, 0), (3000, 1000), (1000, 1000), (1000, 3000), (0, 3000)]
    names = ["skirt-front", "skirt-right", "skirt-front-2", "skirt-right-2", "skirt-back",
             "skirt-left"]  # fmt: skip
    verts, faces, labels = [], [], []
    for i, (a, b) in enumerate(zip(ring, ring[1:] + ring[:1], strict=True)):
        k = len(verts)
        verts += [(*a, 0), (*b, 0), (*b, 400), (*a, 400)]
        faces += [(k, k + 1, k + 2), (k, k + 2, k + 3)]
        labels += [i, i]
    # the roof, so the footprint knows where the cover is
    k = len(verts)
    verts += [(x, y, 400) for x, y in ring]
    faces += [(k, k + 1, k + 2), (k, k + 2, k + 3), (k, k + 3, k + 4), (k, k + 4, k + 5)]
    labels += [6] * 4
    np.savez(tmp_path / "panels.npz", vertices=np.array(verts, dtype=float),
             faces=np.array(faces), labels=np.array(labels))  # fmt: skip
    (tmp_path / "panels.json").write_text(
        json.dumps({"panels": [{"name": n} for n in [*names, "top"]]})
    )
    walls = vent_walls(tmp_path, params())
    want = {"skirt-front": (0, -1), "skirt-right": (1, 0), "skirt-front-2": (0, 1),
            "skirt-right-2": (1, 0), "skirt-back": (0, 1), "skirt-left": (-1, 0)}  # fmt: skip
    for name, d in want.items():
        assert walls.facing[name] == pytest.approx(d, abs=1e-6), name
    assert {"skirt-front-2", "skirt-right-2"} <= walls.inner


def _corner_wall(tmp_path: Path, radius: float = 200.0) -> tuple[Any, Any]:
    """One skirt piece, 0.4 m high, round a rounded corner: 600 mm straight, a quarter circle,
    600 mm straight; its middle lies on the corner."""
    import json
    import math

    from coverengine.finish.finish import vent_walls

    arc = [(600 + radius * math.sin(a), radius - radius * math.cos(a))
           for a in np.linspace(0, math.pi / 2, 24)]  # fmt: skip
    path = [(0.0, 0.0), *arc, (600 + radius, radius + 600)]
    verts, faces = [], []
    for x, y in path:
        verts += [(x, y, 0.0), (x, y, 400.0)]
    for k in range(len(path) - 1):
        a = 2 * k
        faces += [(a, a + 2, a + 3), (a, a + 3, a + 1)]
    np.savez(tmp_path / "panels.npz", vertices=np.array(verts), faces=np.array(faces),
             labels=np.zeros(len(faces), dtype=int))  # fmt: skip
    (tmp_path / "panels.json").write_text(json.dumps({"panels": [{"name": "skirt-front"}]}))
    length = float(np.linalg.norm(np.diff(np.array(path), axis=0), axis=1).sum())
    d = doc(square("skirt-front", 400, ["hem", "seam", "seam", "seam"], [False] * 4))
    d["panels"][0]["outline_mm"] = [[0, 0], [length, 0], [length, 400], [0, 400]]
    return d, vent_walls(tmp_path, params())


def test_no_vent_on_a_rounded_corner(tmp_path: Path) -> None:
    """Rens, 9 Oct 2026 (Casto daybed): "geen vents op afgeronde hoeken". A vent whose middle
    falls on a rounded corner moves along its piece to a straight stretch (ADR-134); with
    `features.vent_on_corners` it stays in the middle."""
    import math

    from coverengine.finish.finish import bend_deg

    d, walls = _corner_wall(tmp_path)
    hem = walls.hems["skirt-front"][0]
    corner = (600.0, 600.0 + math.pi * 100)  # where the quarter circle lies along the wall
    assert Registry.load().resolve()["features.vent_on_corners"] is False  # the default
    one = {"features.vents_total": 1}
    vents, warnings = place_vents(d["panels"], params(**one), walls)
    (rect,) = vents["skirt-front"]
    at = float(np.asarray(rect)[:2, 0].mean())
    assert at + 125 < corner[0] or at - 125 > corner[1]  # the opening off the corner
    assert bend_deg(hem, at, 225) <= 25 and not warnings
    vents, _ = place_vents(d["panels"], params(**one, **{"features.vent_on_corners": True}), walls)
    (rect,) = vents["skirt-front"]
    middle = float(np.asarray(rect)[:2, 0].mean())
    assert corner[0] < middle < corner[1]  # on the corner, as before
    assert bend_deg(hem, middle, 225) > 25
    # a person's place is kept (Rens's circles on C27's rounded arm ends)
    by_hand = {**one, "features.vent_positions": "skirt-front@0.5"}
    vents, _ = place_vents(d["panels"], params(**by_hand), walls)
    assert corner[0] < float(np.asarray(vents["skirt-front"][0])[:2, 0].mean()) < corner[1]


def test_a_round_wall_keeps_its_vents() -> None:
    """A piece that is round all along (a round cover's strip) has no straight stretch: its
    vents stay where the rule put them."""
    import math

    from coverengine.finish.finish import bend_deg, has_straight

    circle = np.array([(500 * math.cos(a), 500 * math.sin(a)) for a in np.linspace(0, 2, 60)])
    assert not has_straight(circle, 225, 30)
    assert bend_deg(circle, 400, 225) == pytest.approx(math.degrees(450 / 500), abs=3)
    straight = np.array([(0.0, 0.0), (1000.0, 0.0)])
    assert bend_deg(straight, 500, 225) == pytest.approx(0, abs=1e-6)


def test_the_logo_on_the_cover_is_the_frame_the_hood_carries_in_the_cutting_file() -> None:
    """ADR-146 (owner, 16 Oct 2026: "see the logo on the 3d model so we can check before we
    accept"): one frame, drawn on the hood's PEN layer and placed on the cover where the sewn
    hood hangs: centred on the opening, as far under the hood's stitch line (the ring a seam
    allowance above the opening) as on the hood piece. Without the logo there is none."""
    from coverengine.finish.finish import hood_size, logo_frame, logo_on_cover

    d = doc(square("skirt-front", 1200, ["hem", "seam", "seam", "seam"], [False] * 4))
    d["panels"][0]["outline_mm"] = [[0, 0], [1200, 0], [1200, 870], [0, 870]]
    p = params()
    pieces, _ = finish(d, p)
    side = next(pc for pc in pieces if pc.name == "skirt-front")
    hood = next(pc for pc in pieces if pc.name == "vent-hood")
    assert hood.logo is not None and any(ln is hood.logo for ln in hood.pen_lines)
    (rect,) = side.openings
    (on_cover,) = side.logos
    a = float(p["stitching.allowance_mm"])
    _, hh = hood_size(p)
    # the hood's x runs along the opening; centred on it
    assert on_cover[:4].mean(axis=0)[0] == pytest.approx(rect[:, 0].mean())
    # the hood's sides sewn down the ring: its length shares out over the ring's height
    seam_y = rect[:, 1].max() + a
    ring = np.ptp(rect[:, 1]) + 2 * a
    assert seam_y - on_cover[:, 1] == pytest.approx(((hh - a) - hood.logo[:, 1]) * ring / (hh - a))
    # owner, 16 Oct 2026 (T1): along the vent's bottom, inside the opening's lower part
    assert rect[:, 1].min() < on_cover[:, 1].min() < on_cover[:, 1].max() < rect[:, 1].mean()
    assert np.ptp(on_cover[:, 0]) == pytest.approx(float(p["features.vent_logo_width_mm"]))
    fin = finished_set(d, pieces, [], p)
    by = {pc["name"]: pc for pc in fin["pieces"]}
    assert fin["format_version"] >= 2
    assert by["vent-hood"]["logo_mm"] == [[round(x, 2), round(y, 2)] for x, y in hood.logo]
    assert len(by["skirt-front"]["logos_mm"]) == len(by["skirt-front"]["openings_mm"])
    off = params(**{"features.vent_logo": False})
    assert logo_frame(off) is None and logo_on_cover(rect, off) is None
    pieces, _ = finish(d, off)
    assert not next(pc for pc in pieces if pc.name == "skirt-front").logos


def test_the_vent_logo_sits_along_the_hoods_open_lower_edge_upright() -> None:
    """Owner, 16 Oct 2026 (T1): "het logo zit nu aan de korte kant van de airvent maar moet aan
    de lange kant aan de onderkant van de airvent met het logo omhoog" (ADR-146). The frame lies
    centred along the hood's open lower edge (the vent's 25 cm bottom side), wider than high,
    `features.vent_logo_above_edge_mm` above it; the word LOGO centred in it; the hood says
    which edge is sewn on (TOP, an UP arrow, the stitch lines open at the bottom) and its name
    keeps out of the logo's way. The audit fails the old place by the top edge, and a frame on
    its short side."""
    from coverengine.audit import logo_on_long_bottom_side
    from coverengine.export.strokefont import text_width
    from coverengine.finish.finish import hood_size

    d = doc(square("skirt-front", 1200, ["hem", "seam", "seam", "seam"], [False] * 4))
    d["panels"][0]["outline_mm"] = [[0, 0], [1200, 0], [1200, 870], [0, 870]]
    p = params()
    pieces, _ = finish(d, p)
    hood = next(pc for pc in pieces if pc.name == "vent-hood")
    hw, hh = hood_size(p)
    frame = hood.logo
    assert frame is not None
    assert frame[:, 1].min() == pytest.approx(float(p["features.vent_logo_above_edge_mm"]))
    assert frame[:4].mean(axis=0) == pytest.approx([hw / 2, frame[:4, 1].mean()])
    assert np.ptp(frame[:, 0]) > np.ptp(frame[:, 1])
    texts = {t: (at, h) for t, at, h in hood.pen_text}
    at, h = texts["LOGO"]
    assert at + [text_width("LOGO", h) / 2, h / 2] == pytest.approx(frame[:4].mean(axis=0))
    assert "TOP: SEW TO COVER" in texts and "OPEN EDGE, INSERT" in texts
    assert texts["TOP: SEW TO COVER"][0][1] > hh / 2 > texts["OPEN EDGE, INSERT"][0][1]
    name = next(t for t in texts if t.endswith("VENT-HOOD"))
    assert texts[name][0][1] > frame[:, 1].max()  # the name is above the logo, not over it
    up = [ln for ln in hood.pen_lines if len(ln) == 2 and ln[0][0] == ln[1][0] == hw / 2]
    assert up and up[0][1][1] > up[0][0][1]  # the UP arrow points to the sewn top
    fin = finished_set(d, pieces, [], p)
    entry = next(pc for pc in fin["pieces"] if pc["name"] == "vent-hood")
    ok, why = logo_on_long_bottom_side(entry)
    assert ok, why
    old = dict(entry, logo_mm=[[80, 240], [200, 240], [200, 280], [80, 280], [80, 240]])
    ok, why = logo_on_long_bottom_side(old)
    assert not ok and "upper half" in why
    on_end = dict(entry, logo_mm=[[120, 20], [160, 20], [160, 140], [120, 140], [120, 20]])
    ok, why = logo_on_long_bottom_side(on_end)
    assert not ok and "short side" in why
    outside = dict(entry, logo_mm=[[80, -20], [200, -20], [200, 20], [80, 20], [80, -20]])
    ok, why = logo_on_long_bottom_side(outside)
    assert not ok and "not inside" in why
