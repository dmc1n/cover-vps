"""The drape simulation (ADR-056): the cloth keeps its lengths, does not go through the
furniture, and folds where it has nowhere else to go."""

import numpy as np
import trimesh
from coverengine import drape
from coverengine.params import Registry

PARAMS = Registry.load(None).resolve(
    trial={"drape.seconds": 1.0, "drape.hem": "free"}
)  # a cloth, no hem


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

    params = Registry.load(None).resolve(
        trial={"drape.seconds": 1.0, "drape.settle_seconds": 1.0, "drape.engine": "style3d",
               "drape.hem": "free"}
    )  # fmt: skip
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
    assert extra["end_speed_mm_s"] < 100.0  # settling: it has come (nearly) to rest


def test_the_seam_hinges_are_found_between_two_pieces() -> None:
    """ADR-063: the bending hinges on the line where two pieces are sewn get the seam's
    stiffness, the others keep the fabric's."""
    from coverengine import drape_style3d

    cloth = _square(400.0, 5, 0.0)  # 4 x 4 squares, two triangles each
    centre = cloth.x[cloth.faces].mean(axis=1)
    piece = (centre[:, 0] > 0).astype(np.int64)  # sewn along x = 0
    hinges = [[0, 0, int(a), int(b)] for a, b in {tuple(sorted(e)) for f in cloth.faces
              for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0]))}]  # fmt: skip
    on = drape_style3d.seam_hinges(cloth.faces, piece, np.array(hinges))
    seam = [h for h, o in zip(hinges, on, strict=True) if o]
    assert len(seam) == 4  # the four edges on x = 0
    assert all(abs(cloth.x[h[2], 0]) < 1e-6 and abs(cloth.x[h[3], 0]) < 1e-6 for h in seam)


def test_a_held_hem_stays_where_it_is() -> None:
    """ADR-060: with the hem held (the drawcord pulled tight), the bottom edge does not ride
    up, even where the cloth above it sinks."""
    params = Registry.load(None).resolve(trial={"drape.seconds": 0.5, "drape.hem": "held"})
    cloth = _square(800.0, 17, 400.0)
    low = cloth.x[:, 1] < -390  # one edge a little lower: that is the "hem"
    cloth.x[low, 2] = 380.0
    box = trimesh.creation.box(extents=(200.0, 200.0, 100.0))
    box.apply_translation((0, 0, 50.0))
    frames, _ = drape.run(cloth, drape.Contact([box]), params, log=lambda *_: None)
    hem = drape.hem_points(cloth, float(params["drape.hem_band_mm"]))
    assert len(hem) > 0
    start = cloth.x[hem] + 0.0
    moved = np.linalg.norm(frames[-1].astype(np.float64)[hem] - start, axis=1)
    assert moved.max() < 10.0  # the hem points stay (the start offset only)


def test_points_a_hair_apart_become_one() -> None:
    """ADR-063: a needle triangle (two corners 0.04 mm apart, left by the cut) is merged away
    before the fall; it made the Fiora L-part blow up."""
    v3 = np.array([[0, 0, 0], [100, 0, 0], [100.04, 0, 0], [50, 80, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 3], [1, 2, 3]], dtype=np.int64)
    weld = drape._merge_close(np.arange(4), v3, faces, 1.0)
    assert weld[1] == weld[2] and len(set(weld.tolist())) == 3
    assert drape._merge_close(np.arange(4), v3, faces, 0.01).tolist() == [0, 1, 2, 3]
