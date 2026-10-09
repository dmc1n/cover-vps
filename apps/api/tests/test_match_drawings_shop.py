"""ADR-114: the shop offers approved drawing covers as existing covers: the price list read for
their kind (sections, families, continued lines, #VALUE! ignored), the stock_model pattern, the
name from the price list, the fixed B2C price or the computed one with the stock discount, and a
cover rejected at the Desk no longer sold."""

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from coverapi import match_list
from coverapi.main import create_app
from fastapi.testclient import TestClient
from openpyxl import Workbook

PW = "a-long-admin-password"
HEADER = ["Item ", "Item Name", "Suitable for ", "Size ", "Packing", "Adv. Verk. Prijs EURO",
          "Type nr."]  # fmt: skip
SHEET = [
    ["#VALUE!"],
    [None, None, "Corner sets"],
    [None, None, "Savona / Siena "],
    ["#VALUE!", "Suns cover corner set left", "Savona with arms / Siena : 3-seater left, corner",
     "327 x 252 x 84 x 93 cm", "1 / box", 899, "C12"],
    [None, None, "Memphis/ Tondo: 2-seater left, corner, 2-seater right"],
    [None, None, "Tables "],
    [None, None, "Dining tables"],
    ["#VALUE!", "Suns Cover dining tables ", "Tables 340 x 100 cm incuding chairs",
     "350 x 166 x 87 cm", "1 / box", 999, "T1"],
    ["#VALUE!", "Suns Cover dining tables ", "Table 300x100", "300x100", "1 / box", 1049, "T9"],
    [None, None, "Umbrellas"],
    ["#VALUE!", "Suns cover umbrella ", "Umbrella cover 3*4", "269x60", "2 / boxes", 279, "U1"],
]  # fmt: skip


def _xlsx(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "SUNS Covers"
    ws.append(["Retail covers 2026-2027"])
    ws.append(HEADER)
    for r in SHEET:
        ws.append(r)
    for i in range(8):  # a list has a dozen coded rows or more: the rest of it
        ws.append(["#VALUE!", "Suns cover lounge chair", f"Family {i}: lounge chair",
                   "95x95x85", "1 / box", 299, f"S{60 + i}"])  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def _drawing(models: Path, mid: str, size_cm: tuple[float, float, float], notes: str,
             status: str, labels: list[str]) -> Path:  # fmt: skip
    d = models / mid
    d.mkdir(parents=True, exist_ok=True)
    (d / "cover.json").write_text(json.dumps({"notes": notes, "category": "Lounge › Sofasets"}))
    (d / "model.json").write_text(json.dumps({"size_mm": [x * 10 for x in size_cm]}))
    (d / "desk.json").write_text(json.dumps({"code": mid.split("-")[1].upper(), "status": status}))
    (d / "products.json").write_text(json.dumps({"labels": labels}))
    return d


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>studio</html>")
    a = create_app(tmp_path / "data", web_dir=web, login_required=True)
    u = a.state.auth.add_user("rick", "Rick", "admin", "rick@example.com", True)
    a.state.auth.set_password(a.state.auth.invite(u.id), PW)
    m = a.state.store.models
    _drawing(m, "drawing-t1", (350, 166, 87), "Drawing T1: box", "approved", ["Table 340x100"])
    _drawing(m, "drawing-t9", (310, 166, 87), "Drawing T9: box", "rejected", ["Table 300x100"])
    _drawing(m, "drawing-c12", (327, 252, 84), "Drawing C12: L shape", "produced",
             ["Savona lounge set Left with arm"])  # fmt: skip
    _xlsx(a.state.store.root / "prices" / "imports" / "20261009-130443-retail.xlsx")
    return a


def _admin(app: Any) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "rick", "password": PW}).status_code == 200
    return c


def test_the_price_list_is_read_with_its_sections_and_families(app: Any) -> None:
    lst = match_list.for_data(app.state.store.root)
    assert lst is not None and lst["source"] == "20261009-130443-retail.xlsx"
    c12 = lst["rows"]["c12"][0]
    assert c12["section"] == "Corner sets" and c12["family"] == "Savona / Siena"
    assert c12["item"] == "Suns cover corner set left"  # "#VALUE!" in Item: ignored
    assert c12["suitable"].endswith("\nMemphis/ Tondo: 2-seater left, corner, 2-seater right")
    assert lst["rows"]["t1"][0]["section"] == "Dining tables"
    assert lst["rows"]["u1"][0]["section"] == "Umbrellas"


