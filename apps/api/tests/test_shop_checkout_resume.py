"""A checkout whose first request stopped half-way is finished by its retry (ADR-129, Codex's
review): the payment is made once (Mollie's idempotency key), the "new order" mail once, and a
payment still being made by another request is said, never answered without a link."""

import io
import json
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from coverapi import shop as shop_module
from coverapi.main import create_app
from fastapi.testclient import TestClient


class FakeMollie:
    """urllib.request.urlopen for Mollie's create payment: one payment per idempotency key."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, req: Any, timeout: float = 0) -> Any:
        key = req.get_header("Idempotency-key")
        self.calls.append(key)
        link = {"checkout": {"href": f"https://pay.example/{key}"}}
        body = json.dumps({"id": f"tr_test{len(set(self.calls))}", "_links": link})

        class Resp(io.BytesIO):
            def __enter__(self) -> "Resp":
                return self

            def __exit__(self, *a: Any) -> None:
                pass

        return Resp(body.encode())


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
    s = dict(app.state.auth.setting("shop", {}) or {})
    s["payment"] = {"mollie_key": "test_fake", "bank_transfer": True}
    app.state.auth.set_setting("shop", s)
    return {"app": app, "c": c, "order": order, "mails": mails}


def half_made_order(shop: dict[str, Any], key: str) -> int:
    """An order as a request leaves it when the server stops right after the order row: no
    payment link yet, no claim, no mail."""
    app, order = shop["app"], shop["order"]
    record = json.loads(
        (app.state.store.root / "shop_quotes" / f"{order['quote_id']}.json").read_text()
    )
    data = {"customer": order, "quote": record, "shipping_eur": 0, "lang": "nl", "stock": None}
    with sqlite3.connect(app.state.auth.path) as db:
        cur = db.execute(
            "INSERT INTO orders (created, token, status, email, data, total_eur, updated, "
            "idempotency_key) VALUES (?, 'tok-half-made-1', 'awaiting_payment', ?, ?, 100, ?, ?)",
            (time.time(), order["email"], json.dumps(data), time.time(), key),
        )
        return int(cur.lastrowid or 0)


def test_a_retry_finishes_a_checkout_whose_first_request_stopped(
    shop: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeMollie()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    oid = half_made_order(shop, "chk-half-0001")
    body = {**shop["order"], "idempotency_key": "chk-half-0001"}
    r = shop["c"].post("/api/shop/order", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["order"] == oid and r.json()["checkout_url"].startswith("https://pay.")
    again = shop["c"].post("/api/shop/order", json=body)
    assert again.json()["checkout_url"] == r.json()["checkout_url"]
    assert len(fake.calls) == 1 and fake.calls[0]  # one payment, with its idempotency key
    assert shop["mails"].count(f"New order {oid}: EUR 100.0") == 1
    with sqlite3.connect(shop["app"].state.auth.path) as db:
        assert db.execute("SELECT COUNT(*), MAX(mollie_id) FROM orders").fetchone() == (
            1,
            "tr_test1",
        )


def test_a_payment_still_being_made_elsewhere_is_said_not_skipped(
    shop: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shop_module, "ORDER_WAIT_S", 1)
    oid = half_made_order(shop, "chk-busy-0001")
    with sqlite3.connect(shop["app"].state.auth.path) as db:  # another request holds it
        db.execute("UPDATE orders SET data=json_set(data, '$.payment_claim', 'other', "
                   "'$.payment_claim_at', ?) WHERE id=?", (time.time(), oid))  # fmt: skip
    body = {**shop["order"], "idempotency_key": "chk-busy-0001"}
    r = shop["c"].post("/api/shop/order", json=body)
    assert r.status_code == 409 and "try again" in r.json()["detail"]


def test_a_mollie_outage_stays_resumable_and_a_stale_claim_is_taken_over(
    shop: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex's second review: a failed or timed-out Mollie call must not end the checkout
    without a payment link; the next try asks Mollie again with the same idempotency key.
    A claim whose request stopped long ago is taken over."""
    fake = FakeMollie()
    down = {"n": 1}

    def flaky(req: Any, timeout: float = 0) -> Any:
        if down["n"]:
            down["n"] -= 1
            fake.calls.append(req.get_header("Idempotency-key"))
            raise TimeoutError("Mollie did not answer")
        return fake(req, timeout)

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    body = {**shop["order"], "idempotency_key": "chk-flaky-001"}
    first = shop["c"].post("/api/shop/order", json=body)
    assert first.status_code == 502 and "try again" in first.json()["detail"]
    again = shop["c"].post("/api/shop/order", json=body)
    assert again.status_code == 200 and again.json()["checkout_url"].startswith("https://pay.")
    assert len(fake.calls) == 2 and fake.calls[0] == fake.calls[1]  # the same payment key
    assert sum(m.startswith("Order ") and "Mollie refused" in m for m in shop["mails"]) == 1
    # a claim of a request that stopped 10 minutes ago does not block a new checkout's retry
    oid = half_made_order(shop, "chk-stale-001")
    with sqlite3.connect(shop["app"].state.auth.path) as db:
        db.execute("UPDATE orders SET data=json_set(data, '$.payment_claim', 'gone', "
                   "'$.payment_claim_at', ?) WHERE id=?", (time.time() - 600, oid))  # fmt: skip
    r = shop["c"].post(
        "/api/shop/order", json={**shop["order"], "idempotency_key": "chk-stale-001"}
    )
    assert r.status_code == 200 and r.json()["order"] == oid and r.json()["checkout_url"]
