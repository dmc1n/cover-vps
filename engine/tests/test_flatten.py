import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely
import trimesh
from coverengine.cli import main
from coverengine.export.pattern import write_all
from coverengine.flatten.pattern import build_patterns, pattern_set
from coverengine.flatten.solve import flatten, singular_values
from coverengine.hull.build import build_hull, write_hull
from coverengine.io.model_io import import_model
from coverengine.params import Registry
from coverengine.params.registry import repo_root
from coverengine.seams.build import cut_cover, write_cut
from coverengine.seams.cut import CutMesh, Seam, apply, seam_edges, unzip
from coverengine.testshapes import build_all
from coverengine.testshapes import write_all as write_shapes
from test_hull import HULL
from test_import import PARAMS as IMPORT_PARAMS
from test_seams import SEAMS

FLAT = {
    "flatten.solver": "slim",
    "flatten.iterations": 50,
    "flatten.slim_tolerance": 1e-7,
    "flatten.max_triangles": 50000,
    "flatten.panel_tolerance_mm": 2.5,
    "flatten.fabric_compensation": False,
    "flatten.stretch_quantile": 0.995,
    "fabric.max_allowed_stretch_pct": 2.0,
    "pen.label_height_mm": 15,
    "pen.tick_length_mm": 10,
    "pen.tick_spacing_mm": 300,
    "export.sheet_spacing_mm": 20,
}
GOLDEN = repo_root() / "testdata" / "golden" / "flatten.json"
SHAPES = {s.name: s for s in build_all()}
COVERS = {"box_with_legs": {}, "chair": {}, "slatted_table": {"hull.support": "balloon"}}


def params(**overrides: Any) -> Any:
    return Registry.load().resolve(trial={**IMPORT_PARAMS, **HULL, **SEAMS, **FLAT, **overrides})


def _cut_once(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """An open ring cut open along y = 0 on the +x side, so it lies flat as one piece."""
    seam = Seam(
        "c",
        "corner",
        field=lambda p: p[:, 1],
        faces=lambda c: np.asarray(c.mesh.triangles_center)[:, 0] > 0,
    )
    cut = apply(CutMesh(mesh, []), seam, 0.5)
    return unzip(cut.mesh, seam_edges(cut)["c"])


def _surface(name: str) -> trimesh.Trimesh:
    s = SHAPES[name]
    mesh = trimesh.Trimesh(s.vertices, s.faces, process=True)
    return _cut_once(mesh) if name in ("cylinder", "cone") else mesh


@pytest.mark.parametrize("name", ["plate", "cylinder", "cone"])
def test_developable_surfaces_flatten_exactly(name: str) -> None:
    flat = flatten(_surface(name), "slim", 50, 1e-7)
    f = flat.faces
    l3 = np.linalg.norm(flat.vertices[f[:, 0]] - flat.vertices[f[:, 1]], axis=1)
    l2 = np.linalg.norm(flat.uv[f[:, 0]] - flat.uv[f[:, 1]], axis=1)
    assert np.abs(l2 / l3 - 1).max() < 0.0005  # under 0.05 %


def test_cylinder_unrolls_to_its_circumference() -> None:
    c = SHAPES["cylinder"]
    flat = flatten(_surface("cylinder"), "slim", 50, 1e-7)
    ring = c.vertices[np.isclose(c.vertices[:, 2], 0.0)]
    ring = ring[np.argsort(np.arctan2(ring[:, 1], ring[:, 0]))]
    circumference = float(
        np.linalg.norm(np.diff(np.vstack([ring, ring[:1]]), axis=0), axis=1).sum()
    )
    width, height = np.ptp(flat.uv, axis=0)
    assert width == pytest.approx(circumference, rel=5e-4)
    assert height == pytest.approx(600.0, rel=5e-4)  # and "up" points to +Y


@pytest.mark.parametrize("name", ["sphere_octant", "saddle"])
def test_curved_surfaces_match_golden_stretch(name: str) -> None:
    import os

    flat = flatten(_surface(name), "slim", 50, 1e-7)
    s1, s2, _ = singular_values(flat.vertices, flat.faces, flat.uv)
    stretch = float(np.maximum(s1 - 1, 1 - s2).max()) * 100
    golden = json.loads(GOLDEN.read_text()) if GOLDEN.is_file() else {}
    if os.environ.get("COVER_UPDATE_GOLDEN") == "1":
        golden[name] = round(stretch, 3)
        GOLDEN.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")
    assert name in golden, "run make golden"
    assert stretch == pytest.approx(golden[name], abs=0.5)


def test_200k_triangle_panel_under_3_seconds() -> None:
    nu, nv = 500, 200
    u, v = np.meshgrid(
        np.linspace(0, 1.5 * np.pi, nu + 1), np.linspace(0, 600, nv + 1), indexing="ij"
    )
    verts = np.column_stack([400 * np.cos(u.ravel()), 400 * np.sin(u.ravel()), v.ravel()])
    idx = np.arange((nu + 1) * (nv + 1)).reshape(nu + 1, nv + 1)
    a, b, c, d = (
        idx[:-1, :-1].ravel(),
        idx[1:, :-1].ravel(),
        idx[1:, 1:].ravel(),
        idx[:-1, 1:].ravel(),
    )
    faces = np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])
    mesh = trimesh.Trimesh(verts, faces, process=False)
    assert len(mesh.faces) >= 200_000
    start = time.perf_counter()
    flat = flatten(mesh, "slim", 50, 1e-7, max_triangles=50_000)
    assert time.perf_counter() - start < 3.0
    width, height = np.ptp(flat.uv, axis=0)
    assert height == pytest.approx(600.0, rel=1e-3)  # still the right size
    assert width == pytest.approx(1.5 * np.pi * 400, rel=1e-3)


