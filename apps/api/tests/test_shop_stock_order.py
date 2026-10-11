"""ADR-118: an existing cover is ordered directly. The quote for a stock cover takes the stock
price path (the published fixed B2C price, else the configurator's for that cover's own sizes
minus the stock discount), never the custom quote; a fixed price only in the draft is not used;
the delivery promise is a shop setting shown only for existing covers; the order carries the
stock model and its price."""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_match_drawings_shop import _admin, app  # noqa: F401 - the shared fixture

ROOT = Path(__file__).resolve().parents[3]
SIZES = {"table_length_cm": 338, "table_width_cm": 100, "table_height_cm": 75, "chairs": True}
ORDER = {"name": "Anna", "email": "anna@example.com", "street": "Dorpsstraat 1",
         "postcode": "1234 AB", "city": "Utrecht", "country": "NL", "terms": True}  # fmt: skip


def _quote(c: TestClient, stock: str | None = None) -> dict[str, Any]:
    r = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": SIZES,
                                        "stock_model": stock})  # fmt: skip
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def _fix(admin: TestClient, prices: dict[str, float], publish: bool) -> None:
    ps = admin.get("/api/prices").json()["current"]
    ps["channels"]["b2c"]["fixed"] = prices
    assert admin.put("/api/prices/draft", json={"data": ps}).status_code == 200
    if publish:
        assert admin.post("/api/prices/publish", json={"note": "fixed"}).status_code == 200


def test_a_stock_quote_takes_the_fixed_price_and_the_custom_one_does_not(app: Any) -> None:  # noqa: F811
    admin = _admin(app)
    _fix(admin, {"drawing-t1": 777.0}, publish=True)
    c = TestClient(app)
    stock = _quote(c, "drawing-t1")
    custom = _quote(c)
    assert stock["price"]["cover_eur"] == 777.0  # exactly the published fixed price
    assert stock["stock"]["price_source"] == "fixed" and stock["stock"]["price_eur"] == 777.0
    assert stock["price"]["indicative"] is False  # a published price is not an estimate
    assert stock["stock"]["size_cm"][:2] == [340.0, 100.0]  # the cover's own furniture sizes
    assert custom["stock"] is None
    assert custom["price"]["cover_eur"] != stock["price"]["cover_eur"]  # the custom path differs


def test_a_draft_price_is_not_sold_and_no_discount_means_the_computed_price(app: Any) -> None:  # noqa: F811
    """The owner's case on 9 Oct: the price list only in the draft and no stock discount set: the
    stock cover is priced on its own sizes by the configurator, so it may equal a custom quote
    for the same sizes. The quote says so (price_source "stock"), and the page shows the existing
    cover state rather than the made-to-measure one."""
    admin = _admin(app)
    _fix(admin, {"drawing-t1": 777.0}, publish=False)
    c = TestClient(app)
    stock = _quote(c, "drawing-t1")
    assert stock["price"]["cover_eur"] != 777.0  # never a draft price in the shop
    assert stock["stock"]["price_source"] == "stock" and stock["stock"]["discount_pct"] == 0
    own = c.post(
        "/api/shop/quote",
        json={
            "product": "dining_set",
            "sizes": {
                **SIZES,
                "table_length_cm": 340,
                "table_width_cm": 100,
                "table_height_cm": 86,
            },
        },
    ).json()
    assert stock["price"]["cover_eur"] == own["price"]["cover_eur"]


def test_the_delivery_promise_is_a_setting_empty_by_default(app: Any) -> None:  # noqa: F811
    c = TestClient(app)
    assert c.get("/api/shop/info").json()["settings"]["stock_delivery_note"] == {}
    admin = _admin(app)
    note = {"nl": "Vandaag besteld, morgen in huis", "en": "Ordered today, delivered tomorrow",
            "de": " ", "fr": ""}  # fmt: skip
    assert admin.put("/api/admin/shop/settings",
                     json={"stock_delivery_note": note}).status_code == 200  # fmt: skip
    shown = c.get("/api/shop/info").json()["settings"]["stock_delivery_note"]
    assert shown == {"nl": note["nl"], "en": note["en"]}  # blank languages: hidden
    overlay = json.loads((ROOT / "apps" / "site" / "preview-overlay.json").read_text())
    pre = overlay["settings"]["stock_delivery_note"]
    assert pre == {"nl": "Vandaag besteld, morgen in huis",
                   "en": "Ordered today, delivered tomorrow",
                   "de": "Heute bestellt, morgen geliefert",
                   "fr": "Commandé aujourd'hui, livré demain"}  # fmt: skip


def test_a_stock_order_carries_its_model_and_price(app: Any) -> None:  # noqa: F811
    admin = _admin(app)
    _fix(admin, {"drawing-t1": 777.0}, publish=True)
    c = TestClient(app)
    q = _quote(c, "drawing-t1")
    r = c.post("/api/shop/order", json={**ORDER, "quote_id": q["id"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["stock"]["model_id"] == "drawing-t1" and d["total_eur"] == 777.0  # no shipping set
    token = d["status_url"].rsplit("/", 1)[1]
    status = c.get(f"/api/shop/order/{token}").json()
    assert status["stock"] == q["stock"]["name"]
    import sqlite3

    with sqlite3.connect(app.state.auth.path) as db:
        data = json.loads(db.execute("SELECT data FROM orders WHERE id=?",
                                     (d["order"],)).fetchone()[0])  # fmt: skip
    assert data["stock"]["model_id"] == "drawing-t1" and data["stock"]["price_eur"] == 777.0
    custom = c.post("/api/shop/order", json={**ORDER, "quote_id": _quote(c)["id"]}).json()
    assert custom["stock"] is None
