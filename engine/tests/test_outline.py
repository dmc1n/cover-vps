"""A box cover's plan from the furniture seen from above (ADR-107): round tables get a round
cover, organic outlines are followed, chairs get no chair space."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
import shapely
import trimesh
from coverengine.cli import main as cover
from coverengine.hull import outline
from coverengine.io.model_io import import_model, load_model
from coverengine.params import Registry


def test_a_chair_is_no_table() -> None:
    """Rens, 8 Oct 2026: six dining chairs got chair space behind and before them ("dining" is
    in their name), a cover twice as deep as the chair."""
    from coverengine.hull.chairs import chair_space, kind

    params = Registry.load(None).resolve()
    assert kind(Path("suns-dining-pemba-dining-chair"), 894, params) == "none"
    assert kind(Path("suns-antas-collection-2021-diningchair"), 939, params) == "none"
    assert kind(Path("suns-dining-table-erice-240"), 764, params) == "dining"
    # a "dining" model whose highest part is a 90 mm rail (a backrest), not a table top
    rail = np.array([[x, y, 760.0] for x in (-280, 280) for y in (300, 390)])
    seat = np.array([[x, y, 450.0] for x in (-280, 280) for y in (-250, 300)])
    blocks, report = chair_space(np.vstack([rail, seat]), Path("x-dining-x"), params)
    assert blocks == [] and report is None


def test_roundness_tells_a_circle_from_an_octagon_and_a_square() -> None:
    params = Registry.load(None).resolve()
    least = float(params["hull.round_fill"])  # type: ignore[arg-type]
    circle = shapely.Point(0, 0).buffer(700, quad_segs=32)
    octagon = shapely.Polygon(
        [(700 * math.cos(a), 700 * math.sin(a)) for a in np.arange(8) * math.pi / 4]
    )
    square = shapely.box(-500, -500, 500, 500)
    assert outline.roundness(circle)[0] >= least
    assert outline.roundness(octagon)[0] < least
    assert outline.roundness(square)[0] < least


def _model(tmp: Path, name: str, mesh: trimesh.Trimesh) -> Path:
    src = tmp / f"{name}.stl"
    mesh.export(src)
    d = tmp / "models" / name
    import_model(src, d, Registry.load().resolve())
    (d / "cover.json").write_text(
        json.dumps({"format_version": 1, "parameters": {"hull": {"top": "box"}}})
    )
    return d


@pytest.mark.parametrize("radius", [450.0, 800.0])
def test_a_round_table_gets_a_round_top_and_a_round_skirt(tmp_path: Path, radius: float) -> None:
    """Rens, 8 Oct 2026, 18 round tables: "round in top view, not square or octagonal". The
    cover is a cylinder round the table and its chairs, with a cone on top that sheds water,
    the skirt seam level, every piece within the roll."""
    params = Registry.load().resolve()
    c = float(params["hull.clearance_mm"])  # type: ignore[arg-type]
    room = float(params["hull.chair_room_mm"])  # type: ignore[arg-type]
    hem = float(params["hull.hem_height_mm"])  # type: ignore[arg-type]
    top = trimesh.creation.cylinder(radius=radius, height=40, sections=96)
    top.apply_translation((0, 0, 750))
    leg = trimesh.creation.cylinder(radius=50, height=730, sections=24)
    leg.apply_translation((0, 0, 365))
    d = _model(tmp_path, "round-table", trimesh.util.concatenate([top, leg]))
    for step in ("hull", "cut", "flatten"):
        assert cover([step, str(d)]) == 0, step
    hull = json.loads((d / "hull.json").read_text())
    plan = hull["box"]["plan"]
    assert plan["kind"] == "round"
    assert hull["drainage"]["drains"]  # rule 12
    assert plan["slope_deg"] >= float(params["hull.min_slope_deg"])  # type: ignore[arg-type]
    mesh = load_model(d / "hull.glb")
    v = np.asarray(mesh.vertices)
    r = np.linalg.norm(v[:, :2], axis=1)
    want = radius + room + c  # the chairs all round, 33 cm beyond the edge (owner)
    low = v[:, 2] < hem + 1
    assert np.allclose(r[low], want, atol=2.0)  # round seen from above
    rim = v[np.abs(r - want) < 1.0][:, 2].max()
    walls = np.abs(np.asarray(mesh.face_normals)[:, 2]) < 0.1
    assert np.allclose(np.asarray(mesh.triangles_center)[walls][:, 2].max(), rim, atol=40)
    # the skirt's top edge at one height (rule 13): every skirt point below the rim lies on it
    top_of_skirt = v[(np.abs(r - want) < 1.0)][:, 2]
    assert np.isclose(top_of_skirt.max(), rim)
    pattern = json.loads((d / "pattern.json").read_text())
    usable = float(params["roll.usable_width_mm"])  # type: ignore[arg-type]
    assert all(p["flat_width_mm"] <= usable for p in pattern["panels"])  # rule 5
    assert sum(p["name"].startswith("top") for p in pattern["panels"]) == plan["top_pieces"]
    assert max(p["stretch"]["max_pct"] if "stretch" in p else 0 for p in pattern["panels"]) < 1


def test_an_organic_outline_is_followed_bays_and_all(tmp_path: Path) -> None:
    """Rens, 8 Oct 2026, 12 organic lounges: "follow the (round) outline from the top view".
    A kidney-shaped sofa: the box spanned its bay; now the walls follow the outline (the bay
    stays open), the top is still the box's, so water runs off."""
    params = Registry.load().resolve()
    c = float(params["hull.clearance_mm"])  # type: ignore[arg-type]
    hem = float(params["hull.hem_height_mm"])  # type: ignore[arg-type]
    body = shapely.union_all(
        [
            shapely.Point(-600, 0).buffer(400),
            shapely.Point(600, 0).buffer(400),
            shapely.box(-600, -400, 600, 400),
        ]  # fmt: skip
    ).difference(shapely.Point(0, -1150).buffer(900))
    sofa = trimesh.creation.extrude_polygon(body, 420)
    sofa.apply_translation((0, 0, 30))
    d = _model(tmp_path, "kidney-sofa", sofa)
    for step in ("hull", "cut", "flatten"):
        assert cover([step, str(d)]) == 0, step
    hull = json.loads((d / "hull.json").read_text())
    assert hull["box"]["plan"]["kind"] == "follow"
    assert hull["drainage"]["drains"]  # rule 12
    plan = shapely.Polygon(hull["box"]["plan"]["outline_mm"])
    low = np.asarray(load_model(d / "hull.glb").vertices)
    low = low[low[:, 2] < hem + 1][:, :2]
    assert float(shapely.distance(plan.exterior, shapely.points(low)).max()) < 1.0  # the hem on it
    assert not plan.contains(shapely.Point(0, -320))  # the bay is not spanned
    # nowhere further out than the clearance plus two cells of the footprint's grid, but for the
    # rounding of the inner corners (smooth seams)
    cell = float(params["hull.plan_cell_mm"])  # type: ignore[arg-type]
    r = float(params["hull.plan_round_mm"])  # type: ignore[arg-type]
    ring = np.asarray(plan.exterior.coords)
    allowed = body.buffer(c + 2 * cell).buffer(r).buffer(-r)
    reach = shapely.distance(allowed, shapely.points(ring))
    assert float(np.max(reach)) < 1.0
    mesh = load_model(d / "hull.glb")
    nz = np.abs(np.asarray(mesh.face_normals)[:, 2])
    assert np.all((nz < 1e-3) | (nz > 0.1))  # the walls stand straight down
    pattern = json.loads((d / "pattern.json").read_text())
    usable = float(params["roll.usable_width_mm"])  # type: ignore[arg-type]
    assert all(p["flat_width_mm"] <= usable for p in pattern["panels"])
