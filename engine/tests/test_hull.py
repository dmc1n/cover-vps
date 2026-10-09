import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import trimesh
from coverengine.cli import main
from coverengine.errors import CoverError
from coverengine.hull import clearance
from coverengine.hull.build import build_hull, write_hull
from coverengine.io.model_io import import_model, load_model
from coverengine.params import Registry
from coverengine.testshapes import load_config, write_all, write_stl
from test_import import PARAMS as IMPORT_PARAMS
from trimesh.grouping import group_rows

# Parameters passed explicitly, so a change of company defaults never breaks these tests.
HULL = {
    "hull.clearance_mm": 10,
    "hull.bridge_gap_mm": 60,
    "hull.hem_height_mm": 50,
    "hull.resolution_mm": 5,
    "hull.smoothing": 0.5,
    "hull.sweep_down": True,
    "hull.edge": "rounded",
    "hull.target_edge_length_mm": 15,
    "hull.smoothing_max_iterations": 20,
    "hull.remesh_passes": 5,
    "hull.remesh_max_deviation_mm": 0.5,
    "hull.clearance_passes": 10,
    "hull.max_grid_cells": 60_000_000,
    "hull.top": "tensioned",
    "hull.min_slope_deg": 5,
    "hull.flat_patch_mm": 100,
    "hull.support": "none",
    "hull.support_height_mm": 0,
    "hull.support_radius_mm": 150,
    "seams.ridge_angle_deg": 40,
}
SHAPES = ["box_with_legs", "slatted_table", "chair", "l_lounge", "sphere", "cone"]
FURNITURE = load_config()["furniture"]


def busy_factor() -> float:
    """The time limits are for a quiet machine; while other work (renders, other test runs) keeps
    the CPUs busy, a limit grows with the load per CPU, never below 1."""
    import os

    try:
        load = os.getloadavg()[0]
    except OSError:
        return 1.0
    return max(1.0, load / (os.cpu_count() or 1))


def params(**overrides: Any) -> Any:
    trial = {**IMPORT_PARAMS, **HULL, **{f"hull.{k}": v for k, v in overrides.items()}}
    return Registry.load().resolve(trial=trial)


