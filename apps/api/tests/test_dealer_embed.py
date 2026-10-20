"""The dealer embed (ADR-150): our configurator on a dealer's website, at the dealer's prices,
behind its domains; our checkout in the dealer's look or the order sent to the dealer."""

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest
from coverapi import dealer_embed as de
from coverapi import shop, shop_suggest
from coverapi.main import create_app
from coverengine import costing
from fastapi.testclient import TestClient

PW = "a-long-admin-password"
DEALER = "https://www.dealer-a.example"
OTHER = "https://evil.example"
SOFA = {
    "product": "sofa",
    "sizes": {"length_cm": 220, "depth_cm": 90, "back_height_cm": 80, "front_height_cm": 60},
}
# what a browser must never see of a dealer price
FORBIDDEN_KEYS = {
    "purchase",
    "purchase_eur",
    "net_eur",
    "gross_eur",
    "margin",
    "margin_pct",
    "margin_eur",
    "cost",
    "cost_eur",
    "costing",
    "b2b",
    "unit_eur",
    "channels",
    "kind_margin_pct",
    "pricing",
    "company_id",
}


def _no_external(*args: Any, **kwargs: Any) -> Any:
    pytest.fail("a dealer embed test tried to call the web")


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(shop_suggest, "run_suggestion", _no_external)
    monkeypatch.setattr("urllib.request.urlopen", _no_external)
    start = threading.Thread.start

    def quiet(thread: threading.Thread) -> None:
        target = getattr(thread, "_target", None)
        if getattr(target, "__module__", "") in {
            "coverapi.jobs",
            "coverapi.shop",
            "coverapi.questions",
            "coverapi.mailer",
        }:
            return
        start(thread)

    monkeypatch.setattr(threading.Thread, "start", quiet)
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>studio</html>")
    a = create_app(tmp_path / "data", web_dir=web, login_required=True)
    user = a.state.auth.add_user("rick", "Rick", "admin", "rick@example.com", True)
    a.state.auth.set_password(a.state.auth.invite(user.id), PW)
    a.state.auth.set_setting(
        "shop", {"shipping": [{"country": "NL", "name": "Nederland", "eur": 12.5}]}
    )
    return a


def _admin(app: Any) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "rick", "password": PW})
    assert r.status_code == 200, r.text
    return c


def _ok(r: Any) -> Any:
    assert r.status_code == 200, r.text
    return r.json()


def _company(app: Any, name: str = "Dealer A", **extra: Any) -> int:
    return int(
        app.state.b2b.add_company(
            {
                "name": name,
                "email": f"{name.split()[-1].lower()}@dealer.example",
                "price_list": "b2b",
                "street": "Kade 1",
                "postcode": "1000 AA",
                "city": "Amsterdam",
                "country": "NL",
                **extra,
            },
            "active",
        )
    )


def _site(
    app: Any,
    admin: TestClient,
    settings: dict[str, Any] | None = None,
    domains: list[str] | None = None,
    company: int | None = None,
) -> dict[str, Any]:
    cid = company or _company(app)
    made = _ok(admin.post("/api/admin/embeds", json={"company_id": cid, "name": "Dealer A site"}))
    sid = made["made"]
    doc = _ok(
        admin.put(
            f"/api/admin/embeds/{sid}",
            json={
                "domains": domains if domains is not None else [DEALER + "/"],
                "settings": settings or {},
            },
        )
    )
    return next(s for s in doc["sites"] if s["id"] == sid)


def _live(app: Any) -> None:
    app.state.auth.set_setting(
        "shop", {**(app.state.auth.setting("shop", {}) or {}), "dealer_embed_enabled": True}
    )


