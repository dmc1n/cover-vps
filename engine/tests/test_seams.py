import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely
import trimesh
from coverengine.cli import main
from coverengine.errors import CoverError
from coverengine.hull.build import build_hull, write_hull
from coverengine.io.model_io import import_model
from coverengine.params import Registry
from coverengine.seams.build import cut_cover, write_cut
from coverengine.seams.cut import CutMesh, Seam, apply, is_disk, panels, seam_edges, unzip
from coverengine.testshapes import write_all
from test_hull import HULL
from test_import import PARAMS as IMPORT_PARAMS

# Parameters passed explicitly, so a change of company defaults never breaks these tests.
SEAMS = {
    "seams.ridge_angle_deg": 40,
    "seams.min_weld_radius_mm": 150,
    "seams.seam_tolerance_mm": 1.0,
    "seams.lap_rule": "upper_over_lower",
    "seams.skirt_seam_inset_mm": 1,
    "seams.corner_angle_deg": 45,
    "seams.corner_window_mm": 100,
    "seams.max_skirt_panel_mm": 3000,
    "seams.min_skirt_panel_mm": 300,
    "seams.snap_mm": 1,
    "seams.band_drop_mm": 20,
    "seams.skirt_seam": "level",
    "seams.skirt_height_mm": 0,
    "seams.skirt_below_rim_mm": -3,
    "seams.min_skirt_height_mm": 150,
    "seams.rim_smoothing_mm": 200,
    "seams.wall_min_mm": 20,
    "seams.wall_min_length_mm": 300,
    "roll.usable_width_mm": 1480,
    "construction.method": "double_stitch",
}
SHAPES = {
    "box_with_legs": {},
    "chair": {},
    "slatted_table": {"hull.support": "balloon"},
    "l_lounge": {},
    "sphere": {},
}


def params(**overrides: Any) -> Any:
    trial = {**IMPORT_PARAMS, **HULL, **SEAMS, **overrides}
    return Registry.load().resolve(trial=trial)


