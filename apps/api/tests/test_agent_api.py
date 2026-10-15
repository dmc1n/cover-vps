"""The public and company-scoped agent API, its limits and discoverable pages (ADR-139)."""

import io
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from coverapi import bodylimit, shop, shop_suggest
from coverapi.main import create_app
from coverengine.params import Registry
from fastapi.testclient import TestClient
from PIL import Image

PW = "a-long-admin-password"
CODE = "suns-2-seater-kota"
SOFA = {"kind": "sofa", "width": 230, "depth": 90, "height": 85}
SIZES = {"length_cm": 230, "depth_cm": 90, "back_height_cm": 85}
FORBIDDEN = set(
    "cost_eur cost labour_eur labour_minutes margin costing fabric_eur parts_eur "
    "b2b_ex_vat_eur extras_eur email phone customer".split()
)


def _no_external(*args: Any, **kwargs: Any) -> Any:
    pytest.fail("An agent test tried to call AI or the web")


@pytest.fixture()
def factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(shop_suggest, "run_suggestion", _no_external)
    # Mollie uses urllib; forbid it even if an order-link accidentally tries to pay.
    monkeypatch.setattr("urllib.request.urlopen", _no_external)
    # These requests neither produce covers nor send scheduled mail. Avoid leaving the
    # app's unrelated daemon loops alive against temporary databases after each test.
    start = threading.Thread.start

    def start_request_threads(thread: threading.Thread) -> None:
        target = getattr(thread, "_target", None)
        if getattr(target, "__module__", "") in {
            "coverapi.jobs",
            "coverapi.shop",
            "coverapi.questions",
            "coverapi.mailer",
        }:
            return
        start(thread)

    monkeypatch.setattr(threading.Thread, "start", start_request_threads)
    original = shop.shop_params
    count = 0

    def build(*, enabled: bool = True, limits: dict[str, Any] | None = None) -> Any:
        nonlocal count
        count += 1
        if limits:

            def params(auth: Any) -> Any:
                p = original(auth)
                overrides = p.registry.resolve(server=limits)
                return type(p)(
                    p.registry,
                    {**p.flat(), **{k: overrides[k] for k in limits}},
                    {k: p.source(k) for k in p.keys()},
                )

            monkeypatch.setattr(shop, "shop_params", params)
        web = tmp_path / f"web-{count}"
        web.mkdir()
        (web / "index.html").write_text("<html>studio</html>")
        (web / "shop.html").write_text(
            "<html><head><!--SSR-HEAD--></head><body><!--SSR-BODY--></body></html>"
        )
        a = create_app(tmp_path / f"data-{count}", web_dir=web, login_required=True)
        user = a.state.auth.add_user("rick", "Rick", "admin", "rick@example.com", True)
        a.state.auth.set_password(a.state.auth.invite(user.id), PW)
        for code, size, category in (
            (CODE, [2300, 900, 850], "Lounge › Sofasets"),
            ("suns-3-seater-kota", [2800, 900, 850], "Lounge › Sofasets"),
            ("suns-lounge-chair-evora", [800, 850, 900], "Lounge › Loungestoelen"),
        ):
            d = a.state.store.models / code
            d.mkdir(parents=True)
            notes = "SUNS: SUNS-2 Seater-Kota" if code == CODE else code
            (d / "cover.json").write_text(json.dumps({"notes": notes, "category": category}))
            (d / "model.json").write_text(json.dumps({"size_mm": size}))
            (d / "product.jpg").write_bytes(b"\xff\xd8\xfftest")
        if enabled:
            a.state.auth.set_setting("shop", {"agent_api_enabled": True})
        return a

    return build


@pytest.fixture()
def app(factory: Any) -> Any:
    return factory()


def _admin(app: Any) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "rick", "password": PW})
    assert r.status_code == 200, r.text
    return c


