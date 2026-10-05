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
        r = client.post(
            "/api/models", files={"file": ("Test Chair.stl", fh)}, data={"kind": "product"}
        )
    assert r.status_code == 200, r.text
    body = r.json()
    job = app.state.jobs.wait(body["job"]["id"], RUN_TIMEOUT_S)
    return {"client": client, "app": app, "id": body["model_id"], "job": job, "root": root}


def test_upload_runs_every_step(chair: dict[str, Any]) -> None:
    job = chair["job"]
    assert job["status"] == "done", job
    assert [s["name"] for s in job["steps"]] == ["import", "hull", "cut", "flatten", "export"]
    assert chair["id"] == "test-chair"


def test_upload_asks_what_the_file_is(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    with (chair["root"] / "shapes" / "chair.stl").open("rb") as fh:
        r = c.post("/api/models", files={"file": ("Second Chair.stl", fh)})
    job = chair["app"].state.jobs.wait(r.json()["job"]["id"], RUN_TIMEOUT_S)
    assert [s["name"] for s in job["steps"]] == ["import"]
    m = c.get("/api/models/second-chair").json()
    assert m["kind"]["guess"] == "product" and not m["kind"]["confirmed"]
    r = c.post("/api/models/second-chair/kind", json={"kind": "product", "run": False})
    assert r.status_code == 200 and r.json()["kind"]["confirmed"]
    assert c.post("/api/models/second-chair/kind", json={"kind": "sofa"}).status_code == 400


def test_model_summary_and_files(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    listing = c.get("/api/models").json()
    assert "test-chair" in [m["id"] for m in listing]
    m = c.get(f"/api/models/{chair['id']}").json()
    assert m["steps_done"] == ["import", "hull", "cut", "flatten", "export"]
    assert m["pattern"]["summary"]["panels"] == len(m["cut"]["panels"])
    assert any(p["name"] == "vent-hood" for p in m["finished"]["pieces"])
    r = c.get(f"/api/models/{chair['id']}/files/cut.dxf")
    assert r.status_code == 200 and b"LWPOLYLINE" in r.content
    assert c.get(f"/api/models/{chair['id']}/files/sizes.pdf").content.startswith(b"%PDF")
    assert c.get(f"/api/models/{chair['id']}/files/secret.txt").status_code == 404
    # the air vents in 3D for the viewer's "Show air vents" (ADR-073)
    assert "vents.json" in m["files"]
    vents = c.get(f"/api/models/{chair['id']}/files/vents.json").json()["vents"]
    hoods = next(p for p in m["finished"]["pieces"] if p["name"] == "vent-hood")
    assert len(vents) == hoods["quantity"] and len(vents[0]["corners_mm"]) == 4
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


def test_plan_view_and_hand_placed_seams(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    p = c.get(f"/api/models/{chair['id']}/plan").json()
    assert len(p["outline"]) > 10 and p["seams"] and p["panels"]
    assert c.get(f"/api/models/{chair['id']}/files/plan.png").content[:4] == b"\x89PNG"
    xmin, ymin, xmax, ymax = p["extent"]
    # a seam straight across the top, from side to side at the middle
    y = (ymin + ymax) / 2
    line = [[xmin - 50, y], [xmax + 50, y]]
    r = c.put(f"/api/models/{chair['id']}/seams", json={"top_seams": [line]})
    assert r.status_code == 200, r.text
    job = chair["app"].state.jobs.wait(r.json()["job"]["id"], RUN_TIMEOUT_S)
    assert job["status"] == "done", job
    m = c.get(f"/api/models/{chair['id']}").json()
    assert sum(1 for q in m["cut"]["panels"] if q["region"] == "top") == 2  # the top is split
    r = c.put(f"/api/models/{chair['id']}/seams", json={"automatic": True})
    job = chair["app"].state.jobs.wait(r.json()["job"]["id"], RUN_TIMEOUT_S)
    m = c.get(f"/api/models/{chair['id']}").json()
    assert sum(1 for q in m["cut"]["panels"] if q["region"] == "top") == 1


def test_family_status_revisions_and_batch(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    assert "table" in c.get("/api/families").json()
    r = c.put(f"/api/models/{chair['id']}/info", json={"status": "checked", "tags": ["test"]})
    assert r.status_code == 200 and r.json()["status"] == "checked"
    assert c.put(f"/api/models/{chair['id']}/info", json={"status": "nope"}).status_code == 400
    listing = {m["id"]: m for m in c.get("/api/models").json()}
    assert listing[chair["id"]]["status"] == "checked"
    assert listing[chair["id"]]["tags"] == ["test"]
    m = c.get(f"/api/models/{chair['id']}").json()
    assert m["revisions"], "every export keeps a revision"
    n = m["revisions"][-1]["number"]
    assert c.get(f"/api/models/{chair['id']}/revisions/{n}/cut.dxf").status_code == 200
    r = c.post("/api/batch", json={"model_ids": [chair["id"]], "steps": ["export"]})
    assert r.status_code == 200, r.text
    job = chair["app"].state.jobs.wait(r.json()["jobs"][0]["id"], RUN_TIMEOUT_S)
    assert job["status"] == "done"
    m2 = c.get(f"/api/models/{chair['id']}").json()
    assert m2["revisions"][-1]["number"] == n + 1
    assert c.post("/api/batch", json={"family": "table"}).status_code == 400  # none of them


def test_improve_step(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    r = c.post(f"/api/models/{chair['id']}/run", json={"steps": ["improve"]})
    assert r.status_code == 200, r.text
    job = chair["app"].state.jobs.wait(r.json()["id"], RUN_TIMEOUT_S)
    assert job["status"] == "done", job
    assert "improve" in job["steps"][0]["log"]


def test_reference_zip(chair: dict[str, Any], tmp_path: Path) -> None:
    import io
    import zipfile

    from matplotlib.figure import Figure

    fig = Figure(figsize=(4, 3))
    fig.text(0.1, 0.5, "Skirt height [40.6cm] 16.0in")
    pdf = io.BytesIO()
    fig.savefig(pdf, format="pdf")
    z = tmp_path / "covers.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(chair["root"] / "shapes" / "chair.stl", "drawings/1.stl")
        zf.writestr("drawings/1.pdf", pdf.getvalue())
        zf.writestr("2.pdf", pdf.getvalue())  # no 3D file: kept as a drawing
    c: TestClient = chair["client"]
    with z.open("rb") as fh:
        r = c.post("/api/references", files={"file": ("covers.zip", fh)})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert [p["name"] for p in doc["pairs"]] == ["1"] and doc["drawings_only"] == ["2.pdf"]
    model_id = doc["pairs"][0]["model_id"]
    job = chair["app"].state.jobs.wait(doc["pairs"][0]["job"], RUN_TIMEOUT_S)
    assert job["status"] == "done", job
    ref = c.get(f"/api/models/{model_id}/files/reference.json").json()
    assert 406.0 in ref["sizes_mm"] and ref["vector_paths"] >= 0
    assert c.get(f"/api/models/{model_id}/files/reference.png").content[:4] == b"\x89PNG"
    assert any(
        s["label"].startswith("Total height") for s in c.get(f"/api/models/{model_id}/sizes").json()
    )
    listed = c.get("/api/references").json()
    assert listed[0]["pairs"][0]["status"] == "done"
    m = c.get(f"/api/models/{model_id}").json()
    assert "reference" in m["tags"]
    bad = c.post("/api/references", files={"file": ("x.zip", b"not a zip")})
    assert bad.status_code == 400


def test_approval_of_the_definitive_drawing(chair: dict[str, Any]) -> None:
    c: TestClient = chair["client"]
    mid = chair["id"]
    r = c.put(f"/api/models/{mid}/info", json={"status": "production"})
    assert r.status_code == 400  # production needs an approval first
    r = c.post(f"/api/models/{mid}/approve", json={"note": "checked on the table"})
    assert r.status_code == 200, r.text
    assert r.json()["approval"]["valid"]
    assert c.get(f"/api/models/{mid}").json()["approval"]["valid"]
    pdf = c.get(f"/api/models/{mid}/approved/sizes.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # calculated again with other settings: the approval no longer matches the files
    r = c.post(
        f"/api/models/{mid}/run", json={"steps": ["export"], "trial": {"hem.allowance_mm": 60}}
    )
    chair["app"].state.jobs.wait(r.json()["id"], RUN_TIMEOUT_S)
    assert c.get(f"/api/models/{mid}").json()["approval"]["valid"] is False
    assert c.delete(f"/api/models/{mid}/approve").status_code == 200


def test_a_full_calculation_is_followed_by_its_drape_in_a_queue_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-059: after a job that ends with export comes the drape (kept with the model), in
    its own queue; a trial run gets none."""
    import subprocess
    import time

    from coverapi import jobs as jobs_mod
    from coverapi.jobs import Jobs, JobSpec
    from coverapi.store import Store

    ran: list[list[str]] = []

    def fake(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        ran.append(args[3:])  # after: python -m coverengine.cli
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(jobs_mod.subprocess, "run", fake)
    store = Store(tmp_path / "data")
    store.ensure()
    (store.models / "m").mkdir()
    jobs = Jobs(store, drape_after_export=True)
    jobs.wait(jobs.submit(JobSpec("m", ["export"], {}))["id"], 10)
    jobs.wait(jobs.submit(JobSpec("m", ["export"], {"hull.clearance_mm": 20}))["id"], 10)
    end = time.time() + 10
    while time.time() < end and sum(a[0] == "drape" for a in ran) < 1:
        time.sleep(0.1)
    time.sleep(0.5)
    assert [a[0] for a in ran].count("export") == 2
    assert [a[0] for a in ran].count("drape") == 1  # after the saved run only


def test_downloads_carry_the_models_name() -> None:
    """The owner (5 Oct 2026): the cutting table's file is named after the model, not cut.dxf."""
    from coverapi.main import _named

    assert _named("suns-lounge-lucia", "cut.dxf") == ("suns-lounge-lucia.dxf", "attachment")
    assert _named("suns-lounge-lucia", "cut.dxf", 3) == ("suns-lounge-lucia-r3.dxf", "attachment")
    assert _named("suns-lounge-lucia", "pattern.dxf")[0] == "suns-lounge-lucia-pattern.dxf"
    assert _named("suns-lounge-lucia", "drape.glb")[1] == "inline"
