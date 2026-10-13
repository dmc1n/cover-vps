"""The workshop login (owner, 13 Oct 2026, question 92; ADR-128): Work → Workshop and the Desk
read-only, fits, notes and pictures on a Desk card, its own questions, the DXF of approved covers.
Never approving, prices, settings, orders, admin pages or paid AI runs: enforced in the API."""

import io
import json
from pathlib import Path
from typing import Any

import pytest
from coverapi import desk
from coverapi.auth import AuthError
from coverapi.main import create_app
from fastapi.testclient import TestClient
from PIL import Image

USERS = (
    ("rick", "Rick", "admin"),
    ("rens", "Rens", "editor"),  # an approver by desk.approvers
    ("werkplaats", "Werkplaats", "workshop"),
    ("wouter", "Wouter", "workshop"),  # a name in desk.approvers, but the workshop role
)


def _secret(user: str) -> str:
    return f"a-long-secret-for-{user[::-1]}-9"


def _model(root: Path, name: str) -> Path:
    d = root / "models" / name
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "model_id": name,
                                              "status": "draft"}))  # fmt: skip
    piece = {"id": "top", "name": "top", "quantity": 1, "size_mm": [9, 9], "area_m2": 1, "note": ""}
    (d / "finished.json").write_text(json.dumps({"pieces": [piece]}))
    (d / "cut.dxf").write_text("0\nEOF\n")
    return d


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    root = tmp_path / "data"
    a = create_app(root, login_required=True)
    auth = a.state.auth
    for user, name, role in USERS:
        u = auth.add_user(user, name, role, f"{user}@example.com", False)
        auth.set_password(auth.invite(u.id), _secret(user))
    _model(root, "suns-chair")
    _model(root, "drawing-a")
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user, "password": _secret(user)})
    assert r.status_code == 200, r.text
    return c


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return buf.getvalue()


def test_the_workshop_reads_the_desk_and_the_workshop(app: Any) -> None:
    w = login(app, "werkplaats")
    me = w.get("/api/auth/me").json()["user"]
    assert me["role"] == "workshop" and me["desk_approver"] is False
    q = w.get("/api/desk").json()
    assert q["can_approve"] is False and q["can_note"] is True and q["spend"] is None
    assert w.get("/api/desk/suns-chair").status_code == 200
    assert w.get("/api/desk/suns-chair/correct").status_code == 200
    ws = w.get("/api/workshop").json()
    assert ws["can_produce"] is False and "orders" in ws
    assert w.get("/api/models").status_code == 200
    assert w.get("/api/models/suns-chair").status_code == 200
    assert w.get("/api/models/suns-chair/files/cover.json").status_code == 200
    assert w.get("/api/questions").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/prices",
        "/api/prices/list",
        "/api/prices/cover/suns-chair",
        "/api/prices/costing",
        "/api/admin/users",
        "/api/admin/orders",
        "/api/admin/shop/settings",
        "/api/admin/feedback",
        "/api/admin/b2b/orders",
        "/api/admin/system",
        "/api/desk-rules",
        "/api/arrangements",
        "/api/references",
        "/api/parameters",
        "/api/models/suns-chair/parameters",
        "/api/models/suns-chair/plan",
    ],
)
def test_the_workshop_sees_no_prices_settings_or_admin(app: Any, path: str) -> None:
    r = login(app, "werkplaats").get(path)
    assert r.status_code == 403, (path, r.status_code)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/models/suns-chair/run", {}),
        ("post", "/api/models/suns-chair/ai-apply", {"action": "x"}),
        ("post", "/api/models/suns-chair/drawing/ai", {}),
        ("post", "/api/batch", {}),
        ("put", "/api/models/suns-chair/parameters", {"values": {}}),
        ("put", "/api/models/suns-chair/info", {"status": "production"}),
        ("post", "/api/models/suns-chair/approval-request", {}),
        ("post", "/api/desk/suns-chair/correct", {"kind": "vents", "count": 3}),
        ("post", "/api/desk-rules", {"group": "x", "key": "y", "value": 1}),
        ("post", "/api/admin/orders/1/produce", {}),
        ("put", "/api/admin/orders/1", {"status": "in_production"}),
        ("post", "/api/questions", {"title": "x"}),
        ("post", "/api/prices/publish", {}),
        ("put", "/api/admin/users/1", {"role": "admin"}),
    ],
)
def test_the_workshop_changes_nothing_else(app: Any, method: str, path: str, body: Any) -> None:
    r = getattr(login(app, "werkplaats"), method)(path, json=body)
    assert r.status_code == 403, (path, r.status_code, r.text)