def _key(admin: TestClient, company: int | None = None) -> dict[str, Any]:
    """A partner key made as the admin does (Settings → Website & API keys)."""
    r = admin.post("/api/admin/agent-api/keys", json={"name": "partner", "company_id": company})
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def _ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _error(response: Any, status: int, code: str) -> Any:
    assert response.status_code == status, response.text
    assert response.json()["error"] == code
    return response.json()


def test_off_by_default_and_preview_gate(factory: Any) -> None:
    """Only an enabled shop or a preview with its valid link key opens agent routes."""
    a = factory(enabled=False)
    c = TestClient(a)
    _error(c.post("/api/v2/match", json=SOFA), 404, "not_found")
    for path in ("/llms-full.txt", "/shop/measure"):
        assert c.get(path).status_code == 404
    assert "For AI agents" not in c.get("/llms.txt").text
    key = _ok(_admin(a).post("/api/admin/shop/link-key"))["key"]
    for host, with_key, status in (
        ("preview.s2dio.living", True, 200),
        ("preview.s2dio.living", False, 404),
        ("shop.s2dio.living", True, 404),
    ):
        headers = {"x-forwarded-host": host, **({"x-link-key": key} if with_key else {})}
        assert c.post("/api/v2/match", json=SOFA, headers=headers).status_code == status
    a.state.auth.set_setting("shop", {"agent_api_enabled": True})
    _ok(c.post("/api/v2/match", json=SOFA))
    assert c.get("/llms-full.txt").status_code == c.get("/shop/measure").status_code == 200
    assert "## For AI agents" in c.get("/llms.txt").text


def test_match_ranking_units_and_shared_costing(app: Any) -> None:
    """Exact sofa matches rank first and use the configurator's stock and custom prices."""
    c = TestClient(app)
    answer = _ok(c.post("/api/v2/match", json=SOFA))
    first = answer["results"][0]
    assert (first["code"], first["type"], first["confidence"], first["fit_pct"]) == (
        CODE,
        "existing",
        "good",
        100,
    )
    custom = next(r for r in answer["results"] if r["type"] == "made_to_measure")
    assert answer["results"].index(custom) > 0
    assert "front_height" in [s["size"] for s in answer["assumed"]]
    for result in answer["results"]:
        assert result["price"]["amount_eur"] > 0 and result["price"]["vat_included"] is True
        assert "configure?" in result["order_url"] and "product=sofa" in result["order_url"]
    assert f"stock={CODE}" in first["order_url"]
    mm = {**SOFA, "unit": "mm", "width": 2300, "depth": 900, "height": 850}
    assert _ok(c.post("/api/v2/match", json=mm))["results"][0]["code"] == CODE
    assert _ok(c.post("/api/v2/match", json={**SOFA, "width": 280}))["results"][0]["code"] == (
        "suns-3-seater-kota"
    )
    for result, stock in ((custom, {}), (first, {"stock_model": CODE})):
        quoted = _ok(c.post("/api/shop/quote", json={"product": "sofa", "sizes": SIZES, **stock}))
        assert result["price"]["amount_eur"] == quoted["price"]["cover_eur"]


@pytest.mark.parametrize(
    ("changes", "code", "field"),
    [
        ({"depth": None}, "missing_size", "depth"),
        ({"kind": "unknown"}, "unknown_kind", "kind"),
        ({"diameter": 100}, "unknown_size", "diameter"),
        ({"width": 5}, "out_of_range", "width"),
        ({"width": "abc"}, "invalid_field", "width"),
        ({"colour": "unknown"}, "unknown_colour", "colour"),
    ],
)
def test_actionable_errors(app: Any, changes: Any, code: str, field: str) -> None:
    """Invalid kinds and sizes return a field and a useful correction hint."""
    body = {k: v for k, v in {**SOFA, **changes}.items() if v is not None}
    err = _error(TestClient(app).post("/api/v2/match", json=body), 400, code)
    assert err["field"] == field and err["hint"]
    if code == "missing_size":
        assert err["message"] == "depth missing for kind sofa" and "depth" in err["hint"]
    if code == "unknown_kind":
        assert all(k in err["hint"] for k in ("sofa", "corner_sofa", "chair"))


