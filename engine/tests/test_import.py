import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import trimesh
from coverengine.cli import main
from coverengine.io.model_io import import_model, load_model
from coverengine.io.parts import matching_rule, split_bodies
from coverengine.io.placement import UNIT_MM, plausibility_warning, rotation
from coverengine.params import Registry
from coverengine.testshapes import BUILDERS, write_all, write_stl
from coverengine.testshapes.assembly import assembly_specs, write_assembly

FLOAT32_TOL = 1e-3  # mm; model.glb stores 32-bit floats
# Parameters passed explicitly, so a change of company defaults never breaks these tests.
PARAMS = {
    "import.min_part_mm": 8,
    "import.deflection_mm": 0.5,
    "import.angular_deflection_deg": 20,
    "import.sew_tolerance_mm": 0.1,
    "import.default_units": "mm",
    "import.up_axis": "auto",
    "import.front": "-y",
    "import.min_plausible_size_mm": 200,
    "import.max_plausible_size_mm": 6000,
}
CHAIR_PARTS = 7  # seat, back, 4 legs, cushion
HARDWARE = assembly_specs()["chair_assembly"]
SMALL_PARTS = HARDWARE["screws"] + HARDWARE["washers"]


def params(**overrides: Any) -> Any:
    trial = {**PARAMS, **{f"import.{k}": v for k, v in overrides.items()}}
    return Registry.load().resolve(trial=trial)


def run(src: Path, out: Path, **kw: Any) -> dict[str, Any]:
    p = kw.pop("p", None) or params()
    return import_model(src, out, p, **kw).model


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("generated")
    write_all(out)
    return out


def sidecar_size(generated: Path, name: str) -> np.ndarray:
    exact = json.loads((generated / f"{name}.json").read_text())["exact"]
    lo = np.array([exact[f"bbox_min_{a}_mm"]["value"] for a in "xyz"])
    hi = np.array([exact[f"bbox_max_{a}_mm"]["value"] for a in "xyz"])
    return hi - lo


@pytest.mark.parametrize("name", list(BUILDERS))
def test_every_shape_imports(generated: Path, tmp_path: Path, name: str) -> None:
    m = run(generated / f"{name}.stl", tmp_path / name)
    lo, hi = (np.array(b) for b in m["bbox_mm"])
    assert lo[2] == 0.0
    assert (lo[:2] + hi[:2]) == pytest.approx([0.0, 0.0], abs=FLOAT32_TOL)
    assert hi - lo == pytest.approx(sidecar_size(generated, name), abs=FLOAT32_TOL)
    assert m["parts"]["kept"] >= 1 and m["parts"]["dropped_small"] == 0
    assert m["warnings"] == []
    mesh = load_model(tmp_path / name)
    assert np.asarray(mesh.vertices).min(axis=0)[2] == 0.0


def test_furniture_part_counts(generated: Path, tmp_path: Path) -> None:
    for name, kept in {"chair": 6, "slatted_table": 15, "box_with_legs": 5}.items():
        assert run(generated / f"{name}.stl", tmp_path / name)["parts"]["kept"] == kept


def test_step_assembly(generated: Path, tmp_path: Path) -> None:
    m = run(generated / "chair_assembly.step", tmp_path / "a")
    assert m["source"]["units_detected"] == "mm"
    assert (m["parts"]["kept"], m["parts"]["dropped_small"]) == (CHAIR_PARTS, SMALL_PARTS)
    parts = json.loads((tmp_path / "a" / "parts.json").read_text())["parts"]
    paths = {p["path"]: p for p in parts}
    assert {"chair/frame/seat", "chair/frame/back", "chair/cushion"} <= set(paths)
    assert [p for p in paths if p.startswith("chair/frame/leg")] == [
        "chair/frame/leg",
        "chair/frame/leg#2",
        "chair/frame/leg#3",
        "chair/frame/leg#4",
    ]
    assert paths["chair/hardware/screw M4"]["status"] == "dropped_small"
    assert paths["chair/frame/seat"]["volume_mm3"] == pytest.approx(500 * 500 * 40, rel=1e-6)
    # same outline as the STL chair (the cushion stays inside it)
    stl = run(generated / "chair.stl", tmp_path / "s")
    assert np.array(m["bbox_mm"]) == pytest.approx(np.array(stl["bbox_mm"]), abs=FLOAT32_TOL)