def _walk(doc: Any, path: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            out.append((f"{path}.{k}", k))
            out += _walk(v, f"{path}.{k}")
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out += _walk(v, f"{path}[{i}]")
    else:
        out.append((path, doc))
    return out


def _no_leak(doc: Any, purchase: float) -> None:
    for where, value in _walk(doc):
        assert value not in FORBIDDEN_KEYS, where
        if isinstance(value, int | float) and not isinstance(value, bool):
            assert abs(float(value) - purchase) > 0.004, f"{where} is the purchase price"


def test_off_until_enabled_preview_or_colleague(app: Any) -> None:
    admin = _admin(app)
    site = _site(app, admin)
    key = site["public_key"]
    anon = TestClient(app)
    assert anon.get(f"/api/embed/v1/{key}/config").status_code == 404
    assert anon.get(f"/embed/v1/frame?dealer={key}").status_code == 404
    link = _ok(admin.post("/api/admin/shop/link-key"))["key"]
    for host, status in (("preview.s2dio.living", 200), ("shop.s2dio.living", 404)):
        h = {"x-link-key": link, "x-site-host": host}
        assert anon.get(f"/api/embed/v1/{key}/config", headers=h).status_code == status, host
    assert admin.get(f"/api/embed/v1/{key}/config").status_code == 200  # a colleague
    _live(app)
    assert anon.get(f"/api/embed/v1/{key}/config").status_code == 200


def test_settings_are_checked(app: Any) -> None:
    admin = _admin(app)
    site = _site(app, admin)
    sid = site["id"]
    bad = [
        ({"theme": {"primary": "red"}}, "primary"),
        ({"theme": {"font": "x;}body{display:none"}}, "font"),
        ({"theme": {"logo_url": "http://dealer.example/logo.png"}}, "logo"),
        ({"pricing": {"mode": "list", "list": "b2b"}}, "purchase list"),
        ({"pricing": {"margin_pct": -5}}, "margin"),
        ({"kinds": ["spaceship"]}, "kinds"),
        ({"return_url": "https://elsewhere.example/thanks"}, "return_url"),
    ]
    for settings, word in bad:
        r = admin.put(f"/api/admin/embeds/{sid}", json={"settings": settings})
        assert r.status_code == 400 and word in r.json()["detail"], (settings, r.text)
    for domain in ("http://dealer.example", "https://*.dealer.example", "https://d.example/shop"):
        r = admin.put(f"/api/admin/embeds/{sid}", json={"domains": [domain]})
        assert r.status_code == 400, domain
    # the company's own purchase list is refused too, whatever its name
    app.state.b2b.change_company(site["company_id"], {"price_list": "b2c"})
    r = admin.put(
        f"/api/admin/embeds/{sid}", json={"settings": {"pricing": {"mode": "list", "list": "b2c"}}}
    )
    assert r.status_code == 400
    assert TestClient(app).get("/api/admin/embeds").status_code == 401


def test_origins_cors_and_preflight(app: Any) -> None:
    admin = _admin(app)
    key = _site(app, admin)["public_key"]
    _live(app)
    c = TestClient(app)
    r = c.get(f"/api/embed/v1/{key}/config", headers={"origin": DEALER})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == DEALER
    assert r.headers["cache-control"] == "no-store"
    assert c.get(f"/api/embed/v1/{key}/config", headers={"origin": OTHER}).status_code == 403
    pre = c.options(
        f"/api/embed/v1/{key}/quote",
        headers={"origin": DEALER, "access-control-request-method": "POST"},
    )
    assert pre.status_code == 204 and pre.headers["access-control-allow-origin"] == DEALER
    pre = c.options(f"/api/embed/v1/{key}/quote", headers={"origin": OTHER})
    assert pre.status_code == 403 and "access-control-allow-origin" not in pre.headers
    assert c.post(f"/api/embed/v1/{key}/quote", json=SOFA).status_code == 403  # no Origin
    r = c.post(f"/api/embed/v1/{key}/quote", json=SOFA, headers={"origin": OTHER})
    assert r.status_code == 403
    # an error for the dealer's own page is readable by that page
    r = c.post(
        f"/api/embed/v1/{key}/quote", json={"product": "spaceship"}, headers={"origin": DEALER}
    )
    assert r.status_code == 400 and r.headers["access-control-allow-origin"] == DEALER
    assert c.get("/api/embed/v1/dpk_nosuchdealer/config").status_code == 404


def test_dealer_price_is_b2b_plus_margin_and_never_leaks(app: Any) -> None:
    admin = _admin(app)
    site = _site(
        app,
        admin,
        {
            "pricing": {
                "margin_pct": 40,
                "kind_margin_pct": {"lounger": 10},
                "rounding": "5",
                "show_vat": True,
            }
        },
    )
    key, sid = site["public_key"], site["id"]
    _live(app)
    c = TestClient(app)
    h = {"origin": DEALER}
    example = _ok(admin.get(f"/api/admin/embeds/{sid}/example?product=sofa"))
    purchase = example["purchase_eur"]
    vat = example["vat_pct"]
    assert example["amount"] == costing.round_price(purchase * 1.4 * (1 + vat / 100), "5")
    config = _ok(c.get(f"/api/embed/v1/{key}/config", headers=h))
    _no_leak(config, purchase)
    sizes = {
        f["key"]: f["default"]
        for p in config["products"]
        if p["key"] == "sofa"
        for f in p["fields"]
    }
    got = _ok(
        c.post(f"/api/embed/v1/{key}/quote", json={"product": "sofa", "sizes": sizes}, headers=h)
    )
    assert got["price"]["amount"] == example["amount"] and got["price"]["vat_included"] is True
    _no_leak(got, purchase)
    glb = c.get(got["scene"], headers=h)
    assert glb.status_code == 200 and f"{purchase:.2f}".encode() not in glb.content
    # another kind's own margin
    lounger = _ok(admin.get(f"/api/admin/embeds/{sid}/example?product=lounger"))
    assert lounger["amount"] == costing.round_price(
        lounger["purchase_eur"] * 1.1 * (1 + vat / 100), "5"
    )
    # a company's own fixed price in the B2B list is its purchase price here too
    record = json.loads((app.state.store.root / "embed_quotes" / f"{got['id']}.json").read_text())
    assert record["embed"]["purchase_eur"] == purchase  # on the server only


def test_price_list_mode_and_ex_vat(app: Any) -> None:
    admin = _admin(app)
    site = _site(
        app,
        admin,
        {"pricing": {"mode": "list", "list": "b2c", "rounding": "none", "show_vat": False}},
    )
    _live(app)
    ex = _ok(admin.get(f"/api/admin/embeds/{site['id']}/example?product=sofa"))
    assert ex["vat_included"] is False and ex["amount"] == ex["net_eur"]
    q = _ok(
        TestClient(app).post(
            f"/api/embed/v1/{site['public_key']}/quote", json=SOFA, headers={"origin": DEALER}
        )
    )
    assert q["price"]["vat_included"] is False


def test_kinds_colours_and_view3d_follow_the_settings(app: Any) -> None:
    admin = _admin(app)
    site = _site(
        app,
        admin,
        {
            "kinds": ["sofa"],
            "colours": ["Navy"],
            "view3d": False,
            "lang": "de",
            "languages": ["de", "en"],
            "texts": {"de": {"title": "Unsere Hüllen"}},
        },
    )
    key = site["public_key"]
    _live(app)
    c = TestClient(app)
    h = {"origin": DEALER}
    cfg = _ok(c.get(f"/api/embed/v1/{key}/config?lang=fr", headers=h))
    assert [p["key"] for p in cfg["products"]] == ["sofa"] and cfg["colours"] == ["Navy"]
    assert cfg["lang"] == "de" and cfg["texts"]["title"] == "Unsere Hüllen"  # fr not offered
    assert cfg["texts"]["get_price"] == "Preis berechnen"
    assert _ok(c.get(f"/api/embed/v1/{key}/config?lang=en", headers=h))["texts"]["title"] == (
        "Design your cover"
    )
    r = c.post(f"/api/embed/v1/{key}/quote", json={**SOFA, "product": "lounger"}, headers=h)
    assert r.status_code == 400
    r = c.post(f"/api/embed/v1/{key}/quote", json={**SOFA, "colour": "Taupe"}, headers=h)
    assert r.status_code == 400
    q = _ok(c.post(f"/api/embed/v1/{key}/quote", json=SOFA, headers=h))
    assert q["scene"] is None and q["colour"] == "Navy"
    assert (
        c.post(
            f"/api/embed/v1/{key}/quote", json={**SOFA, "email": "x@y.example"}, headers=h
        ).status_code
        == 422
    )  # no unknown (personal) fields


def test_our_checkout_in_the_dealers_look(app: Any) -> None:
    admin = _admin(app)
    site = _site(
        app,
        admin,
        {
            "checkout": "ours",
            "end_action": "checkout",
            "return_url": DEALER + "/bedankt",
            "theme": {"primary": "#123456", "logo_url": "https://cdn.dealer-a.example/logo.png"},
            "texts": {"nl": {"thanks": "Dank, tot snel!"}},
        },
    )
    key = site["public_key"]
    _live(app)
    c = TestClient(app)
    h = {"origin": DEALER}
    q = _ok(c.post(f"/api/embed/v1/{key}/quote", json=SOFA, headers=h))
    record = json.loads((app.state.store.root / "embed_quotes" / f"{q['id']}.json").read_text())
    purchase = record["embed"]["purchase_eur"]
    url = _ok(
        c.post(f"/api/embed/v1/{key}/checkout", json={"quote_id": q["id"], "lang": "nl"}, headers=h)
    )["checkout_url"]
    path = url.split("://", 1)[1].split("/", 1)[1]
    page = c.get("/" + path)
    assert page.status_code == 200
    assert "#123456" in page.text and "cdn.dealer-a.example/logo.png" in page.text
    assert f"{purchase:.2f}" not in page.text and "Afrekenen" in page.text
    csp = page.headers["content-security-policy"]
    assert "img-src 'self' data: https://cdn.dealer-a.example" in csp
    assert "frame-ancestors 'none'" in csp
    form = {
        "name": "Eva",
        "email": "eva@example.com",
        "street": "Laan 2",
        "postcode": "1234 AB",
        "city": "Utrecht",
        "country": "NL",
        "terms": "1",
    }
    bad = c.post("/" + path, data={**form, "terms": ""}, follow_redirects=False)
    assert bad.status_code == 400
    other = c.post("/" + path, data=form, headers={"origin": OTHER}, follow_redirects=False)
    assert other.status_code == 403
    r = c.post("/" + path, data=form, follow_redirects=False)
    assert r.status_code == 303 and "/embed/v1/order/" in r.headers["location"]
    with sqlite3.connect(app.state.auth.path) as db:
        rows = db.execute("SELECT status, total_eur, data FROM orders").fetchall()
    assert len(rows) == 1
    status, total, data = rows[0]
    d = json.loads(data)
    assert status == "awaiting_payment" and total == round(q["price"]["amount"] + 12.5, 2)
    assert d["dealer"]["purchase_eur"] == purchase and d["dealer"]["mode"] == "ours"
    assert d["quote"]["quote"]["product"] == "sofa"  # production reads the shop's shape
    again = c.post("/" + path, data=form, follow_redirects=False)  # a double click
    assert again.headers["location"] == r.headers["location"]
    with sqlite3.connect(app.state.auth.path) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
    status_page = c.get("/" + r.headers["location"].split("/", 3)[3])
    assert status_page.status_code == 200
    assert DEALER + "/bedankt" in status_page.text and f"{purchase:.2f}" not in status_page.text
    # the same checkout page after the order: the status page
    assert c.get("/" + path, follow_redirects=False).status_code == 303
    # dealer mode is refused for this site
    r = c.post(
        f"/api/embed/v1/{key}/order",
        json={"quote_id": q["id"], "name": "Eva", "email": "eva@example.com"},
        headers=h,
    )
    assert r.status_code == 409


def test_order_sent_to_the_dealer_and_confirmed(app: Any) -> None:
    admin = _admin(app)
    site = _site(app, admin, {"checkout": "dealer", "end_action": "send_order"})
    key = site["public_key"]
    _live(app)
    c = TestClient(app)
    h = {"origin": DEALER}
    q = _ok(c.post(f"/api/embed/v1/{key}/quote", json=SOFA, headers=h))
    order = {
        "quote_id": q["id"],
        "name": "Eva",
        "email": "eva@example.com",
        "phone": "06",
        "street": "Laan 2",
        "postcode": "1234 AB",
        "city": "Utrecht",
        "lang": "nl",
    }
    assert (
        c.post(
            f"/api/embed/v1/{key}/order", json={**order, "website": "bot"}, headers=h
        ).status_code
        == 400
    )  # the honeypot
    assert (
        c.post(f"/api/embed/v1/{key}/checkout", json={"quote_id": q["id"]}, headers=h).status_code
        == 409
    )  # not our checkout here
    ref = _ok(c.post(f"/api/embed/v1/{key}/order", json=order, headers=h))["reference"]
    assert re.fullmatch(r"D\d+", ref)
    with sqlite3.connect(app.state.auth.path) as db:
        mails = db.execute("SELECT recipient, subject, body FROM mail_outbox").fetchall()
        token = db.execute("SELECT token FROM dealer_orders").fetchone()[0]
    to = {m[0]: m for m in mails}
    assert "a@dealer.example" in to and "eva@example.com" in to
    purchase = json.loads((app.state.store.root / "embed_quotes" / f"{q['id']}.json").read_text())[
        "embed"
    ]["purchase_eur"]
    assert f"{purchase:.2f}" in to["a@dealer.example"][2]  # the dealer sees what it buys at
    assert f"{purchase:.2f}" not in to["eva@example.com"][2]  # the customer never
    page = c.get(f"/embed/v1/confirm/{token}")
    assert page.status_code == 200 and f"{purchase:.2f}" in page.text
    assert (
        c.post(
            f"/embed/v1/confirm/{token}", data={"action": "confirm"}, headers={"origin": OTHER}
        ).status_code
        == 403
    )
    done = c.post(f"/embed/v1/confirm/{token}", data={"action": "confirm"})
    assert done.status_code == 200
    c.post(f"/embed/v1/confirm/{token}", data={"action": "confirm"})  # twice: one order
    with sqlite3.connect(app.state.auth.path) as db:
        b2b = db.execute("SELECT net_eur, payment, po FROM b2b_orders").fetchall()
        orders = db.execute("SELECT status, total_eur FROM orders").fetchall()
        status = db.execute("SELECT status FROM dealer_orders").fetchone()[0]
    assert len(b2b) == 1 and b2b[0][1] == "account" and b2b[0][2].startswith("WEB-D")
    assert orders == [("waiting_production", purchase)] and status == "confirmed"


def test_decline_and_cart_event(app: Any) -> None:
    admin = _admin(app)
    site = _site(app, admin, {"checkout": "dealer", "end_action": "send_order"})
    _live(app)
    c = TestClient(app)
    h = {"origin": DEALER}
    key = site["public_key"]
    q = _ok(c.post(f"/api/embed/v1/{key}/quote", json=SOFA, headers=h))
    _ok(
        c.post(
            f"/api/embed/v1/{key}/order",
            json={"quote_id": q["id"], "name": "Eva", "email": "eva@example.com"},
            headers=h,
        )
    )
    with sqlite3.connect(app.state.auth.path) as db:
        token = db.execute("SELECT token FROM dealer_orders").fetchone()[0]
    c.post(f"/embed/v1/confirm/{token}", data={"action": "decline"})
    c.post(f"/embed/v1/confirm/{token}", data={"action": "confirm"})  # too late: declined
    with sqlite3.connect(app.state.auth.path) as db:
        assert db.execute("SELECT status FROM dealer_orders").fetchone()[0] == "declined"
        assert db.execute("SELECT COUNT(*) FROM b2b_orders").fetchone()[0] == 0
    _ok(
        admin.put(
            f"/api/admin/embeds/{site['id']}",
            json={"settings": {"checkout": "dealer", "end_action": "cart"}},
        )
    )
    _ok(c.post(f"/api/embed/v1/{key}/event", json={"type": "cart", "quote_id": q["id"]}, headers=h))
    usage = next(s for s in _ok(admin.get("/api/admin/embeds"))["sites"])["usage"][0]
    assert usage["quote"] == 1 and usage["order"] == 1 and usage["cart"] == 1


def test_verify_with_the_secret_key(app: Any) -> None:
    admin = _admin(app)
    a = _site(app, admin)
    b = _site(app, admin, company=_company(app, "Dealer B"))
    _live(app)
    secret = _ok(admin.post(f"/api/admin/embeds/{a['id']}/secret"))["secret"]
    assert secret.startswith("dsk_")
    c = TestClient(app)
    qa = _ok(
        c.post(f"/api/embed/v1/{a['public_key']}/quote", json=SOFA, headers={"origin": DEALER})
    )
    qb = _ok(
        c.post(f"/api/embed/v1/{b['public_key']}/quote", json=SOFA, headers={"origin": DEALER})
    )
    auth = {"authorization": f"Bearer {secret}"}
    got = _ok(c.get(f"/api/embed/v1/verify/{qa['id']}", headers=auth))
    assert got["price"]["amount"] == qa["price"]["amount"] and got["purchase"]["amount"] > 0
    assert c.get(f"/api/embed/v1/verify/{qb['id']}", headers=auth).status_code == 404
    assert (
        c.get(
            f"/api/embed/v1/verify/{qa['id']}", headers={"authorization": "Bearer dsk_wrong"}
        ).status_code
        == 401
    )
    assert (
        c.get(
            f"/api/embed/v1/{b['public_key']}/scene/{qa['id']}.glb", headers={"origin": DEALER}
        ).status_code
        == 404
    )  # another site's


def test_frame_lists_its_sites_only(app: Any) -> None:
    admin = _admin(app)
    site = _site(app, admin, domains=[DEALER, "https://dealer-a.example"])
    _live(app)
    r = TestClient(app).get(f"/embed/v1/frame?dealer={site['public_key']}&lang=en")
    assert r.status_code == 200 and "<s2dio-configurator" in r.text
    csp = r.headers["content-security-policy"]
    assert f"frame-ancestors 'self' {DEALER} https://dealer-a.example" in csp
    assert "x-frame-options" not in {k.lower() for k in r.headers}
    # the rest of the studio stays unframeable
    assert TestClient(app).get("/").headers["x-frame-options"] == "SAMEORIGIN"


def test_inactive_site_or_blocked_company_is_gone(app: Any) -> None:
    admin = _admin(app)
    site = _site(app, admin)
    _live(app)
    c = TestClient(app)
    url = f"/api/embed/v1/{site['public_key']}/config"
    assert c.get(url).status_code == 200
    _ok(admin.put(f"/api/admin/embeds/{site['id']}", json={"active": False}))
    assert c.get(url).status_code == 404
    _ok(admin.put(f"/api/admin/embeds/{site['id']}", json={"active": True}))
    app.state.b2b.change_company(site["company_id"], {"status": "blocked"})
    assert c.get(url).status_code == 404


def test_order_limits(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    admin = _admin(app)
    site = _site(app, admin)
    _live(app)
    c = TestClient(app)
    h = {"origin": DEALER}
    key = site["public_key"]
    q = _ok(c.post(f"/api/embed/v1/{key}/quote", json=SOFA, headers=h))
    order = {"quote_id": q["id"], "name": "Eva", "email": "eva@example.com"}
    for _ in range(5):
        _ok(c.post(f"/api/embed/v1/{key}/order", json=order, headers=h))
    r = c.post(f"/api/embed/v1/{key}/order", json=order, headers=h)
    assert r.status_code == 429 and "retry-after" in r.headers


def test_demo_dealers_only_on_the_preview_and_never_order(app: Any) -> None:
    admin = _admin(app)
    link = _ok(admin.post("/api/admin/shop/link-key"))["key"]
    _live(app)  # even with the embed on for live, the demo stays on the preview
    c = TestClient(app)
    key = "dpk_demo_voorbeeld"
    assert c.get(f"/api/embed/v1/{key}/config").status_code == 404
    pv = {"x-link-key": link, "x-site-host": "preview.s2dio.living"}
    cfg = _ok(c.get(f"/api/embed/v1/{key}/config", headers=pv))
    assert cfg["demo"] is True and cfg["layout"] == "compact"
    origin = {**pv, "origin": "https://preview.s2dio.living"}
    q = _ok(c.post(f"/api/embed/v1/{key}/quote", json=SOFA, headers=origin))
    assert q["price"]["amount"] > 0
    assert (
        c.post(f"/api/embed/v1/{key}/quote", json=SOFA, headers={**pv, "origin": OTHER}).status_code
        == 403
    )
    sent = _ok(
        c.post(
            f"/api/embed/v1/{key}/order",
            json={"quote_id": q["id"], "name": "E", "email": "e@example.com"},
            headers=origin,
        )
    )
    assert sent["demo"] is True
    ours = "dpk_demo_exemple"
    q2 = _ok(c.post(f"/api/embed/v1/{ours}/quote", json=SOFA, headers=origin))
    url = _ok(
        c.post(f"/api/embed/v1/{ours}/checkout", json={"quote_id": q2["id"]}, headers=origin)
    )["checkout_url"]
    assert url.startswith("https://preview.s2dio.living/embed/v1/checkout/")
    path = "/" + url.split("/", 3)[3]
    form = {
        "name": "E",
        "email": "e@example.com",
        "street": "S 1",
        "postcode": "1",
        "city": "C",
        "country": "NL",
        "terms": "1",
    }
    r = c.post(path, data=form, headers=pv, follow_redirects=False)
    assert r.status_code == 409
    with sqlite3.connect(app.state.auth.path) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM dealer_orders").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM dealer_usage").fetchone()[0] == 0


def test_norm_origin() -> None:
    assert de.norm_origin("https://WWW.Dealer.nl/") == "https://www.dealer.nl"
    assert de.norm_origin("https://dealer.nl:8443") == "https://dealer.nl:8443"
    assert de.norm_origin("http://localhost:3000") == "http://localhost:3000"
    for bad in (
        "http://dealer.nl",
        "https://*.dealer.nl",
        "https://dealer.nl/x",
        "dealer.nl",
        "https://u:p@dealer.nl",
        "javascript:alert(1)",
        "https://dealer",
    ):
        assert de.norm_origin(bad) is None, bad


def test_snippet() -> None:
    s = de.snippet("https://shop.s2dio.living", "dpk_abcdef")
    assert 'type="module"' in s["script"] and "dealer=dpk_abcdef" in s["iframe"]
    assert "allow-same-origin" in s["iframe"]


def test_shop_untouched_by_the_status_url(app: Any) -> None:
    """The shop's own orders still go to the shop's status page (no status_url in their data)."""
    assert shop.SHOP_DEFAULTS["dealer_embed_enabled"] is False