def test_corner_alias_and_unspecified_hand(app: Any) -> None:
    """The L-shape alias works and warns when the sofa's hand is unknown."""
    answer = _ok(
        TestClient(app).post(
            "/api/v2/match",
            json={
                "kind": "L-shape",
                "long_side": 300,
                "short_side": 250,
                "depth": 90,
                "height": 85,
            },
        )
    )
    assert answer["kind"] == "corner_sofa"
    assert any("hand" in n for n in answer["notes"])


@pytest.mark.parametrize("field", ["email", "name", "phone", "address"])
def test_personal_input_is_refused(app: Any, field: str) -> None:
    """Personal fields are rejected before any furniture result is returned."""
    err = _error(
        TestClient(app).post("/api/v2/match", json={**SOFA, field: "private"}), 400, "unknown_field"
    )
    assert "no personal data" in err["hint"]


def _public(value: Any) -> None:
    if isinstance(value, dict):
        assert not FORBIDDEN.intersection(value)
        for child in value.values():
            _public(child)
    elif isinstance(value, list):
        for child in value:
            _public(child)
    elif isinstance(value, str):
        assert "@" not in value


def test_answers_have_no_private_data(app: Any) -> None:
    """Every public JSON endpoint omits personal data and internal costing recursively."""
    c = TestClient(app)
    for path in ("match", "quote", "order-link"):
        _public(_ok(c.post(f"/api/v2/{path}", json=SOFA)))
    for path in ("covers", f"covers/{CODE}", "kinds"):
        _public(_ok(c.get(f"/api/v2/{path}")))


@pytest.fixture()
def limited(factory: Any) -> Any:
    return factory(
        limits={
            "limits.agent_per_hour": 3,
            "limits.agent_anon_per_day": 5,
            "limits.agent_key_per_hour": 10,
            "limits.agent_key_photos_per_day": 2,
        }
    )


def test_hourly_and_daily_caps_and_partner_independence(limited: Any) -> None:
    """Hourly address and global anonymous caps leave partner keys their own allowance."""
    c = TestClient(limited, client=("127.0.0.1", 12345))

    def hit(address: str) -> Any:
        return c.post("/api/v2/match", json=SOFA, headers={"x-forwarded-for": address})

    r = hit("192.0.2.1")
    assert r.status_code == 200
    assert r.headers["ratelimit-limit"] == "3" and r.headers["ratelimit-remaining"] == "2"
    assert int(r.headers["ratelimit-reset"]) > 0
    assert hit("192.0.2.1").status_code == hit("192.0.2.1").status_code == 200
    r = hit("192.0.2.1")
    _error(r, 429, "rate_limited")
    assert r.headers["ratelimit-remaining"] == "0" and int(r.headers["retry-after"]) > 0
    assert hit("192.0.2.2").status_code == hit("192.0.2.2").status_code == 200
    _error(hit("192.0.2.3"), 429, "daily_limit")
    key = _key(_admin(limited))["key"]
    for _ in range(6):
        _ok(c.post("/api/v2/match", json=SOFA, headers={"x-api-key": key}))


def test_ipv6_addresses_share_a_network_count(limited: Any) -> None:
    """IPv6 addresses within a single slash 64 share the same hourly allowance."""
    c = TestClient(limited, client=("127.0.0.1", 12345))
    for suffix in ("1", "2", "3"):
        _ok(c.get("/api/v2/kinds", headers={"x-forwarded-for": f"2001:db8:1:2::{suffix}"}))
    _error(
        c.get("/api/v2/kinds", headers={"x-forwarded-for": "2001:db8:1:2::4"}), 429, "rate_limited"
    )
    _ok(c.get("/api/v2/kinds", headers={"x-forwarded-for": "2001:db8:1:3::1"}))


