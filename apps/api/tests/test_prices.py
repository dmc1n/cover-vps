"""Prices and costing (ADR-098): draft, preview, publish, versions and rollback; who may do what;
the costing of a cover and of a configurator product, as JSON, CSV and PDF; the shop follows the
published price set."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient

PW = "a-long-admin-password"


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>studio</html>")
    a = create_app(tmp_path / "data", web_dir=web, login_required=True)
    auth = a.state.auth
    for name, role in (("rick", "admin"), ("eddy", "editor"), ("vera", "viewer")):
        u = auth.add_user(name, name.capitalize(), role, f"{name}@example.com", role == "admin")
        auth.set_password(auth.invite(u.id), PW)
    d = a.state.store.models / "drawing-t1"
    d.mkdir(parents=True)
    pieces = [
        {
            "id": "P1",
            "name": "top",
            "quantity": 1,
            "area_m2": 1.0,
            "edges": [{"kind": "seam", "length_mm": 2000}, {"kind": "hem", "length_mm": 3000}],
        },
        {
            "id": "P2",
            "name": "skirt",
            "quantity": 1,
            "area_m2": 1.0,
            "edges": [{"kind": "seam", "length_mm": 2000}, {"kind": "hem", "length_mm": 3000}],
        },
        {"id": "P3", "name": "vent-hood", "quantity": 2, "area_m2": 0.1, "edges": []},
    ]
    (d / "finished.json").write_text(
        json.dumps({"pieces": pieces, "sheet": {"roll_length_mm": 3000}})
    )
    (d / "cover.json").write_text(json.dumps({"notes": "Drawing T1: a test box"}))
    return a


def login(app: Any, name: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": name, "password": PW})
    assert r.status_code == 200, r.text
    return c


def test_who_may_see_and_change_the_prices(app: Any) -> None:
    admin, editor, viewer = login(app, "rick"), login(app, "eddy"), login(app, "vera")
    assert viewer.get("/api/prices").status_code == 403
    assert viewer.get("/api/prices/costing?model=drawing-t1").status_code == 403
    e = editor.get("/api/prices")
    assert e.status_code == 200 and e.json()["can_edit"] is False
    assert editor.get("/api/prices/costing?model=drawing-t1").status_code == 200
    data = e.json()["current"]
    assert editor.put("/api/prices/draft", json={"data": data}).status_code == 403
    assert editor.post("/api/prices/publish", json={}).status_code == 403
    assert editor.post("/api/prices/rollback/1").status_code == 403
    assert admin.get("/api/prices").json()["can_edit"] is True
    assert TestClient(app).get("/api/prices").status_code == 401


def test_draft_preview_publish_and_rollback(app: Any) -> None:
    admin = login(app, "rick")
    state = admin.get("/api/prices").json()
    assert state["using_defaults"] and state["published"] is None and state["draft"] is None
    base = state["current"]
    assert base["indicative"] is True
    draft = copy.deepcopy(base)
    draft["fabrics"][0]["price"] = base["fabrics"][0]["price"] * 2
    r = admin.put("/api/prices/draft", json={"data": draft})
    assert r.status_code == 200 and r.json()["errors"] == []
    before = admin.get("/api/prices/costing?model=drawing-t1").json()
    with_draft = admin.get("/api/prices/costing?model=drawing-t1&set=draft").json()
    assert with_draft["fabric_eur"] == pytest.approx(2 * before["fabric_eur"], abs=0.02)
    p = admin.post("/api/prices/preview", json={}).json()
    assert p["errors"] == [] and p["changed"] == p["total"] - 2  # the balloon and frame stay
    row = next(x for x in p["rows"] if x["key"] == "drawing-t1")
    assert row["after"]["cost"] > row["before"]["cost"] and row["kind"] == "drawing"
    assert any(x["key"] == "configurator:sofa" for x in p["rows"])
    # not live before publishing
    assert admin.get("/api/prices").json()["current"] == base
    v1 = admin.post("/api/prices/publish", json={"note": "fabric price doubled"}).json()
    assert v1["version"] == 1 and v1["prices_changed"] == p["changed"]
    state = admin.get("/api/prices").json()
    assert state["draft"] is None and state["published"]["username"] == "rick"
    assert state["current"]["fabrics"][0]["price"] == draft["fabrics"][0]["price"]
    # a second version, then back to the first
    d2 = copy.deepcopy(state["current"])
    d2["channels"]["b2b"]["pct"] = 10.0
    admin.put("/api/prices/draft", json={"data": d2})
    assert admin.post("/api/prices/publish", json={}).json()["version"] == 2
    back = admin.post("/api/prices/rollback/1").json()
    assert back == {"version": 3, "from_version": 1}
    vs = admin.get("/api/prices/versions").json()["versions"]
    assert [v["version"] for v in vs] == [3, 2, 1] and vs[0]["from_version"] == 1
    assert admin.get("/api/prices").json()["current"]["channels"]["b2b"]["pct"] != 10.0
    assert admin.post("/api/prices/rollback/99").status_code == 404
    log = app.state.auth.audit()
    actions = [x["action"] for x in log]
    assert actions.count("prices published") == 2 and "prices rolled back" in actions
    assert "fabric price doubled" in next(
        x["detail"]
        for x in log
        if x["action"] == "prices published" and '"version": 1' in x["detail"]
    )


def test_a_wrong_price_set_is_not_published(app: Any) -> None:
    admin = login(app, "rick")
    bad = copy.deepcopy(admin.get("/api/prices").json()["current"])
    bad["exchange"]["idr_per_eur"] = -1
    r = admin.put("/api/prices/draft", json={"data": bad})
    assert r.status_code == 200 and any("exchange" in e for e in r.json()["errors"])
    assert admin.post("/api/prices/preview", json={}).json()["errors"]
    assert admin.post("/api/prices/publish", json={}).status_code == 400
    assert admin.delete("/api/prices/draft").status_code == 200
    assert admin.post("/api/prices/publish", json={}).status_code == 400  # no draft


def test_the_costing_of_a_cover_and_a_configurator_product(app: Any) -> None:
    editor = login(app, "eddy")
    c = editor.get("/api/prices/costing?model=drawing-t1").json()
    assert c["name"] == "Drawing T1" and c["kind"] == "drawing"
    assert c["facts"]["piece"] == 2 and c["facts"]["seam_m"] == pytest.approx(2.0)
    assert c["facts"]["hem_m"] == pytest.approx(6.0) and c["facts"]["vent"] == 2
    assert {"b2c", "b2b"} <= set(c["channels"]) and c["cost_eur"] > 0
    assert all("idr" in x for x in c["lines"])  # both currencies
    csv = editor.get("/api/prices/costing.csv?model=drawing-t1")
    assert csv.status_code == 200 and "cost price" in csv.text and "landed cost" in csv.text
    pdf = editor.get("/api/prices/costing.pdf?model=drawing-t1")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    sizes = json.dumps({"length_cm": 200})
    k = editor.get(f"/api/prices/costing?product=sofa&sizes={sizes}").json()
    assert k["kind"] == "configurator" and k["cost_eur"] > 0
    assert editor.get("/api/prices/costing?model=nope").status_code == 404
    assert editor.get("/api/prices/costing?product=spaceship").status_code == 400
    names = {m["id"] for m in editor.get("/api/prices/products").json()["models"]}
    assert names == {"drawing-t1"}


def test_the_shop_follows_the_published_prices(app: Any) -> None:
    admin = login(app, "rick")
    shop = TestClient(app)
    body = {"product": "item", "sizes": {}}
    first = shop.post("/api/shop/quote", json=body).json()
    assert first["price"]["indicative"] is True
    assert shop.get("/api/shop/info").json()["settings"]["indicative"] is True
    ps = copy.deepcopy(admin.get("/api/prices").json()["current"])
    ps["indicative"] = False
    ps["channels"]["b2c"]["pct"] = ps["channels"]["b2c"]["pct"] + 50
    admin.put("/api/prices/draft", json={"data": ps})
    admin.post("/api/prices/publish", json={})
    again = shop.post("/api/shop/quote", json=body).json()
    assert again["price"]["indicative"] is False
    assert again["price"]["cover_eur"] > first["price"]["cover_eur"]
    assert shop.get("/api/shop/info").json()["settings"]["indicative"] is False
    assert "cost" not in json.dumps(again["price"])  # never the cost price to the customer


def test_the_odoo_records_have_the_bill_of_materials(app: Any) -> None:
    admin = login(app, "rick")
    r = admin.get("/api/prices/odoo?model=drawing-t1").json()
    bom = r["mrp.bom"][0]
    assert bom["product_tmpl_id"] == "cover_studio.drawing_t1"
    assert {x["product_id"] for x in bom["bom_line_ids"]} >= {
        "cover_studio.coverlast",
        "cover_studio.vent_set",
    }
    assert sum(o["time_cycle_manual"] for o in bom["operation_ids"]) > 0
    assert {p["name"] for p in r["product.pricelist"]} == {
        "Consumers (webshop)",
        "Business (Sunsit, dealers)",
    }
    assert r["res.currency.rate"][0]["currency_id"] == "IDR"
    assert login(app, "eddy").get("/api/prices/odoo").status_code == 403
