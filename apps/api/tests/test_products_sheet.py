"""The product list linked to the drawing covers at the Desk (ADR-091)."""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from coverapi.products_sheet import kinds, norm, suns_for, suns_index
from fastapi.testclient import TestClient
from openpyxl import Workbook


def _model(root: Path, name: str, code: str | None = None) -> Path:
    d = root / "models" / name
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "model_id": name,
                                              "status": "draft", "tags": ["drawing"]}))  # fmt: skip
    if code:
        (d / "check.json").write_text(json.dumps({"code": code}))
    (d / "order_number.txt").write_text("")  # no PDF in the tests: no order number
    return d


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    root = tmp_path / "data"
    a = create_app(root, login_required=True)
    auth = a.state.auth
    users = (("rick", "Rick", "admin"), ("rens", "Rens de Vries", "editor"),
             ("vera", "Vera", "viewer"))  # fmt: skip
    for user, name, role in users:
        u = auth.add_user(user, name, role, f"{user}@example.com", False)
        auth.set_password(auth.invite(u.id), f"a-long-secret-for-{user[::-1]}-9")
    _model(root, "drawing-s40")
    _model(root, "drawing-c23")
    _model(root, "drawing-l1")
    _model(root, "drawing-cover-39-46-l1-l5-mirror", "cover 39 & 46 - L1 & L5 mirror")
    _model(root, "drawing-d1")
    (root / "models" / "drawing-s40" / "order_number.txt").write_text("Cover 105")
    for s in ("suns-daybed-portofino", "suns-lounge-sato-lounge-chair", "suns-table-kota",
              "suns-chaise-lounge-portofino", "suns-2-seater-portofino"):  # fmt: skip
        _model(root, s)
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post(
        "/api/auth/login", json={"username": user, "password": f"a-long-secret-for-{user[::-1]}-9"}
    )
    assert r.status_code == 200, r.text
    return c


ROWS = [
    ("Bellano/Sato - Lounge chair", "Cover 105", "s40"),
    ("Vento corner", "Cover 66", "C 23"),
    ("Portofino CL left", "Cover 46", "L5"),
    ("Portofino/ Aspen/ Kota normal D-Bed", "Cover 1", "D1"),
    ("Merano lounge chair", "Cover 200", "S99"),
]