def test_admin_creates_partner_key(app: Any) -> None:
    """An admin can create a partner key from JSON and see its secret exactly once."""
    admin = _admin(app)
    key = _ok(admin.post("/api/admin/agent-api/keys", json={"name": "partner"}))
    assert key["key"].startswith("cvk_")
    listed = _ok(admin.get("/api/admin/agent-api"))
    assert listed["keys"][0]["id"] == key["id"]
    assert "key" not in listed["keys"][0] and "shown" in listed["keys"][0]
    assert key["key"] not in json.dumps(listed)


def test_keys_are_shown_once_authenticated_and_revocable(app: Any) -> None:
    """Keys are displayed once, work through both headers and stop working after revocation."""
    admin = _admin(app)
    key = _key(admin)
    assert key["key"].startswith("cvk_")
    listed = _ok(admin.get("/api/admin/agent-api"))
    assert "key" not in listed["keys"][0] and listed["keys"][0]["shown"].startswith("cvk_")
    assert key["key"] not in json.dumps(listed)
    c = TestClient(app)
    for headers in ({"x-api-key": key["key"]}, {"authorization": f"Bearer {key['key']}"}):
        _ok(c.post("/api/v2/match", json=SOFA, headers=headers))
    _error(c.post("/api/v2/match", json=SOFA, headers={"x-api-key": "wrong"}), 401, "unknown_key")
    _ok(admin.post(f"/api/admin/agent-api/keys/{key['id']}/revoke"))
    _error(c.get("/api/v2/kinds", headers={"x-api-key": key["key"]}), 401, "unknown_key")


