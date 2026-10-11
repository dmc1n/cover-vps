"""A model kept but needing no cover (Rens, 9 Oct 2026, question 12): the studio sets and reads
the mark, the shop never offers the model (not as the existing cover, not as a similar one, not
priced as stock), and the Desk does not list it nor approve it. Models without the mark: as
before."""

import json
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient

PORTOFINO = "suns-dining-table-a-240"  # stands in for suns-daybed-with-roof-portofino
SIZES = {"table_length_cm": 239, "table_width_cm": 99, "table_height_cm": 76}


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    root = tmp_path / "data"
    a = create_app(root, login_required=True)
    auth = a.state.auth
    for user, name, role in (("rick", "Rick", "admin"), ("rens", "Rens de Vries", "editor")):
        u = auth.add_user(user, name, role, f"{user}@example.com", False)
        auth.set_password(auth.invite(u.id), f"a-long-secret-for-{user[::-1]}-9")
    for mid, size in (
        (PORTOFINO, (2400, 1000, 760)),
        ("suns-dining-table-b-200", (2000, 900, 750)),
    ):
        d = root / "models" / mid
        d.mkdir(parents=True)
        (d / "cover.json").write_text(json.dumps({"format_version": 1, "model_id": mid,
                                                  "category": "Shop › Tafels",
                                                  "status": "draft"}))  # fmt: skip
        (d / "model.json").write_text(json.dumps({"size_mm": list(size)}))
        (d / "finished.json").write_text(json.dumps({"pieces": []}))
        (d / "cut.dxf").write_text("0\nEOF\n")
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post(
        "/api/auth/login", json={"username": user, "password": f"a-long-secret-for-{user[::-1]}-9"}
    )
    assert r.status_code == 200, r.text
    return c


def _mark(app: Any, reason: str = "the roof is its own cover") -> TestClient:
    rick = login(app, "rick")
    r = rick.put(f"/api/models/{PORTOFINO}/info",
                 json={"no_cover": True, "no_cover_reason": reason})  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["no_cover"] is True and r.json()["no_cover_reason"] == reason
    return rick


def test_the_studio_sets_and_reads_the_mark(app: Any, tmp_path: Path) -> None:
    rick = login(app, "rick")
    listed = {m["id"]: m for m in rick.get("/api/models").json()}
    assert listed[PORTOFINO]["no_cover"] is False  # without the mark
    _mark(app)
    listed = {m["id"]: m for m in rick.get("/api/models").json()}
    assert listed[PORTOFINO]["no_cover"] is True
    assert listed[PORTOFINO]["no_cover_reason"] == "the roof is its own cover"
    assert listed["suns-dining-table-b-200"]["no_cover"] is False
    one = rick.get(f"/api/models/{PORTOFINO}").json()
    assert one["no_cover"] is True and one["category"] == "Shop › Tafels"
    assert rick.put(f"/api/models/{PORTOFINO}/info", json={"no_cover": "maybe"}).status_code == 422
    r = rick.put(f"/api/models/{PORTOFINO}/info", json={"no_cover": False})
    assert r.json()["no_cover"] is False and r.json()["no_cover_reason"] == ""
    doc = json.loads((tmp_path / "data" / "models" / PORTOFINO / "cover.json").read_text())
    assert "no_cover" not in doc and "no_cover_reason" not in doc


def test_the_shop_never_offers_it(app: Any) -> None:
    rick = login(app, "rick")
    rick.put("/api/admin/shop/settings", json={"matching": {"mode": "auto"}})
    c = TestClient(app)
    before = c.post("/api/shop/match", json={"product": "dining_set", "sizes": SIZES}).json()
    assert before["match"]["model_id"] == PORTOFINO  # without the mark: the existing cover
    _mark(app)
    r = c.post("/api/shop/match", json={"product": "dining_set", "sizes": SIZES}).json()
    assert r["match"] is None or r["match"]["model_id"] != PORTOFINO
    assert r["decision"] == "custom"  # the other table is 40 cm short: a custom cover
    q = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": SIZES,
                                        "stock_model": PORTOFINO})  # fmt: skip
    assert q.status_code == 400  # not sold as stock
    own = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": SIZES}).json()
    assert all(n["model_id"] != PORTOFINO for n in own["near"])  # nor as a similar cover
    req = rick.get("/api/admin/matches").json()["requests"][0]
    a = rick.put(f"/api/admin/matches/{req['id']}", json={"chosen": PORTOFINO})
    assert a.status_code == 400  # a colleague cannot choose it either


def test_the_desk_neither_lists_nor_approves_it(app: Any) -> None:
    rens = login(app, "rens")
    every = [i["id"] for i in rens.get("/api/desk").json()["items"]]
    assert PORTOFINO in every  # without the mark: on the Desk as before
    _mark(app)
    every = [i["id"] for i in rens.get("/api/desk").json()["items"]]
    assert PORTOFINO not in every and "suns-dining-table-b-200" in every
    r = rens.post(f"/api/desk/{PORTOFINO}", json={"action": "approve"})
    assert r.status_code == 409 and "needs no cover" in r.json()["detail"]
    assert (
        rens.post(f"/api/desk/{PORTOFINO}", json={"action": "note", "text": "ok"}).status_code
        == 200
    )
    assert rens.post(f"/api/desk/{PORTOFINO}/correct", json={"kind": "vents"}).status_code == 409
    other = rens.post("/api/desk/suns-dining-table-b-200", json={"action": "approve"})
    assert other.status_code == 200 and other.json()["status"] == "approved"
