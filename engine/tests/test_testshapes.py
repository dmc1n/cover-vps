from pathlib import Path

import numpy as np
import pytest
import trimesh
from coverengine.cli import main
from coverengine.io.info import mesh_info
from coverengine.testshapes import BUILDERS, load_config, write_all

TOL = 1e-6  # mm, M0 acceptance
# The chair's tilted back has irrational extreme coordinates; STL stores 32-bit floats.
FLOAT32_TOL = 1e-4


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("generated")
    write_all(out)
    return out


def test_every_shape_generated(generated: Path) -> None:
    for name in BUILDERS:
        assert (generated / f"{name}.stl").is_file()
        assert (generated / f"{name}.json").is_file()


def test_cylinder_acceptance(generated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    info = mesh_info(generated / "cylinder.stl")
    names = {c.name for c in info.comparisons}
    assert {"radius_mm", "height_mm", "bbox_min_x_mm", "bbox_max_z_mm"} <= names
    assert info.max_abs_diff <= TOL
    assert main(["info", str(generated / "cylinder.stl")]) == 0
    assert "radius_mm" in capsys.readouterr().out


@pytest.mark.parametrize("name", [n for n in BUILDERS if n != "chair"])
def test_analytic_dimensions_exact(generated: Path, name: str) -> None:
    info = mesh_info(generated / f"{name}.stl")
    assert info.comparisons
    assert info.max_abs_diff <= TOL, [(c.name, c.diff) for c in info.comparisons]


def test_chair_within_float32(generated: Path) -> None:
    assert mesh_info(generated / "chair.stl").max_abs_diff <= FLOAT32_TOL


def test_on_ground(generated: Path) -> None:
    for name in BUILDERS:
        lo, _ = mesh_info(generated / f"{name}.stl").bounds
        assert lo[2] == pytest.approx(0.0, abs=TOL), name


def test_deterministic(generated: Path, tmp_path: Path) -> None:
    write_all(tmp_path)
    for f in sorted(generated.iterdir()):
        assert f.read_bytes() == (tmp_path / f.name).read_bytes(), f.name


def test_reference_areas_close(generated: Path) -> None:
    for name in ("plate", "cylinder", "cone", "sphere", "sphere_octant", "torus_segment"):
        info = mesh_info(generated / f"{name}.stl")
        (_, value, measured), *_ = info.references
        assert measured == pytest.approx(value, rel=5e-3), name


def test_slat_gaps(generated: Path) -> None:
    cfg = load_config()["furniture"]["slatted_table"]
    mesh = trimesh.load(generated / "slatted_table.stl", process=True)
    top = cfg["height"] - cfg["slat_thickness"]
    slats = sorted(
        (tuple(p.bounds[:, 1]) for p in mesh.split(only_watertight=False) if p.bounds[0, 2] >= top),
    )
    assert len(slats) == cfg["slats"]
    gaps = np.diff(np.array(slats).ravel())[1::2]
    assert np.allclose(gaps, cfg["slat_gap"], atol=TOL)


def test_part_counts(generated: Path) -> None:
    expected = {"box_with_legs": 5, "slatted_table": 15, "chair": 6}
    for name, parts in expected.items():
        assert mesh_info(generated / f"{name}.stl").components == parts


def test_closed_shapes_watertight(generated: Path) -> None:
    for name in ("sphere", "box_with_legs", "slatted_table", "chair"):
        assert mesh_info(generated / f"{name}.stl").watertight, name


def test_info_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["info", "does-not-exist.stl"]) == 1
    assert "no such file" in capsys.readouterr().err