def test_step_inch_and_iges(generated: Path, tmp_path: Path) -> None:
    mm = run(generated / "chair_assembly.step", tmp_path / "mm")
    inch = run(generated / "chair_assembly-inch.step", tmp_path / "inch")
    iges = run(generated / "chair_assembly.iges", tmp_path / "iges")
    assert inch["source"]["units_detected"] == "inch"
    assert iges["source"]["format"] == "iges"
    for other in (inch, iges):
        assert np.array(other["bbox_mm"]) == pytest.approx(np.array(mm["bbox_mm"]), abs=FLOAT32_TOL)
        assert other["parts"]["kept"] == CHAIR_PARTS
        assert other["parts"]["dropped_small"] == SMALL_PARTS


def test_step_units_override(generated: Path, tmp_path: Path) -> None:
    m = run(generated / "chair_assembly-inch.step", tmp_path / "x", units="mm")
    assert m["source"]["units_used"] == "mm"
    assert any("treated as mm" in w for w in m["warnings"])
    assert any("--units inch" in w for w in m["warnings"])  # now looks too small


def test_exclusions_are_remembered(generated: Path, tmp_path: Path) -> None:
    out = tmp_path / "chair"
    src = generated / "chair_assembly.step"
    m = run(src, out, exclude=["CUSHION*"])
    assert (m["parts"]["kept"], m["parts"]["excluded"]) == (CHAIR_PARTS - 1, 1)
    assert m["parts"]["exclude"] == ["CUSHION*"]
    again = run(src, out)
    assert again["parts"]["excluded"] == 1
    assert run(src, out, forget_exclusions=True)["parts"]["excluded"] == 0


def _scaled_chair(generated: Path, path: Path, factor: float) -> Path:
    mesh = trimesh.load(generated / "chair.stl", process=False)
    write_stl(path, np.asarray(mesh.vertices) * factor, np.asarray(mesh.faces), "scaled")
    return path


@pytest.mark.parametrize("unit", ["inch", "m"])
def test_stl_units_warn_and_override(generated: Path, tmp_path: Path, unit: str) -> None:
    src = _scaled_chair(generated, tmp_path / f"chair-{unit}.stl", 1 / UNIT_MM[unit])
    plain = run(src, tmp_path / "plain", p=params(min_part_mm=0))
    assert len(plain["warnings"]) == 1 and f"--units {unit}" in plain["warnings"][0]
    fixed = run(src, tmp_path / "fixed", units=unit)
    assert fixed["warnings"] == []
    reference = run(generated / "chair.stl", tmp_path / "ref")
    assert fixed["size_mm"] == pytest.approx(reference["size_mm"], abs=FLOAT32_TOL)


def _vertices(model_dir: Path) -> np.ndarray:
    return np.asarray(load_model(model_dir).vertices)


def test_up_axis_and_front(generated: Path, tmp_path: Path) -> None:
    mesh = trimesh.load(generated / "chair.stl", process=False)
    v, f = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    run(generated / "chair.stl", tmp_path / "ref")
    expected = _vertices(tmp_path / "ref")
    # the same chair drawn Y-up, and drawn with its front toward +x
    y_up = v @ rotation("y", "-y")  # inverse (transpose) of the import rotation
    write_stl(tmp_path / "y_up.stl", y_up, f, "y_up")
    run(tmp_path / "y_up.stl", tmp_path / "from_y", p=params(up_axis="y"))
    front_x = v @ rotation("z", "x")
    write_stl(tmp_path / "front_x.stl", front_x, f, "front_x")
    run(tmp_path / "front_x.stl", tmp_path / "from_x", p=params(front="x"))
    for d in ("from_y", "from_x"):
        assert _vertices(tmp_path / d) == pytest.approx(expected, abs=FLOAT32_TOL), d


def test_rotations_are_proper() -> None:
    for up in ("z", "y", "x", "-z", "-y", "-x"):
        for front in ("-y", "y", "-x", "x"):
            r = rotation(up, front)
            assert np.linalg.det(r) == pytest.approx(1.0)
            axis = {"x": 0, "y": 1, "z": 2}[up[-1]]
            u = np.zeros(3)
            u[axis] = -1.0 if up.startswith("-") else 1.0
            assert r @ u == pytest.approx([0, 0, 1])


