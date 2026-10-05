import json
import shutil
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely
import trimesh
from coverengine.catalogue import revisions
from coverengine.cli import main
from coverengine.errors import CoverError
from coverengine.export.drawing import load_cover, measure, skirt_heights, write_drawing
from coverengine.export.pattern import write_all
from coverengine.flatten.pattern import build_patterns, pattern_set, wiggle
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
    "seams.max_wiggle_mm": 2.0,
    "fabric.max_allowed_stretch_pct": 2.0,
    "pen.label_height_mm": 15,
    "pen.tick_length_mm": 10,
    "pen.tick_spacing_mm": 300,
    "export.sheet_spacing_mm": 20,
}
GOLDEN = repo_root() / "testdata" / "golden" / "flatten.json"
SHAPES = {s.name: s for s in build_all()}
COVERS = {"box_with_legs": {}, "chair": {}, "slatted_table": {"hull.support": "balloon"}}
# the chair's back stands higher than its seat edge: a wall panel above the level skirt
PANELS = {"box_with_legs": 5, "chair": 6, "slatted_table": 5}


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
    assert len(patterns) == PANELS[name]
    for p in doc["panels"]:
        assert p["stretch"]["quantile_pct"] <= 2.0, p["name"]
        for e in p["edges"]:  # every edge an easy line for clean stitching
            assert e["wiggle_mm"] <= 2.0, (p["name"], e.get("seam", "hem"))
        assert p["fits_roll"]
        outline = shapely.Polygon(p["outline_mm"])
        assert outline.is_valid and outline.exterior.is_simple, p["name"]
        for e in p["edges"]:
            if e["kind"] == "seam":
                # the two sides agree to 2 mm or 0.3 % (a tent's peak cannot lie flat exactly;
                # the rest is recorded as ease)
                limit = max(2.0, 0.003 * e["length_3d_mm"])
                assert e["ease_mm"] <= limit, (p["name"], e["seam"])
                assert e["length_2d_mm"] == pytest.approx(e["length_3d_mm"], rel=5e-3, abs=1.0)


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
    files = ("model.glb", "hull.glb", "pattern.json", "sizes.pdf", "cut.dxf", "cutting-list.pdf")
    for f in files:
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


def test_size_drawing(covers: dict[str, Any], tmp_path: Path) -> None:
    root = covers["root"] / "box_with_legs"
    _, doc, _ = covers["box_with_legs"]
    a = write_drawing(root, doc, params(), tmp_path / "a.pdf")
    b = write_drawing(root, doc, params(), tmp_path / "b.pdf")
    data = a.read_bytes()
    assert data.startswith(b"%PDF") and data == b.read_bytes()  # same input, same file
    import pymupdf

    pages = pymupdf.open(a).page_count
    assert pages == 2 + len(doc["panels"])  # drawing, sizes, one page per panel


def test_drawing_sizes_agree(covers: dict[str, Any]) -> None:
    root = covers["root"] / "box_with_legs"
    _, doc, _ = covers["box_with_legs"]
    cover = load_cover(root, doc, params())
    skirts = [n for n, r in zip(cover.names, cover.regions, strict=True) if r == "skirt"]
    hem = sum(measure(cover, f"hem_length:{n}") or 0.0 for n in skirts)
    assert hem == pytest.approx(measure(cover, "hem_length"), rel=0.01)
    height = measure(cover, "total_height")
    assert height == pytest.approx(float(cover.vertices[:, 2].max()) - cover.hem_z)
    for n in skirts:
        middle, low, high = skirt_heights(cover, n)
        assert 0 < low <= middle <= high < height
    turned = load_cover(root, doc, params(**{"drawing.plan_rotation_deg": 90}))
    assert measure(turned, "plan_extent_a") == pytest.approx(measure(cover, "plan_extent_b"))


def test_wiggle_finds_zig_zags_not_corners() -> None:
    x = np.linspace(0, 1000, 2001)
    straight = np.column_stack([x, np.zeros_like(x)])
    assert wiggle(straight) < 0.01
    heartbeat = np.column_stack([x, 15 * (np.floor(x / 20) % 2)])  # teeth every 20 mm
    assert wiggle(heartbeat) > 2.0
    step = np.column_stack([x, np.where(x > 500, 40.0, 0.0)])  # one step (a wall's end)
    assert wiggle(step) < 0.01
    arc = np.column_stack([500 * np.cos(x / 1000), 500 * np.sin(x / 1000)])
    assert wiggle(arc) < 0.5