def test_photo_suggestion_requires_key_and_counts_usage(
    limited: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Photo recognition needs a key, translates sizes and stops at its daily photo budget."""
    c = TestClient(limited)
    _error(c.post("/api/v2/suggest"), 401, "key_needed")
    admin = _admin(limited)
    key = _key(admin)
    calls = []

    async def fake(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return {
            "product": "sofa",
            "sizes": {**SIZES, "front_height_cm": 60},
            "check": ["depth_cm"],
            "summary": "a sofa",
            "recognised": None,
            "comparable": None,
            "match": None,
        }

    monkeypatch.setattr(shop_suggest, "run_suggestion", fake)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")

    def suggest() -> Any:
        return c.post(
            "/api/v2/suggest",
            headers={"x-api-key": key["key"]},
            files={"photos": ("sofa.png", buf.getvalue(), "image/png")},
        )

    for _ in range(2):
        r = _ok(suggest())
        assert r["kind"] == "sofa" and r["measure_these"] == ["depth"]
        assert r["sizes"] == {"width": 230, "depth": 90, "height": 85, "front_height": 60}
    _error(suggest(), 429, "daily_limit")
    assert len(calls) == 2
    usage = _ok(admin.get("/api/admin/agent-api"))["usage"]
    assert {row["who"] for row in usage} == {"anonymous", f"key:{key['id']}"}
    assert all(
        set(row) == {"day", "who", "endpoint", "count"} and row["count"] > 0 for row in usage
    )
    assert next(row["count"] for row in usage if row["endpoint"] == "AI suggest") == 2


@pytest.mark.parametrize("role", ["workshop", "viewer"])
def test_key_admin_requires_admin(app: Any, role: str) -> None:
    """Workshop and viewer sessions cannot read or manage API keys."""
    u = app.state.auth.add_user(role, role.title(), role)
    app.state.auth.set_password(app.state.auth.invite(u.id), PW)
    c = TestClient(app)
    _ok(c.post("/api/auth/login", json={"username": role, "password": PW}))
    assert c.get("/api/admin/agent-api").status_code == 403
    assert c.post("/api/admin/agent-api/keys", json={"name": "no"}).status_code == 403


def test_company_prices_never_cross_callers(app: Any) -> None:
    """A company's fixed price reaches only its key and all its prices are exclusive of VAT."""
    a = app.state.b2b.add_company(
        {"name": "Dealer A", "email": "a@a.example", "price_list": "b2b"}, "active"
    )
    b = app.state.b2b.add_company(
        {"name": "Dealer B", "email": "b@b.example", "price_list": "b2b"}, "active"
    )
    app.state.b2b.change_company(a, {"fixed": {CODE: 512.5}})
    admin = _admin(app)
    ka, kb = _key(admin, a), _key(admin, b)
    c = TestClient(app)
    for path, method, body in (
        ("match", "post", SOFA),
        (f"covers/{CODE}", "get", None),
        ("order-link", "post", {"kind": "sofa", "cover_code": CODE}),
    ):
        for key, channel in ((ka, "b2b"), (kb, "b2b"), (None, "b2c")):
            r = getattr(c, method)(
                f"/api/v2/{path}",
                headers={"x-api-key": key["key"]} if key else {},
                **({"json": body} if body else {}),
            )
            data = _ok(r)
            assert r.headers["cache-control"] == "no-store"
            assert "X-Api-Key" in r.headers["vary"]
            result = data["results"][0] if path == "match" else data
            assert result["price"]["vat_included"] is (channel == "b2c")
            assert data.get("price_basis", {"channel": data.get("channel")})["channel"] == channel
            # Short links expose their B2B destination in opens; catalogue/match link directly.
            target = result.get("opens", result["order_url"])
            assert ("/b2b/" in target) is (channel == "b2b")
            if key == ka:
                assert result["price"]["amount_eur"] == 512.5
                if path == "match":
                    custom = next(x for x in data["results"] if x["type"] == "made_to_measure")
                    assert custom["price"]["vat_included"] is False
            else:
                assert result["price"]["amount_eur"] != 512.5 and "512.5" not in r.text
            if key is None:
                assert "/b2b/" not in r.text
    app.state.b2b.change_company(a, {"status": "blocked"})
    _error(
        c.post("/api/v2/match", json=SOFA, headers={"x-api-key": ka["key"]}),
        403,
        "company_inactive",
    )


def test_company_order_link_uses_b2b_url(app: Any) -> None:
    """A company key's order link opens the B2B shop (the link itself is the API's short-lived
    /go/ token; where it leads is `opens`)."""
    cid = app.state.b2b.add_company(
        {"name": "Dealer A", "email": "a@a.example", "price_list": "b2b"}, "active"
    )
    key = _key(_admin(app), cid)
    data = _ok(
        TestClient(app).post(
            "/api/v2/order-link",
            json={"kind": "sofa", "cover_code": CODE},
            headers={"x-api-key": key["key"]},
        )
    )
    assert "/api/v2/go/" in data["order_url"] and "/b2b/" in data["opens"]
    assert data["price_basis"]["channel"] == "b2b"


def test_order_link_reports_price_basis(app: Any) -> None:
    """Order links declare the price channel using the same price basis as other answers."""
    data = _ok(TestClient(app).post("/api/v2/order-link", json=SOFA))
    assert data["price_basis"]["channel"] == "b2c"
    assert data["price_basis"]["vat_included"] is True


def test_b2b_session_is_scoped_to_its_cookie_path(app: Any) -> None:
    """A dealer session uses company prices only on the B2B API mount."""
    b = app.state.b2b
    cid = b.add_company(
        {"name": "Dealer", "email": "dealer@a.example", "price_list": "b2b"}, "active"
    )
    b.change_company(cid, {"fixed": {CODE: 512.5}})
    uid = b.add_user(cid, "dealer@a.example", "Dealer", "en")
    b.set_password(b.token(uid, "invite"), "tall-green-umbrella-77")
    c = TestClient(app)
    login = c.post(
        "/api/b2b/login", json={"email": "dealer@a.example", "password": "tall-green-umbrella-77"}
    )
    _ok(login)
    assert "Path=/api/b2b/" in login.headers["set-cookie"]
    r = c.post("/api/b2b/v2/match", json=SOFA)
    assert _ok(r)["results"][0]["price"]["amount_eur"] == 512.5
    assert "access-control-allow-origin" not in r.headers
    assert r.headers["cache-control"] == "no-store" and "X-Api-Key" in r.headers["vary"]
    public = _ok(c.post("/api/v2/match", json=SOFA))
    assert public["price_basis"]["channel"] == "b2c"
    assert public["results"][0]["price"]["amount_eur"] != 512.5
    _error(TestClient(app).post("/api/b2b/v2/match", json=SOFA), 401, "login_needed")


def test_order_link_redirect_expiry_and_no_order(app: Any) -> None:
    """Order links open checkout without creating an order or payment and expire reliably."""
    c = TestClient(app)
    with sqlite3.connect(app.state.auth.path) as db:
        before = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    link = _ok(c.post("/api/v2/order-link", json=SOFA))
    assert "/api/v2/go/" in link["order_url"] and link["agent_may_pay"] is False
    assert link["expires_in_s"] == Registry.load(None).resolve()["limits.agent_link_hours"] * 3600
    assert any("pay" in x and "site" in x for x in link["what_happens_next"])
    path = urlsplit(link["order_url"]).path
    redirect = c.get(path, follow_redirects=False)
    assert redirect.status_code == 302 and "checkout=1" in redirect.headers["location"]
    with sqlite3.connect(app.state.auth.path) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == before
        db.execute("UPDATE agent_links SET expires=0")
    expired = c.get(path, follow_redirects=False)
    assert expired.status_code == 410 and "expired" in expired.text
    _error(
        c.post(
            "/api/v2/order-link", json={"kind": "sofa", "cover_code": "suns-lounge-chair-evora"}
        ),
        400,
        "kind_mismatch",
    )
    _error(
        c.post("/api/v2/order-link", json={"kind": "sofa", "cover_code": "suns-unknown"}),
        404,
        "unknown_cover",
    )


def test_kinds_docs_and_cors(app: Any) -> None:
    """Kinds describe configured ranges and the API documents its fields with public CORS."""
    from coverengine.quote import PRODUCTS

    c = TestClient(app)
    r = c.get("/api/v2/kinds")
    data = _ok(r)
    assert r.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in r.headers
    sofa = next(k for k in data["kinds"] if k["kind"] == "sofa")
    assert sofa["guide_url"].endswith("measure/sofa") and data["how_to_measure"]["how"]
    fields = {
        "width": "length_cm",
        "depth": "depth_cm",
        "height": "back_height_cm",
        "front_height": "front_height_cm",
    }
    for size in sofa["sizes"]:
        _, lo, hi = PRODUCTS["sofa"]["fields"][fields[size["name"]]]
        assert (size["min_cm"], size["max_cm"]) == (lo, hi)
        assert size["required"] is (size["name"] != "front_height")
        assert size["how_to_measure"]
    assert not any(k["barbecue"] for k in data["kinds"])
    app.state.auth.set_setting("shop", {"agent_api_enabled": True, "bbq_enabled": True})
    assert any(k["barbecue"] for k in _ok(c.get("/api/v2/kinds"))["kinds"])
    spec = _ok(c.get("/api/v2/openapi.json"))
    assert {"/match", "/quote", "/order-link", "/kinds", "/covers/{code}"} <= spec["paths"].keys()
    assert spec["components"]["schemas"]["MatchIn"]["properties"]["width"]["description"]
    docs = c.get("/api/v2/docs")
    assert docs.status_code == 200 and "text/html" in docs.headers["content-type"]
    assert "/api/v2/match" in docs.text
    preflight = c.options("/api/v2/match")
    assert preflight.status_code == 204 and preflight.headers["access-control-allow-origin"] == "*"
    assert "X-Api-Key" in preflight.headers["access-control-allow-headers"]


def _ld(response: Any) -> list[Any]:
    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]
    return [
        json.loads(s)
        for s in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', response.text, re.S
        )
    ]


