"""Route A in the web app: upload a drawing (PDF) and the program builds its cover (ADR-081)."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "engine" / "tests"))
from test_drawing_route import _kidney_pdf  # noqa: E402


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: Any) -> Any:
    monkeypatch.setenv("COVER_AUTO_DRAPE", "off")
    return create_app(tmp_path / "data")


def test_an_uploaded_drawing_is_built_as_a_cover_in_the_background(
    app: Any, tmp_path: Path
) -> None:
    pdf = _kidney_pdf(tmp_path / "cover 999 - S99.pdf")
    c = TestClient(app)
    r = c.post("/api/models/drawing",
               files={"file": ("cover 999 - S99.pdf", pdf.read_bytes())})  # fmt: skip
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["code"] == "S99" and out["model_id"] == "drawing-s99"
    d = app.state.store.model_dir(out["model_id"])
    assert (d / "reference.pdf").is_file()
    assert json.loads((d / "desk.json").read_text())["code"] == "S99"
    job = app.state.jobs.wait(out["job"]["id"], 600)
    assert job["status"] == "done", job
    read = c.get(f"/api/models/{out['model_id']}/drawing").json()
    assert read["status"] == "built" and read["vents"] == 4
    # built again from its drawing: a new revision, the desk and the drawing kept
    again = c.post(f"/api/models/{out['model_id']}/drawing")
    assert again.status_code == 200
    assert app.state.jobs.wait(again.json()["job"]["id"], 600)["status"] == "done"
    assert len(json.loads((d / "desk.json").read_text())["history"]) == 2


def test_only_pdfs_are_drawings(app: Any) -> None:
    c = TestClient(app)
    r = c.post("/api/models/drawing", files={"file": ("chair.stl", b"solid x")})
    assert r.status_code == 400
    r = c.post("/api/models/drawing", files={"file": ("fake.pdf", b"not a pdf")})
    assert r.status_code == 400


def test_the_ai_button_queues_the_ai_reading(app: Any, tmp_path: Path, monkeypatch: Any) -> None:
    """ADR-083: "let the AI read it" queues `cover drawing-ai` (the job is caught here, so no
    paid call is made in a test)."""
    pdf = _kidney_pdf(tmp_path / "cover 996 - S96.pdf")
    c = TestClient(app)
    queued: list[Any] = []
    real = app.state.jobs.submit
    out = c.post("/api/models/drawing",
                 files={"file": ("cover 996 - S96.pdf", pdf.read_bytes())}).json()  # fmt: skip
    app.state.jobs.wait(out["job"]["id"], 600)

    def catch(spec: Any) -> dict[str, str]:
        queued.append(spec)
        return {"id": "x", "status": "queued"}

    monkeypatch.setattr(app.state.jobs, "submit", catch)
    r = c.post(f"/api/models/{out['model_id']}/drawing/ai")
    assert r.status_code == 200, r.text
    assert queued and queued[0].steps == ["drawing-ai"]
    assert c.post("/api/models/nothing/drawing/ai").status_code == 400  # no drawing to read
    assert real is not None
