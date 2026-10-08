from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely
from coverengine.export.cut import roll_length, write_export
from coverengine.finish.finish import Piece, finish, finished_set, place_vents, vent_count
from coverengine.params import Registry

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


def test_no_vent_on_an_inner_wall(tmp_path: Path) -> None:
    """Owner, 7 Oct 2026 (C23): air vents only on the outside, never on the inner walls of an
    L shape; the drawing's number goes to the outer walls."""
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
    vents, _ = place_vents(d["panels"], params(), inner)
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


def test_inner_walls_on_request_and_positions_by_hand() -> None:
    """ADR-093 by default; `features.vent_inner_walls` puts them on the front (inner) walls as
    Rens marked; `features.vent_positions` places them where the rule cannot reach."""
    d = doc(wall("skirt-front-2", 2000, 400), wall("skirt-back", 3000, 800))
    inner = frozenset({"skirt-front-2"})
    vents, _ = place_vents(d["panels"], params(**{"features.vents_total": 2}), inner)
    assert sorted(vents) == ["skirt-back"]
    vents, _ = place_vents(
        d["panels"],
        params(**{"features.vents_total": 2, "features.vent_inner_walls": True}),
        inner,
    )
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