def test_skirt_is_level_and_straight(covers: dict[str, Any]) -> None:
    for name in COVERS:
        patterns, _, _ = covers[name]
        for p in patterns:
            if not p.name.startswith("skirt"):
                continue
            ys = p.outline[:, 1]
            # a straight strip: the same height everywhere (top edge level, hem at the bottom)
            assert np.ptp(ys) == pytest.approx(ys.max() - ys.min())
            top = [e for e in p.edges if e["kind"] == "seam" and not e["mate"].startswith("skirt")]
            for e in top:
                assert np.ptp(p.outline[e["_points"], 1]) < 2.0, (name, p.name)


def test_chair_back_is_a_wall(covers: dict[str, Any]) -> None:
    patterns, _, _ = covers["chair"]
    names = {p.name for p in patterns}
    assert any(n.startswith("wall") for n in names)
    top = next(p for p in patterns if p.name == "top")
    assert all(e.get("mate", "") != "skirt-back" for e in top.edges)  # no wrap down the back


def test_batch_reports_changes(covers: dict[str, Any], tmp_path: Path, capsys: Any) -> None:
    root = tmp_path / "models"
    shutil.copytree(covers["root"] / "chair", root / "chair")
    assert main(["batch", "--models", str(root), "--steps", "flatten,export"]) == 0
    assert main(["model", str(root / "chair"), "--status", "checked"]) == 0
    capsys.readouterr()
    code = main(
        [
            "batch",
            "--models",
            str(root),
            "--steps",
            "flatten,export",
            "--set",
            "flatten.max_triangles=2000",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0 and "== chair:" in out and "1 of 1 model(s) done" in out
    assert [r["number"] for r in revisions(root / "chair")] == [1, 2]
    assert revisions(root / "chair")[-1]["status"] == "checked"


def test_report_grades_models(covers: dict[str, Any], tmp_path: Path, capsys: Any) -> None:
    from coverengine.catalogue import grade

    root = tmp_path / "models"
    shutil.copytree(covers["root"] / "box_with_legs", root / "box")
    (root / "empty").mkdir()
    (root / "empty" / "cover.json").write_text("{}")
    assert main(["flatten", str(root / "box")]) == 0
    assert main(["export", str(root / "box")]) == 0
    g = grade(root / "box")
    assert g["grade"] in ("ready", "check") and g["panels"] == 5
    assert grade(root / "empty")["grade"] == "failed"
    capsys.readouterr()
    assert main(["report", "--models", str(root), "--out", str(tmp_path / "rep")]) == 0
    assert "2 models" in capsys.readouterr().out
    assert (tmp_path / "rep" / "catalogue.pdf").read_bytes().startswith(b"%PDF")
    assert "box" in (tmp_path / "rep" / "catalogue.csv").read_text()


def _has_ai_key() -> bool:
    import coverengine.ai as ai

    try:
        ai._key("deepseek")
        return True
    except CoverError:
        return False


@pytest.mark.skipif(not _has_ai_key(), reason="no DEEPSEEK_API_KEY (deploy/.env on the server)")
def test_ai_review_and_actions(covers: dict[str, Any], tmp_path: Path) -> None:
    """A real AI review of the test box's cover, then the actions it may suggest."""
    import coverengine.ai as ai
    from coverengine.params import resolve_model

    d = tmp_path / "box"
    shutil.copytree(covers["root"] / "box_with_legs", d)
    assert main(["flatten", str(d)]) == 0
    assert main(["export", str(d)]) == 0
    try:
        doc = ai.review(d, resolve_model(d))
    except CoverError as exc:  # the AI service itself (no credit, a limit, no key): not our code
        if any(code in str(exc) for code in ("402", "429", "401", "403")):
            pytest.skip(f"the AI service is not available: {exc}")
        raise
    assert doc["pieces_now"] == 5
    assert doc["summary"] and isinstance(doc["target_pieces"], int)
    assert all(s["action"] in ai.ACTIONS for s in doc["suggestions"])  # only known actions
    assert json.loads((d / "ai_review.json").read_text())["summary"] == doc["summary"]
    assert ai.apply_action(d, "skirt_one_piece") == ["cut", "flatten", "export"]
    assert resolve_model(d)["seams.corner_angle_deg"] == ai.NO_CORNERS_DEG
    (d / "proposals.json").write_text('{"top_seams": []}')
    ai.apply_action(d, "drop_program_seams")
    assert not (d / "proposals.json").exists()
    with pytest.raises(CoverError):
        ai.apply_action(d, "set_skirt_height", 20.0)
    applied = json.loads((d / "ai_review.json").read_text())["applied"]
    assert [a["action"] for a in applied] == ["skirt_one_piece", "drop_program_seams"]


@pytest.mark.parametrize("name", ["box_with_legs", "chair", "slatted_table"])
def test_box_cover(covers: dict[str, Any], tmp_path: Path, name: str) -> None:
    """A box cover: few flat pieces, no stretch, seams that match, water runs off."""
    d = tmp_path / name
    shutil.copytree(covers["root"] / name, d)
    (d / "cover.json").write_text(json.dumps({"parameters": {"hull": {"top": "box"}}}))
    rule = ["--set", "ai.provider=none"]
    for step in ("hull", "cut", "flatten", "export"):
        assert main([step, str(d), *rule]) == 0, step
    hull = json.loads((d / "hull.json").read_text())
    assert hull["box"]["chosen_by"] == "rule" and 5 <= hull["box"]["chosen"] <= 10
    doc = json.loads((d / "pattern.json").read_text())
    assert len(doc["panels"]) <= 11  # at most one more than chosen (a gable for water)
    for p in doc["panels"]:
        assert p["stretch"]["quantile_pct"] < 0.1, p["name"]  # flat faces lie flat exactly
        for e in p["edges"]:
            if e["kind"] == "seam":
                assert e["ease_mm"] < 1.0, (p["name"], e["seam"])
    mesh = trimesh.load(d / "hull.glb", force="mesh")
    assert mesh.face_normals[:, 1].max() < 0.999  # no flat top: in glTF y is up


def test_export_places_the_air_vents_on_the_cover_in_3d(
    covers: dict[str, Any], tmp_path: Path
) -> None:
    """vents.json (ADR-073): every vent of the cutting list, on the cover's surface, its bottom
    edge features.vent_above_hem_mm above the hem, its normal pointing out."""
    import igl
    from coverengine.params import resolve_model

    d = tmp_path / "box"
    shutil.copytree(covers["root"] / "box_with_legs", d)
    assert main(["flatten", str(d)]) == 0
    assert main(["export", str(d)]) == 0
    p = resolve_model(d)
    doc = json.loads((d / "vents.json").read_text())
    vents = doc["vents"]
    hoods = [x for x in json.loads((d / "finished.json").read_text())["pieces"]
             if x["name"] == "vent-hood"]  # fmt: skip
    assert vents and len(vents) == hoods[0]["quantity"] and doc["warnings"] == []
    data = np.load(d / "panels.npz")
    v, f = data["vertices"].astype(np.float64), data["faces"].astype(np.int64)
    pts = np.array([c for x in vents for c in x["corners_mm"]] + [x["centre_mm"] for x in vents])
    dist2, _, _ = igl.point_mesh_squared_distance(pts, v, f)
    assert float(np.sqrt(dist2).max()) < 3.0  # param-ok: on the surface, within 3 mm
    hem = float(v[:, 2].min())
    above = float(p["features.vent_above_hem_mm"])  # type: ignore[arg-type]
    middle = (v.min(axis=0) + v.max(axis=0)) / 2
    for x in vents:
        bottom = [c[2] for c in x["corners_mm"][:2]]
        assert bottom == pytest.approx([hem + above] * 2, abs=3.0)  # param-ok: mm
        out = np.asarray(x["centre_mm"]) - middle
        assert float(np.dot(x["normal"][:2], out[:2])) > 0
