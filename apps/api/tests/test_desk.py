"""The drawing desk (ADR-079): the AI sorts, Rens, Rick and Wouter approve; the DXF waits."""

import json
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient


def _model(root: Path, name: str, outcome: str | None, score: float | None) -> Path:
    d = root / "models" / name
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "model_id": name,
                                              "status": "draft", "tags": ["drawing"]}))  # fmt: skip
    (d / "finished.json").write_text(json.dumps({"pieces": [
        {"name": "top", "quantity": 1, "size_mm": [1000, 800]},
        {"name": "vent-hood", "quantity": 4, "size_mm": [280, 315]}]}))  # fmt: skip
    (d / "cut.dxf").write_text("0\nEOF\n")
    if outcome:
        (d / "check.json").write_text(json.dumps({
            "code": name, "outcome": outcome, "gemini": {"score": score, "summary": "s"},
            "deepseek": {"score": score, "summary": "s"}}))  # fmt: skip
    return d


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    root = tmp_path / "data"
    a = create_app(root, login_required=True)
    auth = a.state.auth
    users = (("rick", "Rick", "admin"), ("rens", "Rens de Vries", "editor"),
             ("vera", "Vera", "editor"))  # fmt: skip
    for user, name, role in users:
        u = auth.add_user(user, name, role, f"{user}@example.com", False)
        auth.set_password(auth.invite(u.id), f"a-long-secret-for-{user[::-1]}-9")
    _model(root, "drawing-a", "agreed: same", 95)
    _model(root, "drawing-b", "agreed: different", 20)
    _model(root, "drawing-c", "person to check", 70)
    _model(root, "drawing-d", "agreed: different", 70)
    _model(root, "drawing-e", None, None)
    _model(root, "suns-chair", None, None)
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post(
        "/api/auth/login", json={"username": user, "password": f"a-long-secret-for-{user[::-1]}-9"}
    )
    assert r.status_code == 200, r.text
    return c


def test_the_queue_puts_what_needs_a_person_first(app: Any) -> None:
    q = login(app, "vera").get("/api/desk").json()
    order = [i["id"] for i in q["items"]]
    # AIs disagree, poor, middling, not checked, then what the AIs found right
    assert order == ["drawing-c", "drawing-b", "drawing-d", "drawing-e", "drawing-a"]
    assert q["items"][0]["vents"] == 4 and q["items"][0]["pieces"] == 1
    assert q["counts"]["ai-checked"] == 4 and q["counts"]["new"] == 1
    assert q["can_approve"] is False
    assert len(login(app, "vera").get("/api/desk?scope=all").json()["items"]) == 6


def test_only_approvers_decide_and_the_catalogue_follows(app: Any, tmp_path: Path) -> None:
    vera, rens = login(app, "vera"), login(app, "rens")
    assert vera.post("/api/desk/drawing-b", json={"action": "approve"}).status_code == 403
    assert rens.get("/api/desk").json()["can_approve"] is True  # "Rens" on the list
    r = rens.post("/api/desk/drawing-b", json={"action": "produced", "done": True})
    assert r.status_code == 409  # approve first
    assert (
        rens.post("/api/desk/drawing-b", json={"action": "approve"}).json()["status"] == "approved"
    )
    cover = tmp_path / "data" / "models" / "drawing-b" / "cover.json"
    assert json.loads(cover.read_text())["status"] == "checked"
    r = rens.post("/api/desk/drawing-b", json={"action": "produced", "done": True})
    assert r.json()["status"] == "produced"
    assert json.loads(cover.read_text())["status"] == "production"
    r = rens.post(
        "/api/desk/drawing-b", json={"action": "fit", "fits": False, "note": "2 cm short"}
    )
    assert r.json()["fit"]["note"] == "2 cm short"
    rens.post("/api/desk/drawing-b", json={"action": "undo"})  # the fit
    st = rens.post("/api/desk/drawing-b", json={"action": "undo"}).json()  # produced
    assert st["status"] == "approved"
    assert json.loads(cover.read_text())["status"] == "checked"


def test_a_reject_needs_a_reason_and_is_logged_not_an_ai_lesson(app: Any, tmp_path: Path) -> None:
    """ADR-082: a reject's words no longer go into AI prompts; corrections change the cover."""
    rick = login(app, "rick")
    assert rick.post("/api/desk/drawing-a", json={"action": "reject"}).status_code == 400
    r = rick.post("/api/desk/drawing-a", json={
        "action": "reject", "reasons": ["shape"], "text": "the front must be round"})  # fmt: skip
    assert r.json()["status"] == "rejected"
    learning = tmp_path / "data" / "learning"
    assert not (learning / "lessons.json").is_file()
    assert "the front must be round" in (learning / "desk.jsonl").read_text()
    card = rick.get("/api/desk/drawing-a").json()
    assert (
        card["desk"]["rejected"]["reasons"] == ["shape"]
        and "before" not in card["desk"]["history"][0]
    )


def test_the_cutting_dxf_waits_for_approval(app: Any) -> None:
    vera, rens, rick = login(app, "vera"), login(app, "rens"), login(app, "rick")
    url = "/api/models/drawing-e/files/cut.dxf"
    r = vera.get(url)
    assert r.status_code == 403 and "approve" in r.json()["detail"]
    assert vera.get(f"{url}?override=1").status_code == 403  # only an admin may override
    assert rick.get(f"{url}?override=1").status_code == 200
    hist = rick.get("/api/desk/drawing-e").json()["desk"]["history"]
    assert hist[-1]["action"] == "dxf override"
    rens.post("/api/desk/drawing-e", json={"action": "approve"})
    assert vera.get(url).status_code == 200
    assert vera.get("/api/models/suns-chair/files/cut.dxf").status_code == 200  # scope: drawings
    assert vera.get("/api/desk/drawing-a").json()["dxf_ok"] is False