def test_pages_have_structured_data_and_agent_rules(app: Any) -> None:
    """Measuring and catalogue pages expose structured products, offers and agent rules."""
    c = TestClient(app)
    nodes = _ld(c.get("/shop/measure/sofa"))
    assert next(n for n in nodes if n["@type"] == "Product")["additionalProperty"]
    assert next(n for n in nodes if n["@type"] == "HowTo")["step"]
    product = _ld(c.get(f"/shop/covers/{CODE}"))[0]
    assert product["@type"] == "Product"
    offer = product["offers"]
    assert re.fullmatch(r"\d+\.\d{2}", offer["price"])
    assert offer["priceCurrency"] == "EUR" and offer["availability"].endswith("/MadeToOrder")
    index = _ld(c.get("/shop/covers"))[0]
    assert index["@type"] == "ItemList" and len(index["itemListElement"]) == 3
    full = c.get("/llms-full.txt")
    assert full.status_code == 200
    assert CODE in full.text and "230 × 90 ×" in full.text and "never orders or pays" in full.text
    assert "## For AI agents" in c.get("/llms.txt").text
    assert "/api/v2/docs" in c.get("/llms.txt").text


def test_body_limits_before_parsing_and_photo_route(app: Any) -> None:
    """Oversized match bodies fail before parsing and suggestions receive the photo limit."""
    p = Registry.load(None).resolve()
    limit = int(p["limits.body_mb"] * bodylimit.MIB)
    r = TestClient(app).post(
        "/api/v2/match", content=b"invalid json", headers={"content-length": str(limit + 1)}
    )
    assert r.status_code == 413
    routes = bodylimit.route_limits(p, shop_suggest.MAX_PHOTOS)
    for path in ("/api/v2/suggest", "/api/b2b/v2/suggest"):
        photo_limit = next(size for pattern, size in routes if pattern.fullmatch(path))
        assert photo_limit == shop_suggest.MAX_PHOTOS * p["suggest.photo_max_bytes"] + limit
        assert photo_limit > limit
        assert (
            TestClient(app)
            .post(path, content=b"bad", headers={"content-length": str(photo_limit + 1)})
            .status_code
            == 413
        )