@pytest.fixture(scope="module")
def models(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("seams")
    write_all(root / "generated")
    for name, extra in SHAPES.items():
        import_model(root / "generated" / f"{name}.stl", root / name, params())
        write_hull(root / name, build_hull(root / name, params(**extra)))
    return root


@pytest.fixture(scope="module")
def cuts(models: Path) -> dict[str, Any]:
    return {name: cut_cover(models / name, params()) for name in SHAPES}


def names(cut: Any) -> list[str]:
    return sorted(p.name for p in cut.panels)


def test_box_gives_top_and_four_skirts(cuts: dict[str, Any]) -> None:
    cut = cuts["box_with_legs"]
    assert names(cut) == ["skirt-back", "skirt-front", "skirt-left", "skirt-right", "top"]
    assert all(p.disk for p in cut.panels)
    kinds = sorted(s.kind for s in cut.seams)
    assert kinds.count("corner") == 4 and kinds.count("skirt") == 4


def test_chair_panels(cuts: dict[str, Any]) -> None:
    cut = cuts["chair"]
    # the level skirt all round; above it at the sides and back, where the chair stands
    # higher than its seat edge, one wall panel
    assert names(cut) == ["skirt-back", "skirt-front", "skirt-left", "skirt-right", "top", "wall"]
    assert all(p.disk for p in cut.panels)
    low, high = cut.report["skirt_height_mm"]
    assert low == high  # one height all round


def test_level_skirt_seam_is_level(cuts: dict[str, Any]) -> None:
    for name in ("box_with_legs", "chair", "slatted_table"):
        cut = cuts[name]
        z = [
            float(np.ptp(np.asarray(s.points)[:, 2]))
            for s in cut.seams
            if s.kind == "skirt"
            and cut.panels[s.panels[0]].region != "wall"
            and cut.panels[s.panels[1]].region != "wall"
        ]
        assert z and max(z) < 1.0, name  # the skirt seam at one height (within 1 mm)


def test_table_with_balloon_top_fits_the_roll(cuts: dict[str, Any]) -> None:
    cut = cuts["slatted_table"]
    assert len(cut.panels) == 5
    top = next(p for p in cut.panels if p.name == "top")
    assert top.width_mm <= 1480


def test_l_lounge_skirt_split_at_six_corners(cuts: dict[str, Any]) -> None:
    cut = cuts["l_lounge"]
    assert len([p for p in cut.panels if p.region == "skirt"]) == 6
    assert len([p for p in cut.panels if p.region == "top"]) == 1
    assert all(p.disk and p.width_mm <= 1480 for p in cut.panels)


def test_round_skirt_gets_one_seam_at_the_back(cuts: dict[str, Any]) -> None:
    cut = cuts["sphere"]
    assert names(cut) == ["skirt", "top"]
    corner = [s for s in cut.seams if s.kind == "corner"]
    assert len(corner) == 1 and corner[0].points[:, 1].mean() > 0  # at the back (+y)


@pytest.mark.parametrize("name", ["box_with_legs", "chair", "slatted_table"])
def test_mirrored_panels_are_equal(cuts: dict[str, Any], name: str) -> None:
    area = {p.name: p.area_mm2 for p in cuts[name].panels}
    assert area["skirt-left"] == pytest.approx(area["skirt-right"], rel=1e-3)


@pytest.mark.parametrize("name", list(SHAPES))
def test_panels_tile_the_cover(models: Path, cuts: dict[str, Any], name: str) -> None:
    hull = trimesh.load(models / name / "hull.glb", force="scene")
    hull_area = sum(g.area for g in hull.geometry.values())
    # moving points onto seams (at most seams.snap_mm) changes the area a hair
    assert sum(p.area_mm2 for p in cuts[name].panels) == pytest.approx(hull_area, rel=5e-5)
    for s in cuts[name].seams:
        a, b = s.panels
        assert s.length_mm > 0 and (a != b or s.kind == "corner")
        assert s.id in cuts[name].panels[a].seams and s.id in cuts[name].panels[b].seams


def test_lap_sides(cuts: dict[str, Any]) -> None:
    cut = cuts["box_with_legs"]
    by_name = {p.index: p.name for p in cut.panels}
    for s in cut.seams:
        if s.kind == "skirt":
            assert by_name[s.lap_panel] == "top"  # the top laps over the skirt
        else:
            names_ = {by_name[s.panels[0]], by_name[s.panels[1]]}
            if "skirt-front" in names_:
                assert by_name[s.lap_panel] == "skirt-front"  # front over side


def test_roll_width_split_keeps_every_panel_a_disk_that_fits(models: Path) -> None:
    cut = cut_cover(models / "slatted_table", params(**{"roll.usable_width_mm": 700}))
    tops = [p for p in cut.panels if p.region == "top"]
    assert len(tops) >= 2
    assert all(p.disk and p.width_mm <= 700 for p in cut.panels if p.region == "top")


def test_manual_seams(models: Path, tmp_path: Path) -> None:
    seams = {
        "format_version": 1,
        "skirt_seams": [[0.0, -310.0], [0.0, 310.0]],  # middle of the front and the back
        "top_seams": [[[-500.0, 0.0], [500.0, 0.0]]],  # across the top
    }
    path = tmp_path / "seams.json"
    path.write_text(json.dumps(seams))
    cut = cut_cover(models / "box_with_legs", params(), path)
    assert len([p for p in cut.panels if p.region == "top"]) == 2
    assert len([p for p in cut.panels if p.region == "skirt"]) == 2
    assert all(p.disk for p in cut.panels)
    with pytest.raises(CoverError, match="no seam file"):
        cut_cover(models / "box_with_legs", params(), tmp_path / "missing.json")


def test_a_seam_ending_inside_a_panel_is_not_cut_open(models: Path, tmp_path: Path) -> None:
    # one line across the box top, and a second that stops half way (it runs into the first
    # and a little past it): the part past the first line must not leave a slit
    seams = {
        "format_version": 1,
        "top_seams": [[[-500.0, 0.0], [500.0, 0.0]], [[0.0, -500.0], [0.0, 100.0]]],
    }
    path = tmp_path / "seams.json"
    path.write_text(json.dumps(seams))
    cut = cut_cover(models / "box_with_legs", params(), path)
    tops = [p for p in cut.panels if p.region == "top"]
    assert len(tops) == 3 and all(p.disk for p in tops)
    assert not [s for s in cut.seams if s.panels[0] == s.panels[1]]


def test_close_corners_get_one_seam() -> None:
    from coverengine.seams.auto import Outline, split_positions

    square = shapely.Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    line = Outline(square, np.zeros((0, 2)), 4000.0)
    # two corners 50 mm apart become one seam half way; the others stay
    got = split_positions(line, [0.0, 1000.0, 1050.0, 2000.0, 3000.0], 3000.0, 300.0)
    assert len(got) == 4 and any(abs(g - 1025.0) < 1e-6 for g in got)


def test_dome_gets_a_seam_proposal(models: Path) -> None:
    from coverengine.flatten.pattern import build_patterns, pattern_set
    from test_flatten import FLAT

    p = params(**FLAT)
    write_cut(models / "sphere", cut_cover(models / "sphere", p))
    patterns, report = build_patterns(models / "sphere", p)
    doc, _ = pattern_set(models / "sphere", p, patterns, report)
    (proposal,) = [q for q in doc["proposals"] if q["panel"] == "top"]
    a, b = np.asarray(proposal["points"])
    mid = (a + b) / 2
    assert np.linalg.norm(mid) < 50  # through the middle of the dome
    top = next(q for q in patterns if q.name == "top")
    span = float(np.ptp(top.flat.vertices[:, 0]))
    assert np.linalg.norm(b - a) >= 0.9 * span  # across the whole piece


def test_outputs_are_deterministic(models: Path, cuts: dict[str, Any], tmp_path: Path) -> None:
    for out in ("a", "b"):
        write_cut(models / "chair", cut_cover(models / "chair", params()), tmp_path / out)
    for f in ("panels.glb", "panels.json", "seams.auto.json"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f
    auto = json.loads((tmp_path / "a" / "seams.auto.json").read_text())
    again = cut_cover(models / "chair", params(), tmp_path / "a" / "seams.auto.json")
    assert names(again) == names(cuts["chair"])  # the written seams reproduce the panels
    assert len(auto["skirt_seams"]) == 4


def test_cli(models: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["cut", str(models / "box_with_legs"), "--out", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert "top" in text and "fits the roll" in text and "laps over" in text
    report = json.loads((tmp_path / "panels.json").read_text())
    assert len(report["panels"]) == 5
    assert main(["cut", str(tmp_path / "nothing")]) == 1  # no hull there


def test_unzip_opens_a_ring_cut_once() -> None:
    ring = trimesh.creation.cylinder(radius=100, height=100, sections=32)
    ring = trimesh.Trimesh(
        ring.vertices, ring.faces[np.abs(ring.face_normals[:, 2]) < 0.5], process=True
    )
    seam = Seam(
        "cut",
        "corner",
        field=lambda p: p[:, 1],
        faces=lambda c: np.asarray(c.mesh.triangles_center)[:, 0] > 0,
    )
    cut = apply(CutMesh(ring, []), seam, 0.5)
    edges = seam_edges(cut)["cut"]
    assert len(panels(cut.mesh, edges).tolist()) == len(cut.mesh.faces)
    assert not is_disk(cut.mesh)  # still a ring until opened
    assert is_disk(unzip(cut.mesh, edges))