def test_other_mesh_formats(generated: Path, tmp_path: Path) -> None:
    ref = run(generated / "chair.stl", tmp_path / "ref")
    mesh = trimesh.load(generated / "chair.stl", process=False)
    for fmt in ("obj", "ply"):
        path = tmp_path / f"chair.{fmt}"
        mesh.export(path)
        m = run(path, tmp_path / fmt)
        assert np.array(m["bbox_mm"]) == pytest.approx(np.array(ref["bbox_mm"]), abs=FLOAT32_TOL), (
            fmt
        )
        assert m["parts"]["kept"] == ref["parts"]["kept"], fmt


def test_model_glb_round_trip(generated: Path, tmp_path: Path) -> None:
    """model.glb follows glTF (metres, Y up): importing it again gives the same model."""
    run(generated / "chair.stl", tmp_path / "ref")
    again = run(tmp_path / "ref" / "model.glb", tmp_path / "again")
    assert again["source"]["units_detected"] == "m"
    assert again["placement"]["up_axis"] == "y"
    assert _vertices(tmp_path / "again") == pytest.approx(_vertices(tmp_path / "ref"), abs=1e-3)
    # a generic glTF reader sees metres, Y up, standing on y = 0
    scene = trimesh.load(tmp_path / "ref" / "model.glb", force="scene")
    assert scene.bounds[0][1] == pytest.approx(0.0, abs=1e-9)
    assert scene.extents[1] == pytest.approx(0.943, abs=1e-3)


def test_deterministic(generated: Path, tmp_path: Path) -> None:
    for src in ("chair.stl", "chair_assembly.step", "chair_assembly.iges"):
        a, b = tmp_path / "a" / src, tmp_path / "b" / src
        run(generated / src, a)
        run(generated / src, b)
        for f in ("model.glb", "model.json", "parts.json"):
            assert (a / f).read_bytes() == (b / f).read_bytes(), (src, f)


def test_parameters_recorded(generated: Path, tmp_path: Path) -> None:
    out = tmp_path / "chair"
    assert (
        main(["import", str(generated / "chair.stl"), "--out", str(out), "--min-part-mm", "5"]) == 0
    )
    m = json.loads((out / "model.json").read_text())
    assert m["import_parameters"]["import.min_part_mm"] == 5
    assert m["parameter_sources"]["import.min_part_mm"] == "trial"
    assert m["parameter_sources"]["import.deflection_mm"] == "default"


def test_cli_import_and_info(
    generated: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "chair-a12"
    assert main(["import", str(generated / "chair_assembly.step"), "--out", str(out)]) == 0
    assert f"{CHAIR_PARTS} kept" in capsys.readouterr().out
    assert main(["info", str(out)]) == 0
    text = capsys.readouterr().out
    assert "model       chair-a12" in text and "warnings    none" in text


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["missing.step"], "no such file"),
        (["{g}/chair.json"], "unsupported file type"),
        (["{g}/chair.stl", "--min-part-mm", "5000"], "all 6 parts were dropped"),
        (["{g}/chair.stl", "--up", "q"], "must be one of"),
    ],
)
def test_import_errors(
    generated: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    argv = [a.format(g=generated) for a in argv]
    assert main(["import", *argv, "--out", str(tmp_path / "m")]) == 1
    assert message in capsys.readouterr().err


def test_split_bodies_touching_at_a_point() -> None:
    tri = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]], dtype=float)
    parts = split_bodies("p", tri, np.array([[0, 1, 2], [0, 3, 4]]))
    assert [p.path for p in parts] == ["p/1", "p/2"]


def test_matching_rule() -> None:
    assert matching_rule("chair/cushion seat/2", ["cushion*"]) == "cushion*"
    assert matching_rule("chair/Cushion", ["CUSHION"]) == "CUSHION"
    assert matching_rule("chair/seat", ["cushion*"]) is None
    assert matching_rule("chair/hardware/screw M4", ["chair/hardware/*"]) == "chair/hardware/*"


def test_plausibility_warning_names_units() -> None:
    assert plausibility_warning([500, 600, 900], "mm", 200, 6000) is None
    w = plausibility_warning([20, 24, 35], "mm", 200, 6000)
    assert w and "--units cm" in w and "--units inch" in w and "--units m" not in w


