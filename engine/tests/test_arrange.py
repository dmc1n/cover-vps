"""Arrangements: furniture placed together, one cover over the whole (ADR-089)."""

import json
from pathlib import Path

import pytest
from coverengine import arrange as ar
from coverengine.cli import main as cover
from coverengine.io.model_io import import_model
from coverengine.params import Registry
from coverengine.testshapes import write_all as write_shapes


@pytest.fixture(scope="module")
def models(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two imported boxes on legs (800 x 600 x 700 mm), as two catalogue models."""
    root = tmp_path_factory.mktemp("arr")
    write_shapes(root / "generated")
    models = root / "models"
    for name in ("box-a", "box-b"):
        import_model(root / "generated" / "box_with_legs.stl", models / name,
                     Registry.load().resolve())  # fmt: skip
    return models


def test_snap_puts_a_member_against_the_other_side_aligned(models: Path) -> None:
    a, b = ar.Member("box-a"), ar.Member("box-b")
    meshes = {m: ar.furniture(models, m) for m in ("box-a", "box-b")}
    right = ar.snap([a, b], meshes, 1, 0, "right", "back")
    pa, pb = (
        ar.plan_box(ar.placed(meshes["box-a"], a)),
        ar.plan_box(ar.placed(meshes["box-b"], right)),
    )
    assert pb[0] == pytest.approx(pa[2], abs=0.01)  # touching
    assert pb[3] == pytest.approx(pa[3], abs=0.01)  # the backs in line
    front = ar.snap([a, b], meshes, 1, 0, "front", "left", gap_mm=50)
    pf = ar.plan_box(ar.placed(meshes["box-b"], front))
    assert pf[3] == pytest.approx(pa[1] - 50, abs=0.01) and pf[0] == pytest.approx(pa[0], abs=0.01)
    with pytest.raises(Exception, match="side"):
        ar.snap([a, b], meshes, 1, 0, "above")


def test_turned_and_mirrored_members_keep_their_place(models: Path) -> None:
    mesh = ar.furniture(models, "box-a")
    turned = ar.placed(mesh, ar.Member("box-a", 1000, -200, 90, True))
    x0, y0, x1, y1 = ar.plan_box(turned)
    assert (x1 - x0, y1 - y0) == pytest.approx((600, 800), abs=1)  # 90°: width and depth swap
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx((1000, -200), abs=0.01)
    assert turned.bounds[0][2] == pytest.approx(0, abs=1e-6)  # on the ground


def test_two_boxes_side_by_side_become_one_cover(models: Path) -> None:
    a = ar.Member("box-a")
    b = ar.snap([a, ar.Member("box-b")], {m: ar.furniture(models, m) for m in ("box-a", "box-b")},
                1, 0, "right", "back")  # fmt: skip
    src = ar.write(models, "arr-two-boxes", "Two boxes", [a, b])
    d = models / "arr-two-boxes"
    doc = ar.read(d)
    assert doc["size_mm"] == pytest.approx([1600, 600, 700], abs=1)
    assert [m["model_id"] for m in doc["members"]] == ["box-a", "box-b"]
    assert doc["members"][0]["version"]["model_glb"]  # what each member was
    assert ar.stale(models, doc) == []
    assert cover(["import", str(src), "--out", str(d), "--units", "mm", "--up", "z"]) == 0
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "tags": ["arrangement"],
                                              "parameters": {"hull": {"top": "box"}}}))  # fmt: skip
    for step in ("hull", "cut", "flatten", "export"):
        assert cover([step, str(d)]) == 0, step
    assert (d / ar.ARRANGEMENT_JSON).is_file()  # the import kept it
    assert json.loads((d / "kind.json").read_text())["kind"] == "product"  # and the answer
    fin = json.loads((d / "finished.json").read_text())
    pieces = [p for p in fin["pieces"] if not p["name"].startswith("vent")]
    assert pieces and all(min(p["size_mm"]) <= 1500 for p in pieces)  # every piece fits the roll
    assert max(max(p["size_mm"]) for p in pieces) > 1600  # one cover over both boxes

    # moved apart and built again: a bigger arrangement
    far = ar.Member("box-b", b.x_mm + 300, b.y_mm)
    ar.write(models, "arr-two-boxes", "Two boxes", [a, far])
    assert ar.read(d)["size_mm"][0] == pytest.approx(1900, abs=1)


def test_a_changed_member_makes_the_arrangement_stale(models: Path, tmp_path: Path) -> None:
    import shutil

    shutil.copytree(models / "box-a", tmp_path / "box-a")
    shutil.copytree(models / "box-b", tmp_path / "box-b")
    ar.write(tmp_path, "arr-x", "X", [ar.Member("box-a"), ar.Member("box-b", 1000, 0)])
    doc = ar.read(tmp_path / "arr-x")
    glb = tmp_path / "box-b" / "model.glb"
    glb.write_bytes(glb.read_bytes() + b" ")  # a member changed
    assert ar.stale(tmp_path, doc) == ["box-b"]