def test_the_workshop_never_approves_but_adds_fits_notes_and_pictures(app: Any) -> None:
    for name in ("werkplaats", "wouter"):  # "wouter" is in desk.approvers: the role wins
        w = login(app, name)
        for action in ({"action": "approve"}, {"action": "reject", "reasons": ["shape"]},
                       {"action": "produced"}, {"action": "undo"},
                       {"action": "prefer", "n": 1}):  # fmt: skip
            r = w.post("/api/desk/suns-chair", json=action)
            assert r.status_code == 403, (name, action)
    w = login(app, "werkplaats")
    pic = w.post("/api/desk/suns-chair/pictures",
                 files=[("files", ("a.png", _png(), "image/png"))])  # fmt: skip
    assert pic.status_code == 200, pic.text
    names = pic.json()["pictures"]
    r = w.post("/api/desk/suns-chair", json={"action": "note", "text": "seam 2 tight",
                                             "pictures": names})  # fmt: skip
    assert r.status_code == 200 and r.json()["history"][-1]["by"] == "Werkplaats"
    r = w.post("/api/desk/suns-chair", json={"action": "fit", "fits": True, "note": "good"})
    assert r.status_code == 200 and r.json()["fit"]["by"] == "Werkplaats"
    assert r.json()["status"] != "approved"
    assert w.get(f"/api/models/suns-chair/files/desk/{names[0]}").status_code == 200


def test_the_workshop_downloads_the_dxf_of_approved_covers_only(app: Any) -> None:
    w, rens = login(app, "werkplaats"), login(app, "rens")
    url = "/api/models/suns-chair/files/cut.dxf"
    assert w.get(url).status_code == 403
    assert w.get(f"{url}?override=1").status_code == 403  # only an admin overrides
    assert rens.post("/api/desk/suns-chair", json={"action": "approve"}).status_code == 200
    assert w.get(url).status_code == 200
    assert w.get("/api/models/drawing-a/files/cut.dxf").status_code == 403


def test_the_workshop_role_never_gets_may_approve(app: Any) -> None:
    auth = app.state.auth
    with pytest.raises(AuthError):
        auth.add_user("bench", "Bench", "workshop", None, True)
    u = auth.add_user("bench", "Bench", "workshop")
    with pytest.raises(AuthError):
        auth.update_user(u.id, {"can_approve": True})
    rens = next(x for x in auth.users() if x.username == "rens")
    auth.update_user(rens.id, {"can_approve": True})
    moved = auth.update_user(rens.id, {"role": "workshop"})
    assert moved.can_approve is False and not moved.may("approve")
    admin = login(app, "rick")
    users = admin.get("/api/admin/users").json()
    assert "workshop" in users["roles"]
    new = {"username": "bank", "role": "workshop", "can_approve": True, "send_invite": False}
    r = admin.post("/api/admin/users", json=new)
    assert r.status_code == 400


def test_the_workshop_sees_only_its_own_questions(app: Any) -> None:
    rick = login(app, "rick")
    base = {"text": "?", "topic": "workshop", "options": ["a", "b"], "models": []}
    mine = rick.post("/api/questions", json={**base, "title": "Zoom?",
                                             "answerers": "werkplaats"}).json()  # fmt: skip
    other = rick.post("/api/questions", json={**base, "title": "Prijs?", "topic": "prices",
                                              "answerers": "rens"}).json()  # fmt: skip
    w = login(app, "werkplaats")
    listed = [q["id"] for q in w.get("/api/questions").json()["items"]]
    assert listed == [mine["id"]]
    assert w.get(f"/api/questions/{other['id']}").status_code == 404
    assert w.get("/api/questions/count").json()["for_you"] == 1
    r = w.post(f"/api/questions/{mine['id']}/answer", json={"choice": 0})
    assert r.status_code == 200, r.text
    assert w.post(f"/api/questions/{other['id']}/answer", json={"choice": 0}).status_code == 403
    assert w.post(f"/api/questions/{mine['id']}/final", json={}).status_code == 403


def test_the_allow_list_names_only_known_routes() -> None:
    from coverapi.security import workshop_may

    assert workshop_may("GET", "/api/workshop")
    assert workshop_may("GET", "/api/models/suns-chair/files/cut.dxf")
    assert workshop_may("POST", "/api/desk/suns-chair")
    assert not workshop_may("GET", "/api/prices/list")
    assert not workshop_may("GET", "/api/desk/../prices")
    assert not workshop_may("POST", "/api/models/suns-chair/run")
    assert not workshop_may("DELETE", "/api/desk/suns-chair")
    assert desk.WORKER_ACTIONS == ("note", "fit")
