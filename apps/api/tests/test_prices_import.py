"""A price list from Excel as fixed prices in the draft (ADR-113): money as people write it,
columns found by content, rows matched to drawing covers by code and to SUNS models by name
(conservatively), incl./ex VAT converted exactly, only the draft written (the published set
stays), the history note, conflicts and hand picks, the kept upload, and who may do it."""

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from coverapi import prices_import as pim
from coverapi.main import create_app
from coverengine import costing
from fastapi.testclient import TestClient
from openpyxl import Workbook

PW = "a-long-admin-password"
FINISHED = {
    "pieces": [
        {"id": "P1", "name": "top", "quantity": 1, "area_m2": 1.0,
         "edges": [{"kind": "seam", "length_mm": 2000}, {"kind": "hem", "length_mm": 3000}]},
    ],
    "sheet": {"roll_length_mm": 2000},
}  # fmt: skip


def _model(models: Path, mid: str, notes: str, **files: Any) -> Path:
    d = models / mid
    d.mkdir(parents=True, exist_ok=True)
    (d / "cover.json").write_text(json.dumps({"notes": notes}))
    (d / "finished.json").write_text(json.dumps(FINISHED))
    for name, doc in files.items():
        (d / name.replace("_", ".", 1)).write_text(json.dumps(doc))
    return d


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
    m = a.state.store.models
    _model(m, "drawing-s40", "Drawing S40: sloped box",
           products_json={"labels": ["Bellano/Sato - Lounge chair", "Cover 105"],
                          "suns": {"linked": ["suns-lounge-chair-bellano"],
                                   "suggested": []}})  # fmt: skip
    (m / "drawing-s40" / "order_number.txt").write_text("Cover 105")
    _model(m, "drawing-c5", "Drawing C5: L shape")
    (m / "drawing-c5" / "order_number.txt").write_text("Cover 7")
    _model(m, "suns-lounge-chair-bellano", "SUNS 3D Warehouse x: SUNS-Lounge chair-Bellano")
    _model(m, "suns-2-seater-kota", "SUNS 3D Warehouse x: SUNS-2 Seater-Kota")
    _model(m, "suns-3-seater-kota", "SUNS 3D Warehouse x: SUNS-3 Seater-Kota")
    _model(m, "suns-chaise-lounge-left-nardo", "SUNS 3D Warehouse x: SUNS-Chaise lounge left-Nardo")
    _model(m, "suns-chaise-lounge-right-nardo",
           "SUNS 3D Warehouse x: SUNS-Chaise lounge right-Nardo")  # fmt: skip
    _model(m, "suns-dining-table-nardo", "SUNS 3D Warehouse x: SUNS-Dining table-Nardo")
    return a


