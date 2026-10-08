"""The B2B shop (ADR-101): business accounts apart from the studio's users, logins with the
studio's lock-outs, prices ex VAT from the company's price list (and its own fixed prices),
orders on account into the studio's production flow, and nothing for anyone not logged in."""

import json
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient

PASSWORD = "a-long-dealer-password"


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from coverapi import mailer

    a = create_app(tmp_path / "data", login_required=True)
    u = a.state.auth.add_user("rick", "Rick", "admin", "rick@example.com", True)
    a.state.auth.set_password(a.state.auth.invite(u.id), "a-long-admin-password")
    a.state.mails = []
    monkeypatch.setattr(mailer, "configured", lambda auth: True)
    monkeypatch.setattr(mailer, "send", lambda auth, to, subject, text, html=None:
                        a.state.mails.append((to, subject, text)))  # fmt: skip
    a.state.produced = []
    a.state.shop_produce = a.state.produced.append  # no real calculation in the tests
    models = a.state.store.models
    for mid, size in (("suns-dining-table-a-240", (2400, 1000, 760)),):
        d = models / mid
        d.mkdir(parents=True, exist_ok=True)
        (d / "cover.json").write_text(json.dumps({"category": "Shop › Tafels"}))
        (d / "model.json").write_text(json.dumps({"size_mm": list(size)}))
    return a


def _admin(app: Any) -> TestClient:
    admin = TestClient(app)
    admin.app.state.auth.set_setting("two_factor", False)  # no mailed login code in the tests
    r = admin.post("/api/auth/login", json={"username": "rick",
                                            "password": "a-long-admin-password"})  # fmt: skip
    assert r.status_code == 200, r.text
    return admin


def _dealer(app: Any, admin: TestClient, email: str = "inkoop@dealer.example",
            **company: Any) -> tuple[TestClient, int]:  # fmt: skip
    """A company invited by an admin; its contact sets a password from the mailed link."""
    r = admin.post("/api/admin/b2b/companies", json={
        "name": "Tuincentrum De Linde", "vat_number": "NL001234567B01", "contact": "Joke",
        "email": email, "street": "Lindelaan 4", "postcode": "3511 AA", "city": "Utrecht",
        "country": "NL", "lang": "nl", **company})  # fmt: skip
    assert r.status_code == 200, r.text
    cid = r.json()["company"]["id"]
    assert r.json()["mailed"] and r.json()["company"]["status"] == "invited"
    token = r.json()["link"].rsplit("/", 1)[1]
    c = TestClient(app)
    assert c.get(f"/api/b2b/token/{token}").json()["company"] == r.json()["company"]["name"]
    s = c.post(f"/api/b2b/token/{token}", json={"password": PASSWORD})
    assert s.status_code == 200, s.text
    c.headers["x-b2b-csrf"] = s.json()["csrf"]
    return c, cid