@pytest.fixture(scope="module")
def covers(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("flatten")
    write_shapes(root / "generated")
    out: dict[str, Any] = {"root": root}
    for name, extra in COVERS.items():
        import_model(root / "generated" / f"{name}.stl", root / name, params())
        write_hull(root / name, build_hull(root / name, params(**extra)))
        write_cut(root / name, cut_cover(root / name, params()))
        patterns, report = build_patterns(root / name, params())
        doc, warnings = pattern_set(root / name, params(), patterns, report)
        out[name] = (patterns, doc, warnings)
    return out


@pytest.mark.parametrize("name", list(COVERS))
def test_cover_patterns(covers: dict[str, Any], name: str) -> None:
    patterns, doc, _ = covers[name]
    assert len(patterns) == 5
    for p in doc["panels"]:
        assert p["stretch"]["quantile_pct"] <= 2.0, p["name"]
        assert p["fits_roll"]
        outline = shapely.Polygon(p["outline_mm"])
        assert outline.is_valid and outline.exterior.is_simple, p["name"]
        for e in p["edges"]:
            if e["kind"] == "seam":
                # the two sides agree to 2 mm or 0.3 % (a tent's peak cannot lie flat exactly;
                # the rest is recorded as ease)
                limit = max(2.0, 0.003 * e["length_3d_mm"])
                assert e["ease_mm"] <= limit, (p["name"], e["seam"])
                assert e["length_2d_mm"] == pytest.approx(e["length_3d_mm"], rel=5e-3)


def test_skirt_panels_have_the_hem_at_the_bottom(covers: dict[str, Any]) -> None:
    patterns, _, _ = covers["box_with_legs"]
    for p in patterns:
        if not p.name.startswith("skirt"):
            continue
        hem = [e for e in p.edges if e["kind"] == "hem"]
        assert len(hem) == 1
        hem_y = p.outline[hem[0]["_points"], 1].mean()
        assert hem_y == pytest.approx(p.outline[:, 1].min(), abs=1.0)  # UP points away from it


def test_matching_marks_pair_across_seams(covers: dict[str, Any]) -> None:
    _, doc, _ = covers["box_with_legs"]
    pairs: dict[str, int] = {}
    for p in doc["panels"]:
        for m in p["pen"]:
            if m["type"] == "tick":
                pairs[m["pair"]] = pairs.get(m["pair"], 0) + 1
    assert pairs and all(n == 2 for n in pairs.values())  # every mark has its partner


def test_exports_are_deterministic(covers: dict[str, Any], tmp_path: Path) -> None:
    patterns, _, _ = covers["chair"]
    for out in ("a", "b"):
        (tmp_path / out).mkdir()
        write_all(tmp_path / out, patterns, params())
    for f in ("pattern.dxf", "pattern.svg", "pattern-stretch.svg"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f
    again, report = build_patterns(covers["root"] / "chair", params())
    one = pattern_set(covers["root"] / "chair", params(), again, report)[0]
    assert json.dumps(one, sort_keys=True) == json.dumps(covers["chair"][1], sort_keys=True)


def test_cli_run_and_diff(
    covers: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = covers["root"] / "generated" / "chair.stl"
    assert main(["run", str(src), "--out", str(tmp_path / "a")]) == 0
    for f in ("model.glb", "hull.glb", "panels.json", "pattern.dxf", "pattern.svg", "pattern.json"):
        assert (tmp_path / "a" / f).is_file(), f
    assert (
        main(["run", str(src), "--out", str(tmp_path / "b"), "--set", "hull.clearance_mm=20"]) == 0
    )
    capsys.readouterr()
    assert (
        main(["diff", str(tmp_path / "a" / "pattern.json"), str(tmp_path / "b" / "pattern.json")])
        == 0
    )
    text = capsys.readouterr().out
    assert "hull.clearance_mm" in text and "panel(s) changed" in text
    assert not text.strip().endswith("0 panel(s) changed by more than 1 mm")
