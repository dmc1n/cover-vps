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


def test_vent_on_a_low_skirt_is_reported() -> None:
    d = doc(square("skirt-front", 250, ["hem", "seam", "seam", "seam"], [False] * 4))
    d["panels"][0]["outline_mm"] = [[0, 0], [1200, 0], [1200, 250], [0, 250]]
    _, warnings = place_vents(d["panels"], params())
    assert any("lower than" in w for w in warnings)


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


def test_vents_one_per_metre_and_at_least_one_on_each_side() -> None:
    """Owner, 1 Oct 2026: one per metre, at least one on every side."""
    from coverengine.finish.finish import per_side, side_of

    assert side_of("skirt-front-2") == "skirt-front" and side_of("skirt-left") == "skirt-left"
    # a 2.5 x 0.9 m cover: 6.8 m of hem, 6 vents; the short ends still get one each
    n = per_side(
        6, {"skirt-front": 2500, "skirt-back": 2500, "skirt-left": 900, "skirt-right": 900}
    )
    assert n == {"skirt-front": 2, "skirt-back": 2, "skirt-left": 1, "skirt-right": 1}
    # a small cover: fewer metres than sides, still one per side
    assert per_side(4, {"a": 500, "b": 500, "c": 400, "d": 400}) == {"a": 1, "b": 1, "c": 1, "d": 1}