def test_invite_login_and_the_wrong_password_lockout(app: Any) -> None:
    admin = _admin(app)
    _, cid = _dealer(app, admin)
    assert admin.get("/api/admin/b2b/companies").json()["companies"][0]["status"] == "active"
    c = TestClient(app)
    ok = c.post("/api/b2b/login", json={"email": "Inkoop@Dealer.example", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["company"]["name"] == "Tuincentrum De Linde"
    cookie = ok.headers["set-cookie"]
    assert "b2b_session=" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/api/b2b/" in cookie
    assert c.get("/api/b2b/me").json()["user"]["email"] == "inkoop@dealer.example"
    other = TestClient(app)
    for _ in range(5):
        r = other.post("/api/b2b/login", json={"email": "inkoop@dealer.example",
                                               "password": "not-the-password"})  # fmt: skip
        assert r.status_code == 401
    locked = other.post("/api/b2b/login", json={"email": "inkoop@dealer.example",
                                                "password": PASSWORD})  # fmt: skip
    assert locked.status_code == 429  # the right password, but locked for a while
    assert any(a["action"] == "b2b login failed" for a in app.state.auth.audit(50))
    # a reset by mail: the same answer for an unknown address, a link for a known one
    assert TestClient(app).post("/api/b2b/password/forgot",
                                json={"email": "nobody@x.example"}).status_code == 200  # fmt: skip
    n = len(app.state.mails)
    TestClient(app).post("/api/b2b/password/forgot", json={"email": "inkoop@dealer.example"})
    assert len(app.state.mails) == n + 1 and "/b2b/reset/" in app.state.mails[-1][2]


def test_a_consumer_and_a_studio_session_cannot_reach_the_b2b_shop(app: Any) -> None:
    public = TestClient(app)
    for method, path, body in (
        ("get", "/api/b2b/me", None),
        ("get", "/api/b2b/catalogue", None),
        ("get", "/api/b2b/orders", None),
        ("post", "/api/b2b/quote", {"product": "item"}),
        ("post", "/api/b2b/order", {"lines": [{"quote_id": "0" * 16, "qty": 1}]}),
    ):
        r = getattr(public, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 401, (path, r.text)
    studio = _admin(app)  # a studio admin's own session opens nothing in the B2B shop
    assert studio.get("/api/b2b/catalogue").status_code == 401
    assert studio.post("/api/b2b/quote", json={"product": "item"}).status_code == 401
    # nor does a B2B session open the studio
    dealer, _ = _dealer(app, studio)
    assert dealer.get("/api/models").status_code == 401
    assert dealer.get("/api/admin/b2b/companies").status_code == 401
    assert public.get("/api/admin/b2b/companies").status_code == 401


def test_b2b_prices_are_ex_vat_from_the_b2b_list_and_fixed_prices_win(app: Any) -> None:
    admin = _admin(app)
    dealer, cid = _dealer(app, admin)
    q = dealer.post("/api/b2b/quote", json={"product": "item", "rain": False}).json()
    consumer = TestClient(app).post("/api/shop/quote", json={"product": "item"}).json()
    assert q["price"]["ex_vat"] and q["price"]["channel"] == "b2b" and q["price"]["vat_pct"] > 0
    assert q["price"]["source"] == "list"
    assert 0 < q["price"]["unit_eur"] < consumer["price"]["total_eur"]  # ex VAT, lower markup
    stock = {"product": "dining_set", "stock_model": "suns-dining-table-a-240", "rain": False}
    listed = dealer.post("/api/b2b/quote", json=stock).json()
    assert listed["price"]["source"] == "list" and listed["stock"]["name"]
    r = admin.put(f"/api/admin/b2b/companies/{cid}",
                  json={"fixed": {"suns-dining-table-a-240": 123.0, "balloon": 9.0}})  # fmt: skip
    assert r.status_code == 200, r.text
    fixed = dealer.post("/api/b2b/quote", json=stock).json()
    assert fixed["price"]["unit_eur"] == 123.0 and fixed["price"]["source"] == "company_fixed"
    items = dealer.get("/api/b2b/catalogue").json()["items"]
    assert items[0]["model_id"] == "suns-dining-table-a-240" and items[0]["fixed_eur"] == 123.0
    with_b = dealer.post("/api/b2b/quote", json={**stock, "support": "balloons"}).json()
    assert with_b["price"]["support_eur"] == 9.0 * with_b["balloons"]
    bad = admin.put(f"/api/admin/b2b/companies/{cid}", json={"fixed": {"../x": 1.0}})
    assert bad.status_code == 400
    # a reverse-charged company pays no VAT on the order
    admin.put(f"/api/admin/b2b/companies/{cid}", json={"reverse_charge": True})
    assert dealer.get("/api/b2b/me").json()["company"]["vat_pct"] == 0.0


def test_an_order_on_account_goes_to_the_studio_orders_flagged_b2b(app: Any) -> None:
    admin = _admin(app)
    dealer, cid = _dealer(app, admin)
    admin.put(f"/api/admin/b2b/companies/{cid}", json={"addresses": [
        {"label": "Store Amersfoort", "name": "De Linde Amersfoort", "street": "Markt 1",
         "postcode": "3811 AA", "city": "Amersfoort", "country": "nl"}]})  # fmt: skip
    addr = dealer.get("/api/b2b/me").json()["company"]["addresses"][0]
    assert addr["country"] == "NL" and addr["id"]
    a = dealer.post("/api/b2b/quote", json={"product": "item", "rain": False}).json()
    stock = {"product": "dining_set", "rain": False, "stock_model": "suns-dining-table-a-240"}
    b = dealer.post("/api/b2b/quote", json=stock).json()
    body = {"lines": [{"quote_id": a["id"], "qty": 3}, {"quote_id": b["id"], "qty": 1}],
            "address_id": addr["id"], "po": "PO-2026-118", "lang": "nl"}  # fmt: skip
    # without the CSRF token from the session, no order
    no_csrf = TestClient(app, cookies=dealer.cookies)
    assert no_csrf.post("/api/b2b/order", json=body).status_code == 403
    foreign = dealer.post("/api/b2b/order", json=body, headers={"origin": "https://evil.example"})
    assert foreign.status_code == 403
    n = len(app.state.mails)
    r = dealer.post("/api/b2b/order", json=body)
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["net_eur"] == round(a["price"]["unit_eur"] * 3 + b["price"]["unit_eur"], 2)
    assert o["vat_eur"] == round(o["net_eur"] * a["price"]["vat_pct"] / 100, 2)
    assert o["address"]["city"] == "Amersfoort" and o["po"] == "PO-2026-118"
    # one confirmation to the customer, one to the studio's alert address
    to = [m[0] for m in app.state.mails[n:]]
    assert "inkoop@dealer.example" in to and "rick@s2dio.industries" in to
    assert "PO-2026-118" in app.state.mails[n][2]
    rows = admin.get("/api/admin/orders").json()["orders"]
    assert len(rows) == 2 and all(x["status"] == "on_account" for x in rows)
    assert {x["data"]["b2b"]["po"] for x in rows} == {"PO-2026-118"}
    assert {x["data"]["b2b"]["qty"] for x in rows} == {3, 1}
    assert sorted(app.state.produced) == sorted(x["id"] for x in rows)  # into production
    # stock lines go into production from their own pattern (shop.produce reads the record)
    stock_row = next(x for x in rows if x["data"]["quote"]["stock"])
    assert stock_row["data"]["quote"]["stock"]["model_id"] == "suns-dining-table-a-240"
    # the customer's previous orders, and ordering again at today's prices
    mine = dealer.get("/api/b2b/orders").json()["orders"]
    assert mine[0]["po"] == "PO-2026-118" and mine[0]["lines"][0]["status"] == "on_account"
    again = dealer.post(f"/api/b2b/orders/{mine[0]['id']}/reorder").json()["lines"]
    assert [x["qty"] for x in again] == [3, 1] and again[0]["quote"]["id"] != a["id"]
    assert admin.get(f"/api/admin/b2b/orders?company={cid}").json()["orders"][0]["id"] == o["order"]
    # a minimum order
    admin.put("/api/admin/b2b/settings", json={"min_order_eur": 100000})
    small = dealer.post("/api/b2b/order", json={"lines": [{"quote_id": a["id"], "qty": 1}]})
    assert small.status_code == 400 and "minimum" in small.json()["detail"]
    # another company cannot order this company's prices
    other, _ = _dealer(app, admin, "buyer@other.example", name="Other BV")
    stolen = other.post("/api/b2b/order", json={"lines": [{"quote_id": a["id"], "qty": 1}]})
    assert stolen.status_code == 404


def test_a_blocked_company_is_out_at_once(app: Any) -> None:
    admin = _admin(app)
    dealer, cid = _dealer(app, admin)
    assert dealer.get("/api/b2b/me").status_code == 200
    admin.put(f"/api/admin/b2b/companies/{cid}", json={"status": "blocked"})
    assert dealer.get("/api/b2b/me").status_code == 401  # the session ended
    login = {"email": "inkoop@dealer.example", "password": PASSWORD}
    r = TestClient(app).post("/api/b2b/login", json=login)
    assert r.status_code == 403
    n = len(app.state.mails)
    TestClient(app).post("/api/b2b/password/forgot", json={"email": "inkoop@dealer.example"})
    assert len(app.state.mails) == n  # no reset link for a blocked company
    admin.put(f"/api/admin/b2b/companies/{cid}", json={"status": "active"})
    assert TestClient(app).post("/api/b2b/login", json={
        "email": "inkoop@dealer.example", "password": PASSWORD}).status_code == 200  # fmt: skip


def test_an_account_request_lands_in_admin_for_approval(app: Any) -> None:
    public = TestClient(app)
    r = public.post("/api/b2b/request", json={
        "company": "Buitenleven BV", "vat_number": "BE0123456789", "contact": "Pieter",
        "email": "pieter@buitenleven.example", "city": "Gent", "country": "be",
        "message": "We sell garden furniture in three stores.", "lang": "en"})  # fmt: skip
    assert r.status_code == 200, r.text
    assert any("B2B account requested" in m[1] for m in app.state.mails)
    # a request alone cannot log in
    login = {"email": "pieter@buitenleven.example", "password": PASSWORD}
    assert public.post("/api/b2b/login", json=login).status_code == 401
    admin = _admin(app)
    c = admin.get("/api/admin/b2b/companies").json()["companies"][0]
    assert c["status"] == "requested" and c["request"]["message"].startswith("We sell")
    ok = admin.post(f"/api/admin/b2b/companies/{c['id']}/approve").json()
    assert ok["company"]["status"] == "invited" and ok["mailed"]
    assert "/b2b/welcome/" in ok["link"]
    # the studio's own admin API stays for studio admins
    assert TestClient(app).post(f"/api/admin/b2b/companies/{c['id']}/approve").status_code == 401


def test_the_b2b_page_is_served_and_never_indexed(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>studio</html>")
    (web / "shop.html").write_text("<html><!--SSR-HEAD--><!--SSR-BODY--></html>")
    (web / "b2b.html").write_text("<html>b2b</html>")
    a = create_app(tmp_path / "data", web_dir=web, login_required=True)
    r = TestClient(a).get("/shop/b2b/welcome/abc")
    assert r.text == "<html>b2b</html>" and "noindex" in r.headers["x-robots-tag"]
    assert TestClient(a).get("/shop/de/b2b").status_code == 200  # the shop's own page, not ours