@pytest.fixture(scope="module")
def models(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("hull")
    generated = root / "generated"
    write_all(generated)
    for name in SHAPES:
        import_model(generated / f"{name}.stl", root / name, params())
    import_model(generated / "chair_faceted.step", root / "chair_faceted", params())
    return root


@pytest.fixture(scope="module")
def hulls(models: Path) -> dict[str, Any]:
    """Hulls with the default test parameters, built once."""
    return {name: build_hull(models / name, params()) for name in [*SHAPES, "chair_faceted"]}


def top_profile(mesh: trimesh.Trimesh, x: float, ys: np.ndarray) -> np.ndarray:
    """Highest hull point above (x, y) for each y, from the section at x."""
    seg = trimesh.intersections.mesh_plane(mesh, plane_normal=[1, 0, 0], plane_origin=[x, 0, 0])
    best = np.full(len(ys), -np.inf)
    for a, b in seg:
        lo, hi = sorted([a[1], b[1]])
        m = (ys >= lo) & (ys <= hi) & (hi > lo)
        if m.any():
            best[m] = np.maximum(best[m], a[2] + (ys[m] - a[1]) / (b[1] - a[1]) * (b[2] - a[2]))
    return best


def slat_and_gap_centres() -> tuple[np.ndarray, np.ndarray, float]:
    t = FURNITURE["slatted_table"]
    depth = t["slats"] * t["slat_width"] + (t["slats"] - 1) * t["slat_gap"]
    starts = -depth / 2 + np.arange(t["slats"]) * (t["slat_width"] + t["slat_gap"])
    slats = starts + t["slat_width"] / 2
    gaps = starts[:-1] + t["slat_width"] + t["slat_gap"] / 2
    return slats, gaps, float(t["height"])


def test_table_top_is_flat_when_gaps_are_bridged(hulls: dict[str, Any]) -> None:
    slats, gaps, height = slat_and_gap_centres()
    mesh = hulls["slatted_table"].mesh
    over_slats = top_profile(mesh, 0.0, slats)
    over_gaps = top_profile(mesh, 0.0, gaps)
    assert over_slats == pytest.approx(height + 10, abs=0.5)
    # a 30 mm ball dips 1.7 mm into a 20 mm gap; remeshing flattens it further
    assert np.all(over_gaps >= height + 10 - 2.0)


def test_draped_table_follows_slats_with_small_bridge(models: Path) -> None:
    slats, gaps, height = slat_and_gap_centres()
    mesh = build_hull(
        models / "slatted_table",
        params(bridge_gap_mm=10, clearance_mm=12, top="draped", edge="rounded"),
    ).mesh
    over_slats = top_profile(mesh, 0.0, slats)
    over_gaps = top_profile(mesh, 0.0, gaps)
    assert over_slats == pytest.approx(height + 12, abs=0.5)
    assert np.all(over_slats.min() - over_gaps >= 2.5)  # a groove over every gap


def test_table_skirt_is_vertical_at_clearance(hulls: dict[str, Any]) -> None:
    t = FURNITURE["slatted_table"]
    mesh = hulls["slatted_table"].mesh
    c = mesh.triangles_center
    skirt = (c[:, 2] > 50 + 20) & (c[:, 2] < t["height"] - t["slat_thickness"] - 40)
    # within 6 degrees of vertical; the slight lean is where slat gaps meet the end skirts
    assert np.abs(mesh.face_normals[skirt][:, 2]).max() < 0.1
    v = np.asarray(mesh.vertices)
    assert np.abs(v[:, 0]).max() == pytest.approx(t["length"] / 2 + 10, abs=1.5)


def test_chair_top_spans_the_seat_in_a_straight_line(hulls: dict[str, Any]) -> None:
    """Rule 12: from the front edge of the seat straight up to the top of the back."""
    ch = FURNITURE["chair"]
    mesh = hulls["chair"].mesh
    v = np.asarray(mesh.vertices)
    ys = np.linspace(v[:, 1].min() + 60, v[:, 1].min() + ch["seat"][1] * 0.8, 7)
    z = top_profile(mesh, 0.0, ys)
    line = np.polyval(np.polyfit(ys, z, 1), ys)
    assert np.abs(z - line).max() < 3.0  # straight
    assert np.all(np.diff(z) > 0)  # rising towards the back
    assert z[len(z) // 2] > ch["seat_height"] + 10 + 100  # well above the seat
    assert hulls["chair"].report["drainage"]["drains"]


def test_chair_hangs_at_sides_and_rear(hulls: dict[str, Any]) -> None:
    ch = FURNITURE["chair"]
    mesh = hulls["chair"].mesh
    v, n, c = np.asarray(mesh.vertices), mesh.face_normals, mesh.triangles_center
    low = (c[:, 2] > 70) & (c[:, 2] < ch["seat_height"] - ch["seat"][2] - 30)
    sides = low & (np.abs(n[:, 0]) > 0.9)
    assert np.abs(c[sides][:, 0]) == pytest.approx(ch["seat"][0] / 2 + 10, abs=1.5)
    rear = low & (n[:, 1] > 0.9)
    assert rear.any() and np.abs(n[rear][:, 2]).max() < 0.1  # within 6 degrees of vertical
    # the rear skirt hangs from the back's top edge, which leans out beyond the seat
    assert c[rear][:, 1].min() > v[:, 1].min() + ch["seat"][1] + 10


def test_draped_chair_follows_the_seat(models: Path) -> None:
    ch = FURNITURE["chair"]
    mesh = build_hull(models / "chair", params(top="draped")).mesh
    v = np.asarray(mesh.vertices)
    seat_y = float(v[:, 1].min()) + 10 + ch["seat"][1] / 4
    assert top_profile(mesh, 0.0, np.array([seat_y]))[0] == pytest.approx(
        ch["seat_height"] + 10, abs=0.5
    )


@pytest.mark.parametrize("name", [*SHAPES, "chair_faceted"])
def test_clearance_everywhere(models: Path, hulls: dict[str, Any], name: str) -> None:
    hull = hulls[name]
    model = load_model(models / name)
    d, _ = clearance.distances(hull.mesh, np.asarray(model.vertices), np.asarray(model.faces))
    assert d.min() >= 10 - 1e-6
    assert hull.report["distance_to_model_mm"]["min"] >= 10 - 1e-3
    assert not [w for w in hull.warnings if "closest point" in w]


@pytest.mark.parametrize("name", SHAPES)
def test_open_at_the_hem(hulls: dict[str, Any], name: str) -> None:
    mesh = hulls[name].mesh
    edges = mesh.edges_sorted[group_rows(mesh.edges_sorted, require_count=1)]
    boundary = np.unique(edges)
    assert len(boundary) > 0
    assert np.asarray(mesh.vertices)[boundary][:, 2] == pytest.approx(50.0, abs=1e-9)
    assert np.asarray(mesh.vertices)[:, 2].min() == pytest.approx(50.0, abs=1e-9)
    assert mesh.is_winding_consistent


def test_faces_point_outward(hulls: dict[str, Any]) -> None:
    mesh = hulls["box_with_legs"].mesh
    top = mesh.triangles_center[:, 2] > mesh.bounds[1][2] - 1
    assert mesh.face_normals[top][:, 2].min() > 0.9


def test_deterministic(models: Path, tmp_path: Path) -> None:
    for out in ("a", "b"):
        write_hull(models / "chair", build_hull(models / "chair", params()), tmp_path / out)
    for f in ("hull.glb", "hull.json", "preview.glb"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f


def test_masks(models: Path, tmp_path: Path) -> None:
    ch = FURNITURE["chair"]
    base = build_hull(models / "chair", params())
    top = ch["seat_height"] + 1
    exclude_back = {"type": "box", "min": [-400, -400, top], "max": [400, 600, 2000]}
    solid_front = {"type": "box", "min": [-100, -500, 0], "max": [100, -350, 300]}
    definition = {
        "format_version": 1,
        "parameters": {},
        "hull_masks": [{**exclude_back, "mode": "exclude"}, {**solid_front, "mode": "solid"}],
    }
    (models / "chair" / "cover.json").write_text(json.dumps(definition))
    try:
        masked = build_hull(models / "chair", params())
    finally:
        (models / "chair" / "cover.json").unlink()
    assert masked.report["masks"] == 2
    assert masked.mesh.bounds[1][2] == pytest.approx(ch["seat_height"] + 10, abs=1.5)
    assert masked.mesh.bounds[0][1] < base.mesh.bounds[0][1] - 50


def test_errors(models: Path) -> None:
    with pytest.raises(CoverError, match="not available yet"):
        build_hull(models / "chair", params(sweep_down=False))
    with pytest.raises(CoverError, match="not higher than the hem"):
        build_hull(models / "chair", params(hem_height_mm=5000))


def test_coarser_grid_for_large_models(models: Path) -> None:
    hull = build_hull(models / "box_with_legs", params(max_grid_cells=200_000))
    assert hull.report["resolution_used_mm"] > 5
    assert any("coarser" in w or "used" in w for w in hull.warnings)
    assert hull.report["distance_to_model_mm"]["min"] >= 10 - 1e-3


def test_cli(models: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "out"
    assert main(["hull", str(models / "chair"), "--clearance", "12", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "clearance 12 mm" in text and "closest 12.0 mm" in text
    report = json.loads((out / "hull.json").read_text())
    assert report["parameter_sources"]["hull.clearance_mm"] == "trial"
    assert report["parameters"]["hull.clearance_mm"] == 12
    scene = trimesh.load(out / "preview.glb", force="scene")
    assert len(scene.geometry) == 2  # furniture and cover


def test_500k_triangle_soup_under_a_minute(tmp_path: Path) -> None:
    """M2 acceptance: a 500k-triangle soup in under 60 s (a sphere and a field of small boxes)."""
    sphere = trimesh.creation.icosphere(subdivisions=7, radius=400.0)
    sphere.apply_translation([0, 0, 450])
    # a lid of 10 mm cubes 2 mm apart above the sphere (bridged by the fabric)
    boxes = [
        trimesh.creation.box([10, 10, 10]).apply_translation([x, y, 900])
        for x in np.arange(-700, 700, 12.0)
        for y in np.arange(-780, 780, 12.0)
    ]  # fmt: skip
    soup = trimesh.util.concatenate([sphere, *boxes])
    assert len(soup.faces) >= 500_000
    stl = tmp_path / "soup.stl"
    write_stl(stl, np.asarray(soup.vertices), np.asarray(soup.faces), "soup")
    import_model(stl, tmp_path / "soup", params())
    start = time.perf_counter()
    hull = build_hull(tmp_path / "soup", params())
    elapsed = time.perf_counter() - start
    assert hull.report["distance_to_model_mm"]["min"] >= 10 - 1e-3
    assert elapsed < 60 * busy_factor(), f"hull took {elapsed:.1f} s"  # a minute when quiet


GOLDEN = Path(__file__).resolve().parents[2] / "testdata" / "golden" / "hull"


def hull_summary(report: dict[str, Any]) -> str:
    """The stable, human-readable facts of a hull report (golden files)."""
    lo, hi = report["bbox_mm"]
    d = report["distance_to_model_mm"]
    hem = report["hem"]
    return (
        "\n".join(
            [
                f"model       {report['model_id']}",
                f"resolution  {report['resolution_used_mm']:g} mm",
                f"triangles   {report['mesh']['triangles']}",
                f"area        {report['area_m2']:.3f} m2",
                f"bbox min    {lo[0]:.1f} {lo[1]:.1f} {lo[2]:.1f} mm",
                f"bbox max    {hi[0]:.1f} {hi[1]:.1f} {hi[2]:.1f} mm",
                f"hem         {hem['length_mm'] / 1000:.2f} m at {hem['height_mm']:g} mm",
                f"distance    min {d['min']:.2f} mm (clearance {d['clearance']:g})",
                f"ridges      {report['ridges']['chains']}",
            ]
        )
        + "\n"
    )


@pytest.mark.parametrize("name", [*SHAPES, "chair_faceted"])
def test_golden_hull(hulls: dict[str, Any], name: str) -> None:
    import os

    text = hull_summary(hulls[name].report)
    golden = GOLDEN / f"{name}.txt"
    if os.environ.get("COVER_UPDATE_GOLDEN") == "1":
        GOLDEN.mkdir(parents=True, exist_ok=True)
        golden.write_text(text, encoding="utf-8")
    assert golden.is_file(), f"no golden file {golden}; run make golden"
    assert text == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["slatted_table", "box_with_legs", "l_lounge"])
def test_flat_tops_are_reported(hulls: dict[str, Any], name: str) -> None:
    report = hulls[name].report
    assert not report["drainage"]["drains"]
    assert report["drainage"]["flat_area_mm2"] > 0.1e6
    assert any("water would stay" in w for w in hulls[name].warnings)


@pytest.mark.parametrize("name", ["chair", "sphere", "cone", "chair_faceted"])
def test_sloped_tops_drain(hulls: dict[str, Any], name: str) -> None:
    assert hulls[name].report["drainage"]["drains"]


def test_balloon_makes_a_table_drain(models: Path) -> None:
    hull = build_hull(models / "slatted_table", params(support="balloon"))
    s = hull.report["support"]
    assert hull.report["drainage"]["drains"] and s["automatic"]
    assert s["centre_mm"] == pytest.approx([0.0, 0.0], abs=5.0)
    # the lowest height that sheds water: a little lower does not
    lower = build_hull(
        models / "slatted_table", params(support="balloon", support_height_mm=0.9 * s["height_mm"])
    )
    assert not lower.report["drainage"]["drains"]
    t = FURNITURE["slatted_table"]
    assert hull.mesh.bounds[1][2] == pytest.approx(t["height"] + 10 + s["height_mm"], abs=2.0)


def test_drainage_finds_a_hollow() -> None:
    from coverengine.hull import drainage

    xs = ys = np.arange(-200.0, 201.0, 5.0)
    r = np.hypot(xs[:, None], ys[None, :])
    bowl = 100 + 0.2 * r - 30 * np.exp(-((r / 60) ** 2))  # a cone with a dent in the middle
    inside = r < 200
    result = drainage.check(bowl, inside, xs, ys, 5.0, 100.0)
    assert not result.drains and result.hollow_area_mm2 > 0
    assert result.worst_xy_mm == pytest.approx((0.0, 0.0), abs=5.0)


def test_concave_envelope_is_straight_between_supports() -> None:
    from coverengine.hull.tension import concave_envelope

    xs = np.arange(0.0, 501.0, 5.0)
    ys = np.arange(0.0, 101.0, 5.0)
    obstacle = np.full((len(xs), len(ys)), 100.0)
    obstacle[-1, :] = 600.0  # a wall at the far end
    inside = np.ones_like(obstacle, dtype=bool)
    z = concave_envelope(obstacle, inside, xs, ys)
    assert z[:, 10] == pytest.approx(100 + xs, abs=1e-6)


def test_preview_shows_where_water_stays(models: Path, tmp_path: Path) -> None:
    for name, expected in (("slatted_table", True), ("chair", False)):
        out = tmp_path / name
        write_hull(models / name, build_hull(models / name, params()), out)
        scene = trimesh.load(out / "preview.glb", force="scene")
        assert ("water" in scene.geometry) is expected, name


@pytest.mark.parametrize("name", SHAPES)
def test_hem_is_one_loop_without_cracks(hulls: dict[str, Any], name: str) -> None:
    """The only boundary is the hem: one loop, the same with or without welding points."""
    mesh = hulls[name].mesh
    welded = trimesh.Trimesh(mesh.vertices, mesh.faces, process=True)
    for m in (mesh, welded):
        edges = m.edges_sorted[group_rows(m.edges_sorted, require_count=1)]
        assert len(np.unique(edges)) == len(edges)  # a simple loop: every hem point has two
    assert len(welded.vertices) == len(mesh.vertices)
