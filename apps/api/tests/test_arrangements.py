"""Arrangements in the studio: place furniture together, build one cover (ADR-089)."""

from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from coverengine.io.model_io import import_model
from coverengine.params import Registry
from coverengine.testshapes import write_all as write_shapes
from fastapi.testclient import TestClient


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: Any) -> Any:
    monkeypatch.setenv("COVER_AUTO_DRAPE", "off")
    write_shapes(tmp_path / "generated")
    for name in ("box-a", "box-b"):
        import_model(tmp_path / "generated" / "box_with_legs.stl",
                     tmp_path / "data" / "models" / name, Registry.load().resolve())  # fmt: skip
    return create_app(tmp_path / "data")


def test_place_snap_and_build_one_cover(app: Any) -> None:
    c = TestClient(app)
    out = c.get("/api/arrangements/outline/box-a").json()
    assert out["size_mm"] == pytest.approx([800, 600, 700], abs=1) and out["outline_mm"]
    members = [{"model_id": "box-a"}, {"model_id": "box-b"}]
    snapped = c.post("/api/arrangements/snap", json={"members": members, "i": 1, "j": 0,
                                                     "side": "right"}).json()["member"]  # fmt: skip
    assert snapped["x_mm"] == pytest.approx(800, abs=0.1)  # 400 + 400: touching on the right
    # the plans to choose from before building (ADR-095)
    plans = c.post("/api/arrangements/footprints", json={"members": [members[0], snapped]}).json()
    assert plans["default"] == "follow"
    assert [p["footprint"] for p in plans["options"]] == ["follow", "box", "smooth"]
    assert all(p["outline_mm"] and p["size_mm"][0] > 1600 for p in plans["options"])
    assert c.get("/api/arrangements/settings").json()["footprint"] == "follow"
    bad = {"name": "x", "members": [members[0], snapped], "footprint": "round"}
    assert c.post("/api/arrangements", json=bad).status_code == 400
    r = c.post("/api/arrangements", json={"name": "Two boxes", "members": [members[0], snapped]})
    assert r.status_code == 200, r.text
    built = r.json()
    assert built["model_id"] == "arr-two-boxes" and built["size_mm"][0] == pytest.approx(
        1600, abs=1
    )
    job = app.state.jobs.wait(built["job"]["id"], 900)
    assert job["status"] == "done", job
    listed = c.get("/api/arrangements").json()
    assert listed[0]["id"] == "arr-two-boxes" and listed[0]["built"] and listed[0]["stale"] == []
    brief = next(m for m in c.get("/api/models").json() if m["id"] == "arr-two-boxes")
    assert "arrangement" in (brief.get("tags") or [])  # in the catalogue, so at the Desk too
    one = c.get("/api/arrangements/arr-two-boxes").json()
    assert one["members"][1]["model_id"] == "box-b"
    assert one["footprint"] == "follow"  # the plan it was built with, stored
    # to the Desk, approved there; a change of plan reopens the approval (ADR-115)
    assert one["desk"]["status"] == "new" and one["desk"]["dxf_ok"] is False
    sent = c.post("/api/arrangements/arr-two-boxes/send").json()["desk"]
    assert sent["status"] == "ai-checked" and sent["sent"]["by"] == "Local user"
    assert c.post("/api/desk/arr-two-boxes", json={"action": "approve"}).status_code == 200
    assert c.get("/api/models/arr-two-boxes/files/cut.dxf").status_code == 200
    again = {"name": "Two boxes", "model_id": "arr-two-boxes", "members": [members[0], snapped],
             "footprint": "box"}  # fmt: skip
    r = c.post("/api/arrangements", json=again)
    assert r.status_code == 200, r.text
    assert r.json()["desk"]["status"] == "ai-checked"
    assert r.json()["desk"]["last"]["action"] == "changed after approval"
    assert "plan follow → box" in r.json()["desk"]["last"]["text"]
    assert c.get("/api/models/arr-two-boxes/files/cut.dxf").status_code == 403
    job = app.state.jobs.wait(r.json()["job"]["id"], 900)
    assert job["status"] == "done", job


def test_wrong_requests_are_refused(app: Any) -> None:
    c = TestClient(app)
    assert c.get("/api/arrangements/outline/nothing").status_code == 400
    one = [{"model_id": "box-a"}, {"model_id": "box-b"}]
    assert c.post("/api/arrangements/snap", json={"members": one, "i": 0, "j": 0,
                                                  "side": "left"}).status_code == 400  # fmt: skip
    assert c.post("/api/arrangements/snap", json={"members": one, "i": 1, "j": 0,
                                                  "side": "above"}).status_code == 400  # fmt: skip
    nested = [{"model_id": "box-a"}, {"model_id": "arr-x"}]
    assert c.post("/api/arrangements", json={"name": "x", "members": nested}).status_code in (
        400,
        404,
    )