def _xlsx(rows: list[tuple[str, str, str]] = ROWS, header: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Our list"])  # a title row above the header
    if header:
        ws.append(["WEATHER MAX MID GREY COLOR", "Cover", "Code"])
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def _up(c: TestClient, name: str, data: bytes, column: str = "") -> Any:
    return c.post("/api/desk-products", files={"file": (name, data)},
                  data={"column": column} if column else {})  # fmt: skip


def test_codes_match_however_they_are_written() -> None:
    assert norm("Cover 0105") == norm("cover105") == "cover105"
    assert norm("C 23") == norm("c23") and norm("S-40") == "s40"


def test_an_xlsx_links_its_rows_and_lists_what_it_could_not(app: Any, tmp_path: Path) -> None:
    rick = login(app, "rick")
    r = _up(rick, "namecode.xlsx", _xlsx())
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["column"] == "Code"  # found by its values, not its name
    assert out["rows"] == 5 and out["linked_rows"] == 4 and out["covers"] == 4
    assert [u["Code"] for u in out["unmatched"]] == ["S99"]
    assert out["without_products"] == ["drawing-l1"]
    models = tmp_path / "data" / "models"
    # L5 is inside the combined name; L1 stays with drawing-l1
    doc = json.loads((models / "drawing-cover-39-46-l1-l5-mirror" / "products.json").read_text())
    assert doc["labels"] == ["Cover 46", "Portofino CL left"]
    assert list(models.glob("*/products.json")).__len__() == 4
    assert (tmp_path / "data" / "products").is_dir()  # the upload is kept


def test_the_desk_shows_searches_and_sorts_by_products(app: Any) -> None:
    rick = login(app, "rick")
    _up(rick, "namecode.xlsx", _xlsx())
    items = {i["id"]: i for i in rick.get("/api/desk").json()["items"]}
    assert "Bellano/Sato - Lounge chair" in items["drawing-s40"]["products"]
    assert items["drawing-l1"]["products"] == []
    card = rick.get("/api/desk/drawing-s40").json()["product_list"]
    assert card["column"] == "Code" and card["columns"][:3] == [
        "WEATHER MAX MID GREY COLOR", "Cover", "Code"]  # fmt: skip
    assert card["rows"][0][:3] == ["Bellano/Sato - Lounge chair", "Cover 105", "s40"]
    assert card["suns"]["linked"] == ["suns-lounge-sato-lounge-chair"]
    # the SUNS model knows its drawing too, and shows it as its product
    assert items["suns-lounge-sato-lounge-chair"]["products"] == [
        "S40 · Bellano/Sato - Lounge chair"]  # fmt: skip
    sato = rick.get("/api/desk/suns-lounge-sato-lounge-chair").json()["product_list"]
    assert sato["drawings"]["linked"][0]["id"] == "drawing-s40"


def test_another_column_can_be_chosen_and_applied_again(app: Any, tmp_path: Path) -> None:
    rick = login(app, "rick")
    _up(rick, "namecode.xlsx", _xlsx())
    r = rick.post("/api/desk-products", data={"column": "Cover"})  # the last upload, again
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["column"] == "Cover" and out["linked_rows"] == 1  # only Cover 105 is an order no.
    models = tmp_path / "data" / "models"
    assert sorted(p.parent.name for p in models.glob("*/products.json")) == ["drawing-s40"]
    assert rick.post("/api/desk-products", data={"column": "Nope"}).status_code == 400


def test_a_csv_works_and_an_old_xls_is_refused_plainly(app: Any) -> None:
    rick = login(app, "rick")
    csv = b"Product;Article;Drawing\nKota daybed;A-1;D1\nTable;A-2;S40\n"
    out = _up(rick, "list.csv", csv).json()
    assert out["column"] == "Drawing" and out["linked_rows"] == 2
    r = _up(rick, "list.xls", b"\xd0\xcf\x11\xe0")
    assert r.status_code == 400 and "save it as .xlsx" in r.json()["detail"]


def test_a_zip_is_read_with_care(app: Any) -> None:
    rick = login(app, "rick")
    z = _zip({"namecode.xlsx": _xlsx(), "__MACOSX/._namecode.xlsx": b"junk",
              ".hidden.csv": b"a,b\n1,2\n", "pdfs/Cover 105 - S40.pdf": b"%PDF",
              "pdfs/Z9.pdf": b"%PDF"})  # fmt: skip
    out = _up(rick, "20261007-151325.zip", z).json()
    assert [f["file"] for f in out["files"]] == ["namecode.xlsx"]
    assert out["linked_rows"] == 4
    assert out["pdfs"] == {"count": 2, "matched": 1, "new": ["Z9.pdf"]}
    bad = _zip({"../../evil.csv": b"a,b\nS40,x\n", "namecode.xlsx": _xlsx()})
    r = _up(rick, "bad.zip", bad)
    assert r.status_code == 400 and "unsafe path" in r.json()["detail"]
    assert _up(rick, "x.zip", b"not a zip").status_code == 400


def test_only_editors_and_approvers_upload(app: Any) -> None:
    vera, rens = login(app, "vera"), login(app, "rens")  # a viewer, an editor
    assert _up(vera, "namecode.xlsx", _xlsx()).status_code == 403
    assert _up(rens, "namecode.xlsx", _xlsx()).status_code == 200
    assert vera.get("/api/desk-products").json()["file"] == "namecode.xlsx"


def test_the_drawings_zip_button_hands_a_product_list_over(app: Any, tmp_path: Path) -> None:
    rick = login(app, "rick")
    z = _zip({"namecode.xlsx": _xlsx(), "__MACOSX/._namecode.xlsx": b"junk"})
    r = rick.post("/api/references", files={"file": ("20261007-151325.zip", z)})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "products" and r.json()["linked_rows"] == 4
    assert (tmp_path / "data" / "models" / "drawing-d1" / "products.json").is_file()
    # a zip with neither drawings nor a list still says so
    r = rick.post("/api/references", files={"file": ("x.zip", _zip({"a.txt": b"x"}))})
    assert r.status_code == 400 and "no drawings found" in r.json()["detail"]


def test_suns_links_need_family_and_type_else_only_a_suggestion(tmp_path: Path) -> None:
    for s in ("suns-daybed-portofino", "suns-chaise-lounge-portofino", "suns-table-kota",
              "suns-side-table-kota", "suns-dining-table-savona-220", "suns-corner-kota",
              "suns-lounge-vento-2-seater-left",
              "suns-lounge-vento-angled-2-seater-left"):  # fmt: skip
        (tmp_path / s).mkdir()
        (tmp_path / s / "cover.json").write_text("{}")
    idx = suns_index(tmp_path)
    assert suns_for("Portofino/ Aspen/ Kota normal D-Bed", idx)["linked"] == [
        "suns-daybed-portofino"]  # fmt: skip
    assert suns_for("Portofino CL right", idx)["linked"] == ["suns-chaise-lounge-portofino"]
    assert suns_for("Kota Lounge table", idx)["linked"] == ["suns-table-kota"]
    assert suns_for("Side table Kota", idx)["linked"] == ["suns-side-table-kota"]
    # "w/o side table" is not a table; a lounge set names no type: suggestions, no tables
    s = suns_for("Kota lounge normal SMALL w/o side table", idx)
    assert s == {"linked": [], "suggested": ["suns-corner-kota"]}
    # an angled 2-seater is not the 2-seater; a left one is not a right one
    assert suns_for("Vento 2 seater", idx)["linked"] == ["suns-lounge-vento-2-seater-left"]
    assert suns_for("Vento 2-seater right", idx)["linked"] == []
    assert kinds("Stockholm/ Savona Sofa set 2-searter bench")[0] == {"seater-2", "bench"}
    assert "seater-2-5" in kinds("Bellano/Sato - 2,5 seater")[0]
