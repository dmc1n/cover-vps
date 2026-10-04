"""The cover webshop (ADR-062): pages for people and machines, the configurator's proposal with
the rain check, an order without payment set up, the AI CMS's draft and publish, the settings."""

from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>studio</html>")
    (web / "shop.html").write_text(
        '<html lang="nl"><head><!--SSR-HEAD--></head><body><div id="shop"><!--SSR-BODY-->'
        "</div></body></html>"
    )
    a = create_app(tmp_path / "data", web_dir=web, login_required=True)
    u = a.state.auth.add_user("rick", "Rick", "admin", "rick@example.com", True)
    a.state.auth.set_password(a.state.auth.invite(u.id), "a-long-admin-password")
    return a


def test_the_shop_pages_carry_their_content_for_search_engines(app: Any) -> None:
    c = TestClient(app)
    html = c.get("/shop/", headers={"accept-language": "nl"}).text
    assert "<title>" in html and "application/ld+json" in html and "FAQPage" in html
    assert "Jouw hoes" in html  # the text itself, without JavaScript
    assert c.get("/shop/configure").status_code == 200
    assert "Design your cover" in c.get("/llms.txt").text
    assert "/shop/configure" in c.get("/sitemap.xml").text
    assert "Disallow: /api/" in c.get("/robots.txt").text


def test_a_proposal_with_the_rain_check_and_an_order(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverapi import mailer

    monkeypatch.setattr(mailer, "configured", lambda auth: False)
    c = TestClient(app)
    q = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": {"table_length_cm": 220}})
    assert q.status_code == 200, q.text
    d = q.json()
    assert d["rain"]["options"]["none"]["dry"] is False  # a flat table top holds water
    assert d["rain"]["advice"]["support"] == "balloons"
    with_b = c.post(
        "/api/shop/quote",
        json={"product": "dining_set", "sizes": {"table_length_cm": 220}, "support": "balloons"},
    ).json()
    assert with_b["price"]["total_eur"] > d["price"]["total_eur"]
    assert c.get(d["scene"]).content[:4] == b"glTF"
    order = {"quote_id": with_b["id"], "name": "Anna", "email": "anna@example.com",
             "street": "Dorpsstraat 1", "postcode": "1234 AB", "city": "Utrecht",
             "country": "NL", "terms": True}  # fmt: skip
    r = c.post("/api/shop/order", json=order)
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"] is None  # no Mollie key yet: the order waits for payment
    token = r.json()["status_url"].rsplit("/", 1)[1]
    assert c.get(f"/api/shop/order/{token}").json()["status"] == "awaiting_payment"
    assert c.post("/api/shop/order", json={**order, "terms": False}).status_code == 400
    admin = TestClient(app)
    admin.post("/api/auth/login", json={"username": "rick", "password": "a-long-admin-password"})
    assert admin.get("/api/admin/orders").json()["orders"][0]["email"] == "anna@example.com"


def test_the_cms_drafts_previews_and_publishes(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import coverengine.ai as ai

    monkeypatch.setattr(
        ai, "ask",
        lambda params, system, user: {
            "changes": [{"path": "hero.title.nl", "value": "Nieuwe titel"},
                        {"path": "hero.title.en", "value": "New title"}],
            "summary": "the title",
        },
    )  # fmt: skip
    admin = TestClient(app)
    admin.post("/api/auth/login", json={"username": "rick", "password": "a-long-admin-password"})
    r = admin.post("/api/admin/cms/command", json={"text": "a new title please"})
    assert r.status_code == 200, r.text
    state = admin.get("/api/admin/cms").json()
    assert state["draft"]["hero"]["title"]["nl"] == "Nieuwe titel"
    assert state["live"]["hero"]["title"]["nl"] != "Nieuwe titel"  # not live before publishing
    public = TestClient(app)
    assert "Nieuwe titel" not in public.get("/shop/", headers={"accept-language": "nl"}).text
    assert "Nieuwe titel" in public.get(state["preview"], headers={"accept-language": "nl"}).text
    assert admin.post("/api/admin/cms/publish").status_code == 200
    assert "Nieuwe titel" in public.get("/shop/", headers={"accept-language": "nl"}).text
    viewer_cannot = TestClient(app).post("/api/admin/cms/command", json={"text": "hack"})
    assert viewer_cannot.status_code == 401
    auth = app.state.auth
    auth.set_password(auth.invite(auth.add_user("eddy", "Eddy", "editor").id), "a-long-editor-pw")
    editor = TestClient(app)
    editor.post("/api/auth/login", json={"username": "eddy", "password": "a-long-editor-pw"})
    assert editor.post("/api/admin/cms/command", json={"text": "again"}).status_code == 200
    assert editor.post("/api/admin/cms/publish").status_code == 403  # an admin publishes
    assert editor.get("/api/admin/shop/settings").status_code == 403


def test_the_settings_keep_the_payment_key_secret(app: Any) -> None:
    admin = TestClient(app)
    admin.post("/api/auth/login", json={"username": "rick", "password": "a-long-admin-password"})
    r = admin.put("/api/admin/shop/settings",
                  json={"payment": {"mollie_key": "test_abcdefghijklmnop1234"},
                        "company": {"name": "Covers BV"}})  # fmt: skip
    assert r.status_code == 200, r.text
    s = r.json()["settings"]
    assert (
        "abcdefghijklmnop" not in s["payment"]["mollie_key"] and s["company"]["name"] == "Covers BV"
    )
    again = admin.put("/api/admin/shop/settings", json={"payment": s["payment"]})
    assert again.json()["settings"]["payment"]["mollie_key"] == s["payment"]["mollie_key"]
    info = TestClient(app).get("/api/shop/info").json()
    assert info["settings"]["payment"] is True and "mollie_key" not in str(info["settings"])
