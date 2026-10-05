"""ADR-070: the workshop's own reference per model, compared with the program's cover."""

import json
import time
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import trimesh
from coverapi.main import create_app
from coverengine.io.model_io import glb_bytes
from fastapi.testclient import TestClient


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    a = create_app(tmp_path / "data", login_required=False)
    d = a.state.store.models / "box-1"
    d.mkdir(parents=True)
    box = trimesh.creation.box(extents=(1200.0, 800.0, 700.0))
    box.apply_translation((0, 0, 350.0))
    (d / "hull.glb").write_bytes(glb_bytes([("hull", box)]))
    (d / "model.json").write_text(json.dumps({"id": "box-1", "size_mm": [1200, 800, 700]}))
    (d / "pattern.json").write_text(json.dumps({"panels": [{
        "name": "top", "flat_length_mm": 1200.0, "flat_width_mm": 800.0,
        "edges": [{"kind": "seam", "length_3d_mm": 1200.0}]}]}))  # fmt: skip
    return a


def _wait(c: TestClient) -> dict[str, Any]:
    for _ in range(100):
        s = c.get("/api/models/box-1/reference").json()
        if not s["running"]:
            return s
        time.sleep(0.2)
    raise AssertionError("the comparison did not finish")


def test_a_3d_reference_in_metres_is_laid_over_the_cover(app: Any, tmp_path: Path) -> None:
    ref = trimesh.creation.box(extents=(1.2, 0.8, 0.71))  # in metres, a centimetre higher
    path = tmp_path / "mine.stl"
    ref.export(path)
    c = TestClient(app)
    r = c.post("/api/models/box-1/reference", files={"file": ("mine.stl", path.read_bytes())})
    assert r.status_code == 200, r.text
    sf = _wait(c)["compare"]["surface"]
    assert "error" not in sf, sf
    assert sf["size_mm"]["theirs"] == [1200, 800, 710]  # found as metres
    assert sf["within_fit_pct"] > 80  # the top lies 1 cm off, the rest on it
    assert c.get("/api/models/box-1/reference/compare.glb").status_code == 200


def test_a_pdf_reference_has_its_sizes_found(app: Any, tmp_path: Path, monkeypatch: Any) -> None:
    from coverengine import compare

    lesson = {"rule": "keep the top in one piece", "check": "count", "applies_to": "all"}
    answer = {"summary": "the top is one piece", "differences": [], "lessons": [lesson]}
    monkeypatch.setattr(compare, "_ai_compare", lambda *a, **k: answer)
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Top 120 cm x 80 cm, height 99 cm")
    pdf = tmp_path / "mine.pdf"
    doc.save(pdf)
    c = TestClient(app)
    c.post("/api/models/box-1/reference", files={"file": ("mine.pdf", pdf.read_bytes())})
    dr = _wait(c)["compare"]["drawing"]
    assert len(dr["matched"]) == 2 and dr["missing_mm"] == [990.0]
    r = c.post("/api/models/box-1/reference/lessons/0")
    assert r.status_code == 200 and r.json()["lessons"] == 1
    kept = json.loads((app.state.store.root / "learning" / "lessons.json").read_text())
    assert kept[0]["rule"] == "keep the top in one piece"
    assert (app.state.store.root / "learning" / "references.jsonl").is_file()


def test_other_files_are_refused(app: Any) -> None:
    r = TestClient(app).post("/api/models/box-1/reference", files={"file": ("x.docx", b"x")})
    assert r.status_code == 400