def test_2000_part_assembly_under_two_minutes(tmp_path: Path) -> None:
    """M1 acceptance: a detailed assembly (synthetic until real samples exist) in < 2 min."""
    (src,) = write_assembly("chair_hardware_2000", tmp_path)
    start = time.perf_counter()
    m = run(src, tmp_path / "m")
    elapsed = time.perf_counter() - start
    spec = assembly_specs()["chair_hardware_2000"]
    assert m["parts"]["total"] >= 2000
    assert m["parts"]["kept"] == CHAIR_PARTS
    assert m["parts"]["dropped_small"] == spec["screws"] + spec["washers"]
    assert elapsed < 120, f"import took {elapsed:.1f} s"


def _signed_volume(p: Any) -> float:
    tri = p.vertices[p.faces]
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()) / 6


def test_faceted_step_matches_opencascade(generated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The fast reader for meshes saved as STEP gives what OpenCascade gives, orientation too."""
    from coverengine.io import cad
    from coverengine.io.faceted_step import read_faceted_step

    src = generated / "chair_faceted.step"
    fast = read_faceted_step(src)
    assert fast is not None and fast.facets == 72 and fast.mm_per_unit == 1.0
    monkeypatch.setattr(cad, "read_faceted_step", lambda path: None)
    slow = cad.load_cad(
        src,
        PARAMS["import.deflection_mm"],
        PARAMS["import.angular_deflection_deg"],
        PARAMS["import.sew_tolerance_mm"],
    )
    assert len(fast.parts) == len(slow.parts) == 6
    for a, b in zip(
        sorted(fast.parts, key=lambda p: tuple(p.bounds[0])),
        sorted(slow.parts, key=lambda p: tuple(p.bounds[0])),
        strict=True,
    ):
        # OpenCascade's triangles come through 32-bit floats
        assert np.array(a.bounds) == pytest.approx(np.array(b.bounds), abs=1e-4)
        assert _signed_volume(a) == pytest.approx(_signed_volume(b), rel=1e-6)
        assert _signed_volume(a) > 0  # faces point outward


def test_faceted_step_imports_like_the_stl(generated: Path, tmp_path: Path) -> None:
    faceted = run(generated / "chair_faceted.step", tmp_path / "f")
    stl = run(generated / "chair.stl", tmp_path / "s")
    assert faceted["parts"]["kept"] == stl["parts"]["kept"] == 6
    assert np.array(faceted["bbox_mm"]) == pytest.approx(np.array(stl["bbox_mm"]), abs=1e-3)


def test_faceted_reader_declines_curved_cad(generated: Path) -> None:
    from coverengine.io.faceted_step import read_faceted_step

    assert read_faceted_step(generated / "chair_assembly.step") is None  # assembly, cylinders


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # the owner's first real file: a unit named METRE, defined as 1 mm
        (
            b"#13=(CONVERSION_BASED_UNIT('METRE',#20)LENGTH_UNIT()NAMED_UNIT(#21));\n"
            b"#20=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.0),#28);\n"
            b"#28= (NAMED_UNIT(#21)LENGTH_UNIT()SI_UNIT(.MILLI.,.METRE.));\n",
            ("METRE", 1.0),
        ),
        # OpenCascade's inch files: bare value, entity spread over lines
        (
            b"#28 = ( CONVERSION_BASED_UNIT('INCH',#30) LENGTH_UNIT() NAMED_UNIT(\n  #29) );\n"
            b"#30 = LENGTH_MEASURE_WITH_UNIT(25.4,#31);\n"
            b"#31 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n",
            ("INCH", 25.4),
        ),
        (b"#1 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n", ("millimetre", 1.0)),
        (b"#1 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.) );\n", ("metre", 1000.0)),
        (
            b"#1 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n"
            b"#2 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.) );\n",
            None,  # two different units: no single answer
        ),
        (b"#1 = CARTESIAN_POINT('',(0.,0.,0.));\n", None),
    ],
)
def test_step_length_unit(text: bytes, expected: tuple[str, float] | None) -> None:
    from coverengine.io.faceted_step import step_length_unit

    assert step_length_unit(text) == expected


def test_unit_name_contradicting_definition_warns() -> None:
    from coverengine.io.model_io import _cad_units

    u = _cad_units("METRE", 1.0, None)
    assert (u.detected, u.used, u.scale) == ("mm", "mm", 1.0)
    assert "names its unit 'METRE' but defines it as 1 mm" in u.warnings[0]
    fixed = _cad_units("METRE", 1.0, "m")
    assert (fixed.used, fixed.scale, fixed.mm_per_file_unit) == ("m", 1000.0, 1000.0)