def test_an_approved_drawing_cover_is_offered_and_sold(app: Any) -> None:
    admin = _admin(app)
    matching = {"mode": "auto", "stock_discount_pct": 10}
    admin.put("/api/admin/shop/settings", json={"matching": matching})
    c = TestClient(app)
    sizes = {"table_length_cm": 338, "table_width_cm": 100, "table_height_cm": 75}
    r = c.post("/api/shop/match", json={"product": "dining_set", "sizes": sizes}).json()
    assert r["decision"] == "existing" and r["match"]["model_id"] == "drawing-t1"
    name = "SUNS cover dining tables – Tables 340 x 100 cm incuding chairs"
    assert r["match"]["name"] == name  # the price list's name, not "drawing-t1"
    q = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": sizes,
                                        "stock_model": "drawing-t1",
                                        "match_token": r["token"]}).json()  # fmt: skip
    assert q["stock"] == {"model_id": "drawing-t1", "name": name}
    own = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": {
        "table_length_cm": 340, "table_width_cm": 100, "table_height_cm": 86}}).json()  # fmt: skip
    assert q["price"]["cover_eur"] == round(own["price"]["cover_eur"] * 0.9, 2)  # stock rule
    ps = admin.get("/api/prices").json()["current"]
    ps["channels"]["b2c"]["fixed"] = {"drawing-t1": 999.0}
    admin.put("/api/prices/draft", json={"data": ps})
    admin.post("/api/prices/publish", json={"note": "fixed"})
    q = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": sizes,
                                        "stock_model": "drawing-t1"}).json()  # fmt: skip
    assert q["price"]["cover_eur"] == 999.0  # its fixed B2C price wins
    corner = {"long_side_cm": 325, "short_side_cm": 250, "back_height_cm": 83}
    hand = {"product": "corner_sofa", "sizes": {**corner, "side": "left"}}
    left = c.post("/api/shop/match", json=hand).json()
    assert left["match"]["model_id"] == "drawing-c12"  # produced counts too
    hand["sizes"]["side"] = "right"
    right = c.post("/api/shop/match", json=hand).json()
    assert right["match"] is None or right["match"]["model_id"] != "drawing-c12"


def test_a_rejected_or_unknown_cover_is_not_sold(app: Any) -> None:
    c = TestClient(app)
    sizes = {"table_length_cm": 300, "table_width_cm": 100, "table_height_cm": 75}
    bad = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": sizes,
                                          "stock_model": "drawing-t9"})  # fmt: skip
    assert bad.status_code == 400  # rejected at the Desk
    assert (
        c.post(
            "/api/shop/quote",
            json={"product": "dining_set", "sizes": sizes, "stock_model": "order-12"},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/shop/quote", json={"product": "sofa", "sizes": {}, "stock_model": "drawing-t1"}
        ).status_code
        == 400
    )
    desk = app.state.store.models / "drawing-t1" / "desk.json"
    desk.write_text(json.dumps({"code": "T1", "status": "rejected"}))
    t = time.time() + 5
    os.utime(desk, (t, t))
    gone = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": sizes,
                                           "stock_model": "drawing-t1"})  # fmt: skip
    assert gone.status_code == 400  # rejected later: no longer in the range


def test_a_colleague_may_choose_a_drawing_cover(app: Any) -> None:
    admin = _admin(app)
    c = TestClient(app)
    sizes = {"table_length_cm": 250, "table_width_cm": 100, "table_height_cm": 75}
    c.post("/api/shop/match", json={"product": "dining_set", "sizes": sizes,
                                    "email": "anna@example.com"})  # fmt: skip
    req = admin.get("/api/admin/matches").json()["requests"][0]
    a = admin.put(f"/api/admin/matches/{req['id']}", json={"chosen": "drawing-t1"})
    assert a.status_code == 200, a.text
