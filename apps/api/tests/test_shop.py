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


def _catalogue(app: Any) -> None:
    import json

    models = app.state.store.models if hasattr(app.state, "store") else None
    assert models is not None
    for mid, cat, size in (("suns-dining-table-a-240", "Tafels", (2400, 1000, 760)),
                           ("suns-dining-table-b-200", "Tafels", (2000, 900, 750))):  # fmt: skip
        d = models / mid
        d.mkdir(parents=True, exist_ok=True)
        (d / "cover.json").write_text(json.dumps({"category": f"Shop › {cat}"}))
        (d / "model.json").write_text(json.dumps({"size_mm": list(size)}))


def _login(app: Any) -> TestClient:
    admin = TestClient(app)
    admin.post("/api/auth/login", json={"username": "rick", "password": "a-long-admin-password"})
    return admin


def test_the_learning_mode_a_colleague_confirms_the_match_first(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-064: in shadow mode the customer leaves an address; a colleague confirms or changes
    the proposal; the customer then sees it; the learning page counts the change."""
    from coverapi import mailer

    sent: list[tuple[str, str]] = []
    admin = _login(app)  # before the mail is on (it would ask for a mailed code)
    monkeypatch.setattr(mailer, "configured", lambda auth: True)
    monkeypatch.setattr(mailer, "send", lambda auth, to, subject, text, html=None:
                        sent.append((to, text)))  # fmt: skip
    _catalogue(app)
    c = TestClient(app)
    sizes = {"table_length_cm": 238, "table_width_cm": 100, "table_height_cm": 76}
    assert (
        c.post("/api/shop/match", json={"product": "dining_set", "sizes": sizes}).status_code == 400
    )
    r = c.post("/api/shop/match", json={"product": "dining_set", "sizes": sizes,
                                        "email": "anna@example.com", "lang": "de"})  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "open" and "match" not in r.json()  # nothing before a person
    token = r.json()["token"]
    assert c.get(f"/api/shop/match/{token}").json() == {"status": "open"}
    req = admin.get("/api/admin/matches").json()["requests"][0]
    assert req["best_model"] == "suns-dining-table-a-240" and req["best_pct"] == 100.0
    a = admin.put(f"/api/admin/matches/{req['id']}", json={"chosen": "suns-dining-table-b-200"})
    assert a.json()["changed"] is True  # the colleague chose another cover: a lesson
    assert any(to == "anna@example.com" and f"/shop/de/match/{token}" in t for to, t in sent)
    seen = c.get(f"/api/shop/match/{token}").json()
    assert seen["match"]["model_id"] == "suns-dining-table-b-200"
    band = admin.get("/api/admin/learning").json()["bands"][0]
    assert band["requests"] == 1 and band["changed"] == 1


def test_auto_mode_answers_at_once_and_an_existing_cover_is_ordered(app: Any) -> None:
    _catalogue(app)
    admin = _login(app)
    admin.put("/api/admin/shop/settings", json={"matching": {"mode": "auto"}})
    c = TestClient(app)
    sizes = {"table_length_cm": 239, "table_width_cm": 99, "table_height_cm": 76}
    r = c.post("/api/shop/match", json={"product": "dining_set", "sizes": sizes}).json()
    assert r["decision"] == "existing" and r["match"]["model_id"] == "suns-dining-table-a-240"
    q = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": sizes,
                                        "stock_model": "suns-dining-table-a-240",
                                        "match_token": r["token"]}).json()  # fmt: skip
    assert q["stock"]["model_id"] == "suns-dining-table-a-240"
    own = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": {
        "table_length_cm": 240, "table_width_cm": 100, "table_height_cm": 76}}).json()  # fmt: skip
    assert q["sizes_cm"] == own["sizes_cm"]  # priced on the existing cover's own sizes
    order = {"quote_id": q["id"], "name": "Anna", "email": "anna@example.com",
             "street": "Dorpsstraat 1", "postcode": "1234 AB", "city": "Utrecht",
             "country": "NL", "terms": True}  # fmt: skip
    oid = c.post("/api/shop/order", json=order).json()["order"]
    assert admin.post(f"/api/admin/orders/{oid}/produce").json()["model_id"] == (
        "suns-dining-table-a-240"  # cut from its own pattern, no new model
    )


def test_the_shop_speaks_every_language_and_the_ai_fills_them_in(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coverengine.ai as ai

    def fake(params: Any, system: str, user: str) -> dict[str, Any]:
        import json

        texts = json.loads(user)["texts"]
        return {"texts": {k: {x: f"[{x}] {v.get('en', '')}" for x in ("de", "fr")}
                          for k, v in texts.items()}}  # fmt: skip

    monkeypatch.setattr(ai, "ask", fake)
    admin = _login(app)
    out = admin.post("/api/admin/cms/translate").json()
    assert out["translated"] > 50  # the texts and the buttons, in German and French
    admin.post("/api/admin/cms/publish")
    c = TestClient(app)
    html = c.get("/shop/de/").text
    assert '<html lang="de">' in html and "[de] Your cover." in html
    assert 'hreflang="fr"' in html and 'hreflang="x-default"' in html
    assert "/shop/de/configure" in c.get("/sitemap.xml").text
    words = c.get("/api/shop/info").json()["content"]["ui"]["words"]
    assert words["match_title"]["fr"].startswith("[fr]")


def test_the_fit_question_after_delivery(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlite3
    import time

    from coverapi import mailer

    sent: list[str] = []
    admin = _login(app)
    monkeypatch.setattr(mailer, "configured", lambda auth: True)
    monkeypatch.setattr(mailer, "send", lambda auth, to, subject, text, html=None:
                        sent.append(text))  # fmt: skip
    settings = {"domain": "shop.example.com", "fit_mail": {"enabled": True, "days": 14}}
    admin.put("/api/admin/shop/settings", json=settings)
    c = TestClient(app)
    q = c.post("/api/shop/quote", json={"product": "item", "sizes": {}}).json()
    order = {"quote_id": q["id"], "name": "Anna", "email": "anna@example.com",
             "street": "Dorpsstraat 1", "postcode": "1234 AB", "city": "Utrecht",
             "country": "NL", "terms": True}  # fmt: skip
    oid = c.post("/api/shop/order", json=order).json()["order"]
    with sqlite3.connect(app.state.auth.path) as db:  # shipped three weeks ago
        db.execute("UPDATE orders SET status='shipped', updated=? WHERE id=?",
                   (time.time() - 21 * 86400, oid))  # fmt: skip
    assert app.state.fit_mails() == 1 and app.state.fit_mails() == 0  # once only
    token = next(t for t in sent if "/fit/" in t).split("/fit/")[1].split()[0]
    assert c.post(f"/api/shop/fit/{token}", json={"score": 4, "comment": "past goed"}).json()["ok"]
    photo = c.post(f"/api/shop/fit/{token}/photo", content=b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    assert photo.status_code == 200
    fb = admin.get("/api/admin/feedback").json()["feedback"][0]
    assert fb["score"] == 4 and fb["photo"] == f"order-{oid}.png"


def test_the_film_is_served_with_byte_ranges(app: Any) -> None:
    """ADR-065: the welcome film from data/media, in parts (Safari asks for ranges)."""
    media = app.state.store.root / "media"
    media.mkdir(parents=True, exist_ok=True)
    (media / "welcome.mp4").write_bytes(bytes(range(256)) * 40)
    c = TestClient(app)
    r = c.get("/media/welcome.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    assert c.get("/media/../app.db").status_code == 404
    assert c.get("/media/other.exe").status_code == 404


def test_the_home_film_comes_in_av1_and_h264_with_a_poster(app: Any) -> None:
    """ADR-108: the hero film in two codecs and its poster reach the page through the settings;
    the media names it uses are served."""
    admin = _login(app)
    film = {"film_url": "/media/hero-kota1-h264.mp4", "film_av1": "/media/hero-kota1-av1.mp4",
            "film_poster": "/media/hero-kota1.jpg"}  # fmt: skip
    assert admin.put("/api/admin/shop/settings", json=film).status_code == 200
    got = TestClient(app).get("/api/shop/info").json()["settings"]
    assert {k: got[k] for k in film} == film
    media = app.state.store.root / "media"
    media.mkdir(parents=True, exist_ok=True)
    for name in ("hero-kota1-h264.mp4", "hero-kota1-av1.mp4", "hero-kota1.jpg", "hero-kota1.webp"):
        (media / name).write_bytes(b"x" * 10)
        assert TestClient(app).get(f"/media/{name}").status_code == 200


def test_the_website_reaches_the_studio_with_its_key_and_the_public_does_not(app: Any) -> None:
    """ADR-066: the website (its own domain, a Cloudflare Worker) uses the studio's shop with a
    key; with the link closed, the public is sent to the website and the API refuses them."""
    admin = _login(app)
    key = admin.post("/api/admin/shop/link-key").json()["key"]
    admin.put("/api/admin/shop/settings",
              json={"domain": "hoezen.example", "website_link": {"closed": True}})  # fmt: skip
    public = TestClient(app)
    r = public.get("/shop/de/configure", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "https://hoezen.example/de/configure"
    assert public.post("/api/shop/quote", json={"product": "item"}).status_code == 403
    assert "Disallow: /" in public.get("/robots.txt").text
    site = TestClient(app, headers={"x-link-key": key, "x-client-ip": "203.0.113.9"})
    html = site.get("/shop/de/").text
    assert 'rel="canonical" href="https://hoezen.example/de/"' in html
    assert site.post("/api/shop/quote", json={"product": "item"}).status_code == 200
    assert "https://hoezen.example/configure" in site.get("/sitemap.xml").text
    wrong = TestClient(app, headers={"x-link-key": "not-the-key"})
    assert wrong.post("/api/shop/quote", json={"product": "item"}).status_code == 403
    assert admin.get("/shop/?preview=x").status_code == 200  # colleagues still see the preview


def test_the_story_is_only_for_its_own_model(app: Any) -> None:
    """ADR-067: the scroll story's data comes for the one model set (no other model leaks)."""
    c = TestClient(app)
    assert c.get("/api/shop/story/suns-other.json").status_code == 404
    info = c.get("/api/shop/info").json()
    assert info["settings"]["story_model"] == "suns-2-seater-kota"
    assert info["settings"]["home_story"] is False  # the live home stays until switched on
    assert len(info["content"]["story"]["chapters"]) == 6


LEGAL_PAGES = ("terms", "privacy", "returns", "cookies", "contact", "warranty")


def test_every_consumer_page_is_public_and_the_legal_drafts_say_so(app: Any) -> None:
    """ADR-103: every consumer page answers without a login; a legal page without the owner's
    own text shows our draft, marked "to approve", with the company's details filled in (or a
    "to fill in" mark); the owner's own text replaces the draft."""
    c = TestClient(app)  # no login (the served app requires one for the studio)
    for page in ("", "configure", *LEGAL_PAGES, "en/", "de/configure", "en/returns"):
        r = c.get(f"/shop/{page}")
        assert r.status_code == 200, page
    terms = c.get("/shop/terms").text
    assert "CONCEPT — TER GOEDKEURING" in terms and "6:230p" in terms
    assert "[nog in te vullen: KvK-nummer]" in terms
    assert "<title>Algemene voorwaarden · " in terms
    en = c.get("/shop/en/returns").text
    assert "DRAFT — TO APPROVE" in en and "14 days" in en
    admin = _login(app)
    admin.put("/api/admin/shop/settings", json={"company": {"kvk": "12345678", "name": "Hoes BV"}})
    assert "KvK 12345678" in c.get("/shop/terms").text
    legal = c.get("/api/shop/info").json()["content"]["legal"]
    assert set(LEGAL_PAGES) <= set(legal)
    assert legal["privacy"]["nl"].startswith("CONCEPT") and "Hoes BV" in legal["privacy"]["nl"]
    app.state.site.change([{"path": "legal.terms.nl", "value": "Onze eigen voorwaarden."}])
    app.state.site.publish("rick")
    terms = c.get("/shop/terms").text
    assert "Onze eigen voorwaarden." in terms and "CONCEPT" not in terms


def test_search_engines_see_each_page_once_and_never_a_customer_s_own(app: Any) -> None:
    """ADR-103: a title, a description, a canonical address, hreflang and Open Graph per page;
    an unknown address is a real 404; an order's own page is never indexed."""
    c = TestClient(app)
    html = c.get("/shop/en/privacy").text
    assert "<title>Privacy statement · " in html
    assert 'rel="canonical" href="http://testserver/shop/en/privacy"' in html
    assert 'hreflang="de" href="http://testserver/shop/de/privacy"' in html
    assert 'hreflang="x-default"' in html
    assert 'property="og:image" content="http://testserver/brand/og-shop.png"' in html
    assert 'property="og:locale" content="en_GB"' in html
    assert 'name="twitter:card"' in html and 'name="robots"' not in html
    missing = c.get("/shop/studio")
    assert missing.status_code == 404 and 'name="robots" content="noindex"' in missing.text
    assert c.get("/shop/de/index.html").status_code == 404
    order = c.get("/shop/order/abcdefghijkl")
    assert order.status_code == 200 and order.headers["x-robots-tag"] == "noindex"
    assert 'rel="canonical"' not in order.text


def test_the_website_s_robots_and_sitemap(app: Any) -> None:
    """ADR-103: the website's robots.txt allows the shop and keeps the API, the business shop
    and the customers' own pages out; the sitemap lists every public page in every language
    with its alternates."""
    admin = _login(app)
    key = admin.post("/api/admin/shop/link-key").json()["key"]
    admin.put("/api/admin/shop/settings", json={"domain": "hoezen.example"})
    site = TestClient(app, headers={"x-link-key": key, "x-client-ip": "203.0.113.9"})
    robots = site.get("/robots.txt").text
    assert "Allow: /\n" in robots
    for path in ("/api/", "/b2b", "/order/", "/*/order/", "/match/", "/fit/"):
        assert f"Disallow: {path}\n" in robots
    assert "Sitemap: https://hoezen.example/sitemap.xml" in robots
    xml = site.get("/sitemap.xml").text
    for page in LEGAL_PAGES:
        assert f"<loc>https://hoezen.example/{page}</loc>" in xml
        assert f"<loc>https://hoezen.example/fr/{page}</loc>" in xml
    assert 'hreflang="de" href="https://hoezen.example/de/returns"' in xml
    assert "order/" not in xml and "b2b" not in xml


def test_the_public_endpoints_hold_their_limits_and_refuse_bots(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-103: the honeypot refuses a bot; the order, the quote and Mollie's webhook each have
    a per-visitor limit (through the website: the visitor's own address)."""
    from coverapi import mailer

    monkeypatch.setattr(mailer, "configured", lambda auth: False)
    c = TestClient(app)
    q = c.post("/api/shop/quote", json={"product": "item"}).json()
    order = {"quote_id": q["id"], "name": "Anna", "email": "anna@example.com",
             "street": "Dorpsstraat 1", "postcode": "1234 AB", "city": "Utrecht",
             "country": "NL", "terms": True}  # fmt: skip
    assert c.post("/api/shop/order", json={**order, "website": "http://spam"}).status_code == 400
    bot = c.post("/api/shop/match", json={"product": "item", "sizes": {}, "website": "x"})
    assert bot.status_code == 400
    codes = [c.post("/api/shop/order", json=order).status_code for _ in range(10)]
    assert codes[-1] == 429 and codes[0] == 200  # 10 a minute, the bot's try counted too
    hooks = [c.post("/api/shop/mollie", data={"id": "nonsense"}).status_code for _ in range(61)]
    assert hooks[0] == 400 and hooks[-1] == 429
    assert c.post("/api/shop/quote", json={"product": "item"}).status_code == 200  # its own count
    info = c.get("/api/shop/info").json()["settings"]
    assert info["payment_mode"] == "none" and info["indicative"] is True


def test_the_mode_of_payments_follows_the_key_s_prefix() -> None:
    from coverapi.shop import payment_mode

    assert payment_mode({"payment": {"mollie_key": "test_abc"}}) == "test"
    assert payment_mode({"payment": {"mollie_key": "live_abc"}}) == "live"
    assert payment_mode({"payment": {"mollie_key": ""}}) == "none"


def test_the_3d_files_travel_packed(app: Any) -> None:
    """ADR-106: a GLB goes gzip-packed to a browser that takes it (the edge does not pack model
    types), and as it is to one that does not; the edge and the browser may keep it."""
    import gzip

    c = TestClient(app)
    packed = c.get("/api/shop/demo.glb", headers={"accept-encoding": "gzip"})
    assert packed.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in packed.headers["vary"]
    plain = c.get("/api/shop/demo.glb", headers={"accept-encoding": "identity"})
    assert "content-encoding" not in plain.headers
    assert plain.content[:4] == b"glTF" and packed.content == plain.content  # unpacked by httpx
    assert len(gzip.compress(plain.content)) < len(plain.content) / 2
    q = c.post("/api/shop/quote", json={"product": "dining_set", "sizes": {}}).json()
    scene = c.get(q["scene"], headers={"accept-encoding": "gzip"})
    assert scene.content[:4] == b"glTF" and "max-age" in scene.headers["cache-control"]