def login(app: Any, name: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": name, "password": PW}).status_code == 200
    return c


def xlsx(rows: list[list[Any]], header: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Price list 2027"])  # a title above the header, as people do
    ws.append(header or ["Code", "Omschrijving", "Verkoopprijs incl. BTW"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SHEET = [
    ["S40", "Bellano/Sato - Lounge chair", "€ 1.234,95"],  # code (and a product name)
    ["", "SUNS 2 Seater Kota", "€ 649,00"],  # a SUNS name, exactly
    ["", "Kota 3-seater", 749.5],  # a SUNS name in other words: probable
    ["Cover 7", "", "899"],  # the order number on the drawing
    ["", "Nardo chaise lounge right", "€ 899,-"],  # the right one, never the left
    ["", "Unknown Fantasy Sofa", "€ 499,95"],  # nothing
    ["", "Ballon", "24,95"],  # the balloon
    ["", "Nardo lounge set", "1299"],  # a family, no type: a person chooses
]


def upload(c: TestClient, data: bytes, name: str = "prijslijst.xlsx", **form: str) -> Any:
    return c.post("/api/prices/import", files={"file": (name, data)}, data=form)


@pytest.mark.parametrize(
    ("given", "want"),
    [
        ("€ 1.234,95", 1234.95), ("1,234.95", 1234.95), ("1234,95", 1234.95),
        ("€ 459,-", 459.0), ("EUR 249", 249.0), ("1.234", 1234.0), ("12.5", 12.5),
        (1299, 1299.0), (749.5, 749.5), ("€1.234.567,00", 1234567.0), ("1 234,95", 1234.95),
        ("Cover 7", None), ("S40", None), ("n.v.t.", None), ("", None), (0, None),
        ("-5", None), (True, None),
    ],
)  # fmt: skip
def test_money_as_people_write_it(given: Any, want: float | None) -> None:
    assert pim.parse_price(given) == want


def test_the_columns_are_found_by_content(app: Any) -> None:
    r = upload(login(app, "rick"), xlsx(SHEET))
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["price_column"] == "Verkoopprijs incl. BTW" and rep["incl_vat"] is True
    assert set(rep["id_columns"]) == {"Code", "Omschrijving"}
    assert rep["channel"] == "b2c" and rep["file"] == "prijslijst.xlsx"
    # chosen again by a person (a browser's form sends the lines with \r\n)
    again = login(app, "rick").post(
        "/api/prices/import", data={"upload": rep["upload"], "id_columns": "Omschrijving\r\nCode"}
    )
    assert again.json()["id_columns"] == ["Omschrijving", "Code"]


def test_rows_are_matched_by_code_and_name_conservatively(app: Any) -> None:
    rep = upload(login(app, "rick"), xlsx(SHEET)).json()
    rows = {r["label"]: r for r in rep["rows"]}

    def ids(label: str) -> dict[str, str]:
        return {t["id"]: t["confidence"] for t in rows[label]["targets"]}

    s40 = rows["S40 · Bellano/Sato - Lounge chair"]
    assert s40["status"] == "exact" and s40["price_given"] == 1234.95
    assert ids(s40["label"]) == {"drawing-s40": "exact", "suns-lounge-chair-bellano": "probable"}
    assert ids("SUNS 2 Seater Kota") == {"suns-2-seater-kota": "exact"}
    assert ids("Kota 3-seater") == {"suns-3-seater-kota": "probable"}  # not the 2-seater
    assert ids("Cover 7") == {"drawing-c5": "exact"}
    assert ids("Nardo chaise lounge right") == {"suns-chaise-lounge-right-nardo": "probable"}
    assert ids("Ballon") == {"balloon": "exact"}
    assert rows["Unknown Fantasy Sofa"]["status"] == "none"
    lounge = rows["Nardo lounge set"]
    assert lounge["status"] == "ambiguous" and not lounge["targets"]
    cands = {c["id"] for c in lounge["candidates"]}
    assert "suns-chaise-lounge-left-nardo" in cands and "suns-dining-table-nardo" not in cands
    assert rep["counts"] == {"exact": 4, "probable": 2, "none": 1, "ambiguous": 1}


def test_incl_and_ex_vat_are_converted_exactly() -> None:
    rule = {"method": "markup", "pct": 50.0, "base": "landed", "rounding": "0.95"}
    b2b = {**rule, "vat_pct": 21.0, "show_vat": False, "fixed": {}}
    b2c = {**rule, "vat_pct": 21.0, "show_vat": True, "fixed": {}}
    for cents in range(1, 300001, 997):  # € 0.01 … € 3000, every price shape
        p = cents / 100
        ps = {"channels": {"b2b": {**b2b, "fixed": {"x": pim.stored_price(p, True, b2b)}},
                           "b2c": {**b2c,
                                   "fixed": {"x": pim.stored_price(p, False, b2c)}}}}  # fmt: skip
        assert costing.fixed_price(ps, "x", "b2b")["gross_eur"] == p  # type: ignore[index]
        assert costing.fixed_price(ps, "x", "b2c")["net_eur"] == p  # type: ignore[index]
    assert pim.stored_price(1234.95, True, b2c) == 1234.95  # same unit: as given, no rounding
    assert pim.stored_price(100.0, False, b2b) == 100.0


def test_only_the_draft_is_written_and_the_publish_takes_the_note(app: Any) -> None:
    admin = login(app, "rick")
    base = admin.get("/api/prices").json()["current"]
    admin.put("/api/prices/draft", json={"data": base})
    first = admin.post("/api/prices/publish", json={"note": "first"}).json()["version"]
    rep = upload(admin, xlsx(SHEET)).json()
    r = admin.post("/api/prices/import/apply", json={"upload": rep["upload"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["count"] == 7 and out["note"] == "Imported from prijslijst.xlsx (7 prices, B2C)"
    state = admin.get("/api/prices").json()
    assert state["published"]["version"] == first
    assert state["current"]["channels"]["b2c"]["fixed"] == {}  # nothing live yet
    assert state["draft"]["data"]["channels"]["b2c"]["fixed"] == {
        "drawing-s40": 1234.95, "suns-lounge-chair-bellano": 1234.95,
        "suns-2-seater-kota": 649.0, "suns-3-seater-kota": 749.5, "drawing-c5": 899.0,
        "suns-chaise-lounge-right-nardo": 899.0, "balloon": 24.95,
    }  # fmt: skip
    assert state["draft"]["note"].startswith("Imported from prijslijst.xlsx")
    seen = admin.post("/api/prices/preview", json={}).json()
    s40 = next(x for x in seen["rows"] if x["key"] == "drawing-s40")
    assert s40["after"]["b2c"] == 1234.95
    v = admin.post("/api/prices/publish", json={}).json()["version"]
    hist = admin.get("/api/prices/versions").json()["versions"][0]
    assert hist["version"] == v and hist["note"].startswith("Imported from prijslijst.xlsx")
    kept = list((app.state.store.root / "prices" / "imports").iterdir())
    assert len(kept) == 1 and kept[0].name.endswith("-prijslijst.xlsx")


def test_b2b_stores_ex_vat_so_the_price_incl_vat_is_the_sheet_s(app: Any) -> None:
    admin = login(app, "rick")
    rep = upload(admin, xlsx(SHEET), channel="b2b").json()
    t = next(t for r in rep["rows"] for t in r["targets"] if t["id"] == "drawing-s40")
    assert t["stored"] == round(1234.95 / 1.21, 6) and t["shown_incl"] == 1234.95
    admin.post("/api/prices/import/apply", json={"upload": rep["upload"], "channel": "b2b",
                                                 "exclude": ["balloon"]})  # fmt: skip
    d = admin.get("/api/prices").json()["draft"]["data"]["channels"]
    assert "balloon" not in d["b2b"]["fixed"] and d["b2c"]["fixed"] == {}
    c = admin.get("/api/prices/costing?model=drawing-s40&set=draft").json()
    assert c["channels"]["b2b"]["gross_eur"] == 1234.95 and c["channels"]["b2b"]["fixed"]
    # the same list said to be ex VAT: stored as given in the ex-VAT channel
    ex = upload(admin, xlsx(SHEET), channel="b2b", incl_vat="false").json()
    t = next(t for r in ex["rows"] for t in r["targets"] if t["id"] == "drawing-s40")
    assert ex["incl_vat"] is False and t["stored"] == 1234.95


def test_conflicts_and_hand_picks(app: Any) -> None:
    admin = login(app, "rick")
    sheet = SHEET + [["", "Bellano lounge chair", "€ 1.199,00"]]  # the SUNS chair again
    rep = upload(admin, xlsx(sheet)).json()
    # the S40 row names the Bellano chair only probably (through the product list), this row
    # too: two prices, a person chooses
    assert [c["id"] for c in rep["conflicts"]] == ["suns-lounge-chair-bellano"]
    unknown = next(r for r in rep["rows"] if r["label"] == "Unknown Fantasy Sofa")
    picks = [{"index": unknown["index"], "id": "suns-dining-table-nardo"},
             {"index": rep["rows"][-1]["index"], "id": "suns-lounge-chair-bellano"}]  # fmt: skip
    out = admin.post("/api/prices/import/apply", json={"upload": rep["upload"], "picks": picks})
    fixed = out.json()["draft"]["data"]["channels"]["b2c"]["fixed"]
    assert fixed["suns-dining-table-nardo"] == 499.95
    assert fixed["suns-lounge-chair-bellano"] == 1199.0
    bad = admin.post("/api/prices/import/apply",
                     json={"upload": rep["upload"],
                           "picks": [{"index": 0, "id": "../x"}]})  # fmt: skip
    assert bad.status_code == 400


def test_other_columns_csv_and_zip(app: Any) -> None:
    admin = login(app, "rick")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Artikel", "Naam", "Inkoop", "Prijs excl. BTW"])
    w.writerow(["1", "SUNS 2 Seater Kota", "100,00", "536,36"])
    w.writerow(["2", "S40", "120,00", "1.020,62"])
    data = buf.getvalue().encode()
    rep = upload(admin, data, "prices.csv").json()
    assert rep["price_column"] == "Prijs excl. BTW" and rep["incl_vat"] is False  # the header
    assert rep["id_columns"] == ["Naam"]
    again = admin.post("/api/prices/import", data={"upload": rep["upload"],
                                                   "price_column": "Inkoop",
                                                   "incl_vat": "true"}).json()  # fmt: skip
    assert again["price_column"] == "Inkoop" and again["rows"][0]["price_given"] == 100.0
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("lists/prices.csv", data)
        f.writestr("__MACOSX/._prices.csv", b"junk")
    assert upload(admin, z.getvalue(), "prices.zip").json()["rows"][0]["price_given"] == 536.36
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as f:
        f.writestr("../prices.csv", data)
    r = upload(admin, evil.getvalue(), "prices.zip")
    assert r.status_code == 400 and "unsafe" in r.json()["detail"]
    assert upload(admin, b"x", "old.xls").status_code == 400
    assert admin.post("/api/prices/import", data={"upload": "../app.db"}).status_code == 400


def test_who_may_import(app: Any) -> None:
    data = xlsx(SHEET)
    for name in ("eddy", "vera"):
        c = login(app, name)
        assert upload(c, data).status_code == 403
        assert c.post("/api/prices/import/apply", json={"upload": "x"}).status_code == 403
    assert upload(TestClient(app), data).status_code == 401
    assert not (app.state.store.root / "prices" / "imports").exists()  # nothing kept


def test_the_shop_sells_a_stock_cover_at_its_fixed_price(app: Any) -> None:
    from test_shop import _catalogue

    _catalogue(app)
    admin = login(app, "rick")
    ps = admin.get("/api/prices").json()["current"]
    ps["channels"]["b2c"]["fixed"] = {"suns-dining-table-a-240": 777.95}
    admin.put("/api/prices/draft", json={"data": ps})
    admin.post("/api/prices/publish", json={"note": "fixed"})
    sizes = {"table_length_cm": 240, "table_width_cm": 100, "table_height_cm": 76}
    c = TestClient(app)
    q = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": sizes,
                                        "stock_model": "suns-dining-table-a-240"},
               ).json()  # fmt: skip
    own = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": sizes}).json()
    assert q["price"]["cover_eur"] == 777.95 and own["price"]["cover_eur"] != 777.95
