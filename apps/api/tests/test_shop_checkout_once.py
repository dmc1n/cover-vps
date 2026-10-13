"""One checkout, one order (ADR-129): a double click, a retry or two requests at the same moment
with the same idempotency key make one order (as B2B, ADR-104); a page without a key is
protected too (the same proposal and address, unpaid, within a quarter of an hour)."""

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def shop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from coverapi import mailer

    mails: list[str] = []
    monkeypatch.setattr(mailer, "send", lambda auth, to, subject, text, html=None:
                        mails.append(subject))  # fmt: skip
    app = create_app(tmp_path / "data")
    c = TestClient(app)
    q = c.post("/api/shop/quote", json={"product": "item", "sizes": {}})
    assert q.status_code == 200, q.text
    order = {"quote_id": q.json()["id"], "name": "Anna", "email": "anna@example.com",
             "street": "Dorpsstraat 1", "postcode": "1234 AB", "city": "Utrecht",
             "country": "NL", "terms": True}  # fmt: skip
    return {"app": app, "c": c, "order": order, "mails": mails}


def _orders(app: Any) -> int:
    with sqlite3.connect(app.state.auth.path) as db:
        return int(db.execute("SELECT COUNT(*) FROM orders").fetchone()[0])


def test_the_same_key_makes_one_order(shop: dict[str, Any]) -> None:
    c, order = shop["c"], {**shop["order"], "idempotency_key": "chk-1a2b3c4d5e6f"}
    first = c.post("/api/shop/order", json=order)
    again = c.post("/api/shop/order", json=order)
    assert first.status_code == again.status_code == 200, again.text
    assert first.json()["order"] == again.json()["order"]
    assert first.json()["status_url"] == again.json()["status_url"]
    assert again.json()["repeat"] is True
    assert _orders(shop["app"]) == 1
    assert sum(s.startswith("New order") for s in shop["mails"]) == 1
    # a key used for another customer's order is refused, never answered with that order
    other = {**order, "email": "bob@example.com"}
    assert c.post("/api/shop/order", json=other).status_code == 409
    # a new checkout (a new key) is a new order
    assert c.post("/api/shop/order", json={**order, "idempotency_key": "chk-ffff0000"}).json()[
        "order"] != first.json()["order"]  # fmt: skip


def test_two_requests_at_the_same_moment_make_one_order(shop: dict[str, Any]) -> None:
    order = {**shop["order"], "idempotency_key": "chk-race-0001"}
    out: list[Any] = []
    go = threading.Barrier(4)

    def post() -> None:
        go.wait()
        out.append(TestClient(shop["app"]).post("/api/shop/order", json=order))

    ts = [threading.Thread(target=post) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert all(r.status_code == 200 for r in out), [r.text for r in out]
    assert len({r.json()["order"] for r in out}) == 1
    assert _orders(shop["app"]) == 1


def test_a_page_without_a_key_is_protected_too(shop: dict[str, Any]) -> None:
    c, order = shop["c"], shop["order"]
    a = c.post("/api/shop/order", json=order).json()
    b = c.post("/api/shop/order", json=order).json()
    assert a["order"] == b["order"] and _orders(shop["app"]) == 1
    # another address is another order
    c.post("/api/shop/order", json={**order, "street": "Kerkstraat 2"})
    assert _orders(shop["app"]) == 2
    bad = c.post("/api/shop/order", json={**order, "idempotency_key": "bad key!"})
    assert bad.status_code == 422
