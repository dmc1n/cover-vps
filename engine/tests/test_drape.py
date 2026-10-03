"""The drape simulation (ADR-056): the cloth keeps its lengths, does not go through the
furniture, and folds where it has nowhere else to go."""

import numpy as np
import trimesh
from coverengine import drape
from coverengine.params import Registry

PARAMS = Registry.load(None).resolve(trial={"drape.seconds": 1.0})


def _square(size: float, n: int, z: float) -> drape.Cloth:
    g = np.linspace(-size / 2, size / 2, n)
    xx, yy = np.meshgrid(g, g)
    uv = np.column_stack([xx.ravel(), yy.ravel()])
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = i * n + j, i * n + j + 1, (i + 1) * n + j, (i + 1) * n + j + 1
            faces += [[a, b, d], [a, d, c]]
    f = np.array(faces, dtype=np.int64)
    return drape.sheet(np.column_stack([uv, np.full(len(uv), z)]), f, uv)


def _stretch(c: drape.Cloth, x: np.ndarray) -> np.ndarray:
    ds = np.stack([x[c.faces[:, 1]] - x[c.faces[:, 0]], x[c.faces[:, 2]] - x[c.faces[:, 0]]], 2)
    return np.linalg.svd(ds @ c.rest_inv, compute_uv=False)


def test_a_tablecloth_falls_on_a_box_keeps_its_lengths_and_folds_over_the_edges() -> None:
    cloth = _square(1200.0, 25, 520.0)  # 1.2 m square, 20 cm above a 60 cm box of 50 cm high
    box = trimesh.creation.box(extents=(600.0, 600.0, 500.0))
    box.apply_translation((0, 0, 250.0))
    frames, report = drape.run(cloth, drape.Contact([box]), PARAMS, log=lambda *_: None)
    x = frames[-1].astype(np.float64)
    s = _stretch(cloth, x)
    assert np.percentile(s[:, 0], 99) < 1.03  # the fabric hardly stretches (< 3 %)
    middle = np.linalg.norm(x[:, :2], axis=1) < 200
    assert np.all(x[middle, 2] > 500.0)  # it lies on the box, not through it
    edge = (np.abs(cloth.x[:, 0]) > 580) & (np.abs(cloth.x[:, 1]) < 100)  # the edges' middles
    assert np.all(x[edge, 2] < 250.0)  # hang down the sides: 30 cm over a 50 cm high box
    assert np.all(np.abs(x[edge, 0]) < 360.0)  # close to the box's side (at 30 cm)
    assert report["max_fold_deg"] > float(PARAMS["drape.fold_deg"])  # the corners fold


def test_the_same_input_gives_the_same_drape() -> None:
    box = trimesh.creation.box(extents=(400.0, 400.0, 300.0))
    box.apply_translation((0, 0, 150.0))
    a, _ = drape.run(_square(600.0, 11, 320.0), drape.Contact([box]), PARAMS, lambda *_: None)
    b, _ = drape.run(_square(600.0, 11, 320.0), drape.Contact([box]), PARAMS, lambda *_: None)
    assert np.array_equal(a[-1], b[-1])


def test_style3d_drapes_the_tablecloth_with_canvas_like_stretch() -> None:
    """ADR-058: Newton's garment solver on the same tablecloth: on the box, down the sides,
    and hardly any stretch (a woven fabric)."""
    from coverengine import drape_style3d

    params = Registry.load(None).resolve(trial={"drape.seconds": 1.0, "drape.engine": "style3d"})
    cloth = _square(1200.0, 25, 520.0)
    box = trimesh.creation.box(extents=(600.0, 600.0, 500.0))
    box.apply_translation((0, 0, 250.0))
    frames, extra = drape_style3d.run(cloth, [box], params, log=lambda *_: None)
    x = frames[-1].astype(np.float64)
    assert extra["engine"] == "style3d"
    assert np.percentile(_stretch(cloth, x)[:, 0], 99) < 1.01  # under 1 % stretch
    middle = np.linalg.norm(x[:, :2], axis=1) < 200
    assert np.all(x[middle, 2] > 490.0)  # on the box
    edge = (np.abs(cloth.x[:, 0]) > 580) & (np.abs(cloth.x[:, 1]) < 100)
    assert np.all(x[edge, 2] < 400.0)  # the sides come down
