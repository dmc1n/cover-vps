"""Measuring a cover (ADR-111): the vents' sizes and places as the cutting file has them, the
distance along the fabric, the check list and the measured deviations."""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from coverengine.cli import main
from coverengine.export.checklist import ensure_checklist
from coverengine.finish.vents3d import corners_along, ensure_vents
from coverengine.hull.build import build_hull, write_hull
from coverengine.io.model_io import import_model
from coverengine.learned import measure_kind, measured_deviations
from coverengine.measure import check_points, deviations, geodesic, snap_doc
from coverengine.params import Registry, resolve_model
from coverengine.seams.build import cut_cover, write_cut
from coverengine.testshapes import write_all as write_shapes
from test_hull import HULL
from test_import import PARAMS as IMPORT_PARAMS
from test_seams import SEAMS


def _params() -> Any:
    return Registry.load().resolve(trial={**IMPORT_PARAMS, **HULL, **SEAMS})


@pytest.fixture(scope="module")
def box(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The box on legs (800 x 600 x 400 on 300 mm legs, testdata/shapes.yaml), cut and exported:
    four skirt pieces, one vent in the middle of each."""
    root = tmp_path_factory.mktemp("measure")
    write_shapes(root / "generated")
    d = root / "box"
    import_model(root / "generated" / "box_with_legs.stl", d, _params())
    write_hull(d, build_hull(d, _params()))
    write_cut(d, cut_cover(d, _params()))
    assert main(["flatten", str(d)]) == 0
    assert main(["export", str(d)]) == 0
    return d


def test_vent_numbers_are_the_cutting_files(box: Path) -> None:
    """Each vent: its opening as cut, its bottom edge `features.vent_above_hem_mm` above the
    hem along the fabric, and in the middle of its skirt piece: as far from the seam on the left
    as from the one on the right, both together with the opening the piece's hem length."""
    p = resolve_model(box)
    doc = json.loads(ensure_vents(box).read_text())  # type: ignore[union-attr]
    assert doc["format"] == 2 and doc["warnings"] == []
    vents = doc["vents"]
    assert [v["number"] for v in vents] == list(range(1, len(vents) + 1))
    assert sorted(v["piece"] for v in vents) == [
        "skirt-back",
        "skirt-front",
        "skirt-left",
        "skirt-right",
    ]
    pattern = {q["name"]: q for q in json.loads((box / "pattern.json").read_text())["panels"]}
    above = float(p["features.vent_above_hem_mm"])  # type: ignore[arg-type]
    width = float(p["features.vent_width_mm"])  # type: ignore[arg-type]
    for v in vents:
        assert v["size_mm"][0] == pytest.approx(width, abs=0.2)
        assert v["above_hem_mm"] == pytest.approx(above, abs=0.5)
        assert v["bottom_edge"] == "hem"
        hem = sum(e["length_2d_mm"] for e in pattern[v["piece"]]["edges"] if e["kind"] == "hem")
        left, right = v["sides"]["left"], v["sides"]["right"]
        assert left["mm"] + right["mm"] + v["size_mm"][0] == pytest.approx(hem, abs=1.0)
        assert left["mm"] == pytest.approx(right["mm"], abs=1.0)  # one vent: the middle
        assert left["to"] == right["to"] == "seam"
        assert {left["name"], right["name"]} <= set(pattern) and left["name"] != right["name"]
        # in 3D: the bottom 5 cm above the cover's lower edge (the walls are upright)
        assert v["bottom_z_mm"] - doc["lower_edge_z_mm"] == pytest.approx(above, abs=2.0)
        lo, hi = v["height_line_mm"]
        assert hi[2] - lo[2] == pytest.approx(above, abs=2.0)
        # the side lines run along the wall at the opening's bottom height
        for s in (left, right):
            a, b = np.asarray(s["line_mm"])
            assert np.linalg.norm(b - a) == pytest.approx(s["mm"], rel=0.02, abs=3.0)
            assert a[2] == pytest.approx(v["bottom_z_mm"], abs=2.0)
    # left and right as seen from outside: the front's left is the cover's left side (-x)
    front = next(v for v in vents if v["piece"] == "skirt-front")
    assert front["sides"]["left"]["name"] == "skirt-left"
    assert front["sides"]["right"]["name"] == "skirt-right"


def test_an_old_vents_json_is_made_again(box: Path) -> None:
    path = box / "vents.json"
    path.write_text(json.dumps({"vents": [], "warnings": []}))  # format 1, newer than finished
    assert ensure_vents(box) == path
    assert json.loads(path.read_text())["format"] == 2


def test_a_corner_inside_a_piece_is_found() -> None:
    """An L along the hem: 1 m along x, then 0.6 m along y: one corner, 1 m from the start."""
    pts = np.array([[x, 0.0, 50.0] for x in range(0, 1001, 25)]
                   + [[1000.0, y, 50.0] for y in range(25, 601, 25)])  # fmt: skip
    found = corners_along(pts)
    assert len(found) == 1 and found[0] == pytest.approx(1000.0, abs=15.0)
    assert corners_along(pts[:30]) == []  # straight


def test_along_the_fabric(box: Path) -> None:
    """On one flat wall the fabric is the straight line; round a corner of the box it is the
    two walls' widths (less a little for the rounded corner), longer than the straight line."""
    snaps = snap_doc(box)
    lo, hi = np.asarray(snaps["box_mm"])
    z = float(lo[2]) + 150.0
    front = [0.0, float(lo[1]), z]
    g = geodesic(box, [-200.0, float(lo[1]), z], [200.0, float(lo[1]), z + 100.0])
    assert g["straight_mm"] == pytest.approx(math.hypot(400.0, 100.0), abs=0.2)
    assert g["height_mm"] == pytest.approx(100.0)
    assert g["surface_mm"] == pytest.approx(g["straight_mm"], abs=1.0)
    side = [float(hi[0]), 0.0, z]
    g = geodesic(box, front, side)
    walls = float(hi[0]) + float(-lo[1])
    assert g["straight_mm"] == pytest.approx(math.hypot(hi[0], lo[1]), abs=0.5)
    assert walls - 15.0 <= g["surface_mm"] <= walls + 1.0
    assert len(g["path_mm"]) > 2
    # a point off the cover: no fabric distance
    g = geodesic(box, front, [0.0, 0.0, -500.0])
    assert g["surface_mm"] is None and g["why"]


def test_snap_lines(box: Path) -> None:
    snaps = snap_doc(box)
    ids = {s["id"] for s in snaps["seams"]}
    assert len(ids) == len(json.loads((box / "panels.json").read_text())["seams"])
    assert all(len(s["points_mm"]) >= 2 for s in snaps["seams"])
    # the hem: one closed line at the lower edge
    low = [e for e in snaps["edges"] if max(p[2] for p in e) <= snaps["lower_edge_z_mm"] + 5]
    assert len(low) == 1 and low[0][0] == low[0][-1]


def test_check_points_and_list(box: Path) -> None:
    pts = check_points(box)
    by = {p["key"]: p for p in pts["points"]}
    hull = json.loads((box / "hull.json").read_text())
    assert by["size.height"]["mm"] == pytest.approx(
        700 + HULL["hull.clearance_mm"] - pts["lower_edge_z_mm"], abs=5.0
    )
    assert by["size.length"]["mm"] == pytest.approx(800 + 2 * HULL["hull.clearance_mm"], abs=5.0)
    assert by["hem.length"]["mm"] == pytest.approx(hull["hem"]["length_mm"], rel=0.01)
    for v in pts["vents"]:
        n = v["number"]
        assert by[f"vent.{n}.above_hem"]["mm"] == v["above_hem_mm"]
        assert by[f"vent.{n}.left"]["mm"] == v["sides"]["left"]["mm"]
    assert any(k.startswith("seam.") for k in by) and any(k.startswith("piece.") for k in by)
    # the check list: the same numbers, made once, the same file again (rule 10)
    pdf = ensure_checklist(box)
    assert pdf is not None and pdf.read_bytes().startswith(b"%PDF")
    import pymupdf

    text = pymupdf.open(pdf)[0].get_text()
    assert "check list for the sewn cover" in text
    v1 = pts["vents"][0]
    assert f"{v1['above_hem_mm'] / 10:.1f}" in text and f"V1 {v1['piece']}" in text
    first = pdf.read_bytes()
    pdf.unlink()
    assert ensure_checklist(box).read_bytes() == first  # type: ignore[union-attr]


def test_measured_deviations(box: Path, tmp_path: Path) -> None:
    pts = check_points(box)["points"]
    rows = deviations(pts, {"vent.1.above_hem": 58.0, "size.height": 1.0e9, "nope": 3.0})
    assert [r["key"] for r in rows] == ["vent.1.above_hem", "size.height"]
    assert rows[0]["diff_mm"] == pytest.approx(58.0 - rows[0]["expected_mm"])
    assert measure_kind("vent.3.above_hem") == "vent.above_hem"
    assert measure_kind("skirt.skirt-left") == "skirt"
    assert measure_kind("piece.top-1.hem") == "piece.hem"
    assert measure_kind("seam.a/b") == "seam" and measure_kind("size.height") == "size.height"
    # the vents sit 8 mm too high on three covers of one family: systematic
    models = tmp_path / "models"
    for k in range(3):
        d = models / f"c{k}"
        d.mkdir(parents=True)
        (d / "cover.json").write_text(json.dumps({"family": "box"}))
        fit = {"fits": False, "measured": [{"key": f"vent.{k + 1}.above_hem", "diff_mm": 8.0}]}
        (d / "desk.json").write_text(json.dumps({"fit": fit}))
    out = measured_deviations(models, 5.0, 3)
    assert out == [
        {
            "group": "box",
            "kind": "vent.above_hem",
            "values": 3,
            "covers": ["c0", "c1", "c2"],
            "mean_mm": 8.0,
            "max_mm": 8.0,
            "systematic": True,
        }
    ]
    assert not measured_deviations(models, 10.0, 3)[0]["systematic"]
