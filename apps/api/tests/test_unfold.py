"""The cover unfolded, piece by piece, with where its fabric goes (ADR-085)."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from coverapi.main import create_app
from coverengine.testshapes import write_all as write_shapes
from fastapi.testclient import TestClient

RUN_TIMEOUT_S = 600


@pytest.fixture(scope="module")
def box(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("unfold")
    write_shapes(root / "shapes")
    app = create_app(root / "data")
    client = TestClient(app)
    with (root / "shapes" / "box_with_legs.stl").open("rb") as fh:
        r = client.post("/api/models", files={"file": ("Box.stl", fh)}, data={"kind": "product"})
    assert r.status_code == 200, r.text
    body = r.json()
    job = app.state.jobs.wait(body["job"]["id"], RUN_TIMEOUT_S)
    assert job["status"] == "done", job
    d = Path(app.state.store.model_dir(body["model_id"]))
    return {"client": client, "app": app, "id": body["model_id"],
            "cache_after_run": (d / "unfold").exists()}  # fmt: skip


def test_every_piece_unfolds_and_the_fabric_adds_up(box: dict[str, Any]) -> None:
    c: TestClient = box["client"]
    r = c.get(f"/api/models/{box['id']}/unfold.json")
    assert r.status_code == 200, r.text
    meta = r.json()
    d = box["app"].state.store.model_dir(box["id"])
    fin = json.loads((d / "finished.json").read_text())
    pieces = [p for p in fin["pieces"] if not p["name"].startswith("vent-")]
    flat = [p for p in meta["flat"] if not p["extra"]]
    assert len(flat) == len(pieces) == len(meta["pieces"])
    t = meta["totals"]
    assert all(v >= 0 for v in t.values())
    parts = t["net_m2"] + t["seam_m2"] + t["hem_m2"] + t["vents_m2"]
    assert parts == pytest.approx(t["cut_m2"], abs=0.01)
    assert t["cut_m2"] <= t["fabric_m2"] + 1e-6
    for p in flat:  # the cut outline holds the net outline, and is larger
        assert p["cut_m2"] >= p["net_m2"] > 0
        assert p["cut_cm"][0] >= p["net_cm"][0] and p["cut_cm"][1] >= p["net_cm"][1]

    # the morph: three shapes of the same points, then the pieces and the triangles
    blob = c.get(f"/api/models/{box['id']}/unfold.bin").content
    n, m = meta["points"], meta["triangles"]
    assert len(blob) == 3 * n * 12 + n + m * 12
    flat_pts = np.frombuffer(blob, dtype="<f4", count=n * 3, offset=2 * n * 12).reshape(n, 3)
    assert np.ptp(flat_pts[:, 1]) < 1e-3  # flat on the table


def test_the_second_view_comes_from_the_cache(box: dict[str, Any]) -> None:
    c: TestClient = box["client"]
    c.get(f"/api/models/{box['id']}/unfold.json")
    assert c.get(f"/api/models/{box['id']}/unfold.json").json()["cached"] is True


def test_a_cover_not_yet_calculated_has_nothing_to_unfold(box: dict[str, Any]) -> None:
    assert box["client"].get("/api/models/nothing/unfold.json").status_code == 404


def test_unfold_never_runs_in_the_standard_calculation(box: dict[str, Any]) -> None:
    """ADR-080: only on request; a fresh model has no unfold cache until someone asks."""
    assert box["cache_after_run"] is False
