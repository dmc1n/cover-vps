"""Rain on a cover (ADR-049): hollows hold water, flat parts are found, drops run off."""

import json
from pathlib import Path

import numpy as np
import trimesh
from coverengine.io.model_io import glb_bytes
from coverengine.params import Registry
from coverengine.rain import RAIN_JSON, fill, simulate


def _surface(dip_mm: float, slope_deg: float) -> trimesh.Trimesh:
    """A 1.2 x 1.2 m top 800 mm high, sloping to the front, with a hollow in the middle, and
    walls down to the floor."""
    n = 49
    xs = np.linspace(-600, 600, n)
    gx, gy = np.meshgrid(xs, xs, indexing="ij")
    top = 800 + np.tan(np.radians(slope_deg)) * gy
    top -= dip_mm * np.exp(-(gx**2 + gy**2) / (2 * 180.0**2))
    v = np.column_stack([gx.ravel(), gy.ravel(), top.ravel()])
    f = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = i * n + j, (i + 1) * n + j, (i + 1) * n + j + 1, i * n + j + 1
            f += [[a, b, c], [a, c, d]]
    m = trimesh.Trimesh(v, np.array(f), process=True)
    walls = []
    box = trimesh.creation.box((1200, 1200, 700))
    box.apply_translation((0, 0, 350))
    keep = np.abs(box.face_normals[:, 2]) < 0.5  # the four walls
    walls.append(trimesh.Trimesh(box.vertices, box.faces[keep]))
    return trimesh.util.concatenate([m, *walls])


def _model(tmp_path: Path, cover: trimesh.Trimesh) -> Path:
    d = tmp_path / "m"
    d.mkdir()
    under = trimesh.creation.box((1100, 1100, 600))
    under.apply_translation((0, 0, 300))
    (d / "model.glb").write_bytes(glb_bytes([("furniture", under)]))
    (d / "hull.glb").write_bytes(glb_bytes([("hull", cover)]))
    return d


def test_fill_finds_a_hollow() -> None:
    z = np.full((9, 9), 10.0)
    z[3:6, 3:6] = 4.0
    z[0, :] = np.nan  # outside the cover
    filled = fill(z)
    assert np.allclose(filled[3:6, 3:6], 10.0)  # filled up to the rim


def test_a_hollow_holds_water_and_sags(tmp_path: Path) -> None:
    params = Registry.load(None).resolve()
    d = _model(tmp_path, _surface(dip_mm=60, slope_deg=2))
    r = simulate(d, params, use_ai=False)
    assert r["ponds"], r
    pond = r["ponds"][0]
    assert pond["max_depth_mm"] > 5 and pond["volume_l"] > 0.1
    assert pond["volume_with_sag_l"] >= pond["volume_l"]  # the water's weight deepens it
    assert not r["dry"]
    assert json.loads((d / RAIN_JSON).read_text())["drops"]


def test_a_sloping_top_is_dry(tmp_path: Path) -> None:
    params = Registry.load(None).resolve()
    d = _model(tmp_path, _surface(dip_mm=0, slope_deg=8))
    r = simulate(d, params, use_ai=False)
    assert not r["ponds"] and r["flat_area_m2"] == 0 and r["dry"]
    assert r["exits"]["front"] > r["exits"]["back"]  # it runs off the low side
