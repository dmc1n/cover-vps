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
    """Owner, 5 Oct 2026: "4 Air Pocket" on the drawing beats one per metre."""
    from coverengine.finish.finish import per_side

    sides = {"back": 3000, "front": 3000, "left": 900, "right": 900}
    assert sum(per_side(sides, params()).values()) == 8
    four = per_side(sides, params(**{"features.vents_total": 4}))
    assert four == {"back": 2, "front": 2, "left": 0, "right": 0}
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
