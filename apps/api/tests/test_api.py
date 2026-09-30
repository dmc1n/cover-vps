import json
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from coverengine.testshapes import write_all as write_shapes
from fastapi.testclient import TestClient

RUN_TIMEOUT_S = 600


@pytest.fixture(scope="module")
def chair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("web")
    write_shapes(root / "shapes")
    app = create_app(root / "data")
    client = TestClient(app)
    with (root / "shapes" / "chair.stl").open("rb") as fh:
        r = client.post("/api/models", files={"file": ("Test Chair.stl", fh)})
    assert r.status_code == 200, r.text
    body = r.json()
    job = app.state.jobs.wait(body["job"]["id"], RUN_TIMEOUT_S)
    return {"client": client, "app": app, "id": body["model_id"], "job": job, "root": root}


def test_upload_runs_every_step(chair: dict[str, Any]) -> None:
    job = chair["job"]
    assert job["status"] == "done", job
    assert [s["name"] for s in job["steps"]] == ["import", "hull", "cut", "flatten", "export"]
    assert chair["id"] == "test-chair"


def test_model_summary_and_files(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    listing = c.get("/api/models").json()
    assert [m["id"] for m in listing] == ["test-chair"]
    m = c.get(f"/api/models/{chair['id']}").json()
    assert m["steps_done"] == ["import", "hull", "cut", "flatten", "export"]
    assert m["pattern"]["summary"]["panels"] == len(m["cut"]["panels"])
    assert any(p["name"] == "vent-hood" for p in m["finished"]["pieces"])
    r = c.get(f"/api/models/{chair['id']}/files/cut.dxf")
    assert r.status_code == 200 and b"LWPOLYLINE" in r.content
    assert c.get(f"/api/models/{chair['id']}/files/sizes.pdf").content.startswith(b"%PDF")
    assert c.get(f"/api/models/{chair['id']}/files/secret.txt").status_code == 404
    assert c.get("/api/models/../etc/files/model.json").status_code == 404


def test_parameters_save_to_cover_json(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    specs = c.get("/api/parameters").json()
    assert any(s["key"] == "hull.clearance_mm" and s["comment"] for s in specs)
    r = c.put(f"/api/models/{chair['id']}/parameters", json={"values": {"hull.clearance_mm": 15}})
    assert r.status_code == 200
    assert r.json()["sources"]["hull.clearance_mm"] == "model"
    doc = json.loads((chair["root"] / "data" / "models" / chair["id"] / "cover.json").read_text())
    assert doc["parameters"] == {"hull": {"clearance_mm": 15}}
    bad = c.put(f"/api/models/{chair['id']}/parameters", json={"values": {"hull.nope": 1}})
    assert bad.status_code == 400


def test_trial_run_is_not_saved_and_shows_the_diff(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    c.put(f"/api/models/{chair['id']}/parameters", json={"values": {}})
    r = c.post(
        f"/api/models/{chair['id']}/run",
        json={"steps": ["cut", "flatten"], "trial": {"stitching.allowance_mm": 20}},
    )
    assert r.status_code == 200, r.text
    job = chair["app"].state.jobs.wait(r.json()["id"], RUN_TIMEOUT_S)
    assert job["status"] == "done", job
    m = c.get(f"/api/models/{chair['id']}").json()
    assert m["diff"] is not None
    assert any(s["key"] == "stitching.allowance_mm" for s in m["diff"]["settings"])
    params = c.get(f"/api/models/{chair['id']}/parameters").json()
    assert params["sources"]["stitching.allowance_mm"] == "default"  # trial, not saved


def test_bad_requests(chair: dict[str, Any], tmp_path: Path) -> None:
    c: TestClient = chair["client"]
    r = c.post("/api/models", files={"file": ("notes.txt", b"hello")})
    assert r.status_code == 400
    r = c.post(f"/api/models/{chair['id']}/run", json={"steps": ["bake"]})
    assert r.status_code == 400
    r = c.post(f"/api/models/{chair['id']}/run", json={"trial": {"hull.clearance_mm": "wide"}})
    assert r.status_code == 400
    assert c.get("/api/models/nope").status_code == 404