def test_preview_urls_stay_on_preview(factory: Any) -> None:
    """The preview's API links keep its host instead of sending visitors to the live shop."""
    a = factory(enabled=False)
    key = _ok(_admin(a).post("/api/admin/shop/link-key"))["key"]
    headers = {"x-forwarded-host": "preview.s2dio.living", "x-link-key": key}
    c = TestClient(a)
    answer = _ok(c.post("/api/v2/match", json=SOFA, headers=headers))
    for result in answer["results"]:
        assert result["order_url"].startswith("https://preview.s2dio.living/")
        if result["type"] == "existing":
            assert result["page_url"].startswith("https://preview.s2dio.living/")
    assert _ok(c.get(f"/api/v2/covers/{CODE}", headers=headers))["page_url"].startswith(
        "https://preview.s2dio.living/"
    )


def test_parallel_recognitions_cannot_pass_the_daily_slot(
    limited: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex's review: two recognitions at the same moment with one slot left start one paid
    call only (one at a time per key; the slot is taken before any await)."""
    import asyncio

    import httpx

    admin = _admin(limited)
    key = _key(admin)
    calls: list[Any] = []

    async def slow(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        await asyncio.sleep(0.3)
        return {"product": "sofa", "sizes": SIZES, "check": [], "summary": "", "recognised": None,
                "comparable": None, "match": None}  # fmt: skip

    monkeypatch.setattr(shop_suggest, "run_suggestion", slow)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")

    photo = {"photos": ("s.png", buf.getvalue(), "image/png")}
    head = {"x-api-key": key["key"]}

    async def three() -> list[int]:
        transport = httpx.ASGITransport(app=limited)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:

            async def one() -> int:
                r = await c.post("/api/v2/suggest", headers=head, files=photo)
                return r.status_code

            return list(await asyncio.gather(one(), one(), one()))

    assert sorted(asyncio.run(three())) == [200, 429, 429] and len(calls) == 1
    c = TestClient(limited)
    _ok(c.post("/api/v2/suggest", headers=head, files=photo))  # the second of 2 daily slots
    _error(c.post("/api/v2/suggest", headers=head, files=photo), 429, "daily_limit")
    assert len(calls) == 2


def test_a_b2b_login_alone_gets_no_paid_recognition(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex's review: photo recognition needs a partner key; a B2B session is not one."""
    b = app.state.b2b
    cid = b.add_company({"name": "Dealer", "email": "d@d.example", "price_list": "b2b"}, "active")
    uid = b.add_user(cid, "dealer@shop.example", "Dealer", "en")
    b.set_password(b.token(uid, "invite"), "tall-green-umbrella-77")
    c = TestClient(app)
    login = c.post("/api/b2b/login", json={"email": "dealer@shop.example",
                                          "password": "tall-green-umbrella-77"})  # fmt: skip
    assert login.status_code == 200, login.text

    async def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a paid recognition ran")

    monkeypatch.setattr(shop_suggest, "run_suggestion", never)
    _error(c.post("/api/b2b/v2/suggest", data={"url": "https://example.com/sofa"}), 401,
           "key_needed")  # fmt: skip


def test_cover_pages_count_against_the_anonymous_limits(limited: Any) -> None:
    """Codex's review: a cover page computes a price, so it counts like an anonymous call and
    answers 429 (not 404) over the limit."""
    c = TestClient(limited)
    codes = [c.get(f"/shop/covers/{CODE}").status_code for _ in range(5)]
    assert codes[0] == 200 and 429 in codes


def test_3d_previews_count_on_the_work_cap(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex's review, round 3: a new 3D preview counts on the agents' work cap; an ignored
    field makes no new one."""
    c = TestClient(app)
    url = _ok(c.post("/api/v2/match", json=SOFA))["results"][-1]["preview_3d_url"]
    path = url.split("testserver", 1)[1]
    assert c.get(path).status_code == 200
    built: list[Any] = []
    import coverengine.quote as q

    real = q.preview_glb
    monkeypatch.setattr(q, "preview_glb", lambda *a: built.append(a) or real(*a))
    sizes = json.dumps({"length_cm": 230, "depth_cm": 90, "back_height_cm": 85, "x": 1})
    r = c.get("/api/v2/preview.glb", params={"product": "sofa", "sizes": sizes})
    assert r.status_code == 200 and built == []  # the same preview: no new work
    from coverapi.ratelimit import GlobalCap

    monkeypatch.setattr(GlobalCap, "hit", lambda self, now=None: False)
    sizes = json.dumps({"length_cm": 231, "depth_cm": 90, "back_height_cm": 85})
    r = c.get("/api/v2/preview.glb", params={"product": "sofa", "sizes": sizes})
    assert r.status_code == 429 and r.json()["error"] == "busy"


def test_a_recognition_starts_only_with_a_whole_run_of_budget_left(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex's review, round 4: just below the key's day budget no new recognition starts
    (a run's worth, limits.agent_key_eur_per_recognition, must be left)."""
    from coverengine import spend

    key = _key(_admin(app))

    async def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a paid recognition ran")

    monkeypatch.setattr(shop_suggest, "run_suggestion", never)
    monkeypatch.setattr(spend, "visitor_eur", lambda who, now=None: 0.95)  # cap 1.0, run 0.1
    r = TestClient(app).post(
        "/api/v2/suggest", headers={"x-api-key": key["key"]}, data={"url": "https://x.example/s"}
    )
    _error(r, 429, "daily_limit")


@pytest.mark.parametrize("path", ["/shop/covers", "/llms-full.txt", "/shop/measure"])
def test_agent_pages_count_against_the_anonymous_limits(limited: Any, path: str) -> None:
    """Codex's review, round 6: the catalogue pages and llms-full.txt count like anonymous
    calls and answer 429 over the limits."""
    c = TestClient(limited)
    codes = [c.get(path).status_code for _ in range(5)]
    assert codes[0] == 200 and 429 in codes
