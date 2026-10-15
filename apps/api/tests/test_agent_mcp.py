# ruff: noqa: F811 - the fixtures imported from test_agent_api are parameters here
"""The MCP server (/mcp, ADR-145) in raw JSON-RPC: both protocol eras, every tool, errors with
hints, limits, partner keys and B2B price scoping, no personal data, preview-only exposure.
Written by Codex, reviewed (fixtures shared with test_agent_api)."""

import base64
import io
import json
import sqlite3
from typing import Any

import pytest
from coverapi import shop_suggest
from fastapi.testclient import TestClient
from PIL import Image

# the agent API's own fixtures and helpers: the same app, data, keys and limits
from test_agent_api import (  # noqa: F401 - fixtures
    CODE,
    SIZES,
    SOFA,
    _admin,
    _key,
    _ok,
    _public,
    app,
    factory,
    limited,
)

HEADERS = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
    "mcp-protocol-version": "2025-06-18",
}
TOOLS = [
    "list_kinds",
    "find_cover",
    "get_quote",
    "get_cover",
    "create_order_link",
    "suggest_from_photo",
]


def rpc(client: TestClient, method: str, params: Any = None, *, headers: Any = None) -> Any:
    return client.post(
        "/mcp",
        headers={**HEADERS, **(headers or {})},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


def call(client: TestClient, tool: str, args: Any = None, *, headers: Any = None) -> Any:
    body = _ok(rpc(client, "tools/call", {"name": tool, "arguments": args or {}}, headers=headers))
    assert "result" in body, body
    result = body["result"]
    if not result.get("isError", False):
        _public(result["structuredContent"])
        assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result


def success(result: Any) -> Any:
    assert not result.get("isError", False), result
    return result["structuredContent"]


def refusal(result: Any, code: str, field: str | None = None) -> Any:
    assert result["isError"] is True, result
    data = result["structuredContent"]
    assert data["error"] == code, data
    assert data["hint"], data
    if field is not None:
        assert data["field"] == field, data
    return data


def initialization(version: str) -> dict[str, Any]:
    return {
        "protocolVersion": version,
        "capabilities": {},
        "clientInfo": {"name": "tests", "version": "1"},
    }


@pytest.mark.parametrize("version", ["2025-06-18", "2025-11-25"])
def test_initialize(app: Any, version: str) -> None:
    """Handshake versions negotiate tools and human payment without creating a session."""
    response = rpc(
        TestClient(app),
        "initialize",
        initialization(version),
        headers={"mcp-protocol-version": version},
    )
    result = _ok(response)["result"]
    assert result["protocolVersion"] == version
    assert result["serverInfo"]["name"] == "s2dio-covers"
    assert "tools" in result["capabilities"]
    assert "a person" in result["instructions"] and "pays" in result["instructions"]
    assert "mcp-session-id" not in response.headers


def test_modern_protocol_without_initialize(app: Any) -> None:
    """Modern discovery, listing and calls use independent envelopes and routing headers."""
    c = TestClient(app)
    meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "tests", "version": "1"},
    }
    for method in ("server/discover", "tools/list", "tools/call"):
        params = {"_meta": meta}
        headers = {"mcp-protocol-version": "2026-07-28", "Mcp-Method": method}
        if method == "tools/call":
            params.update(name="list_kinds", arguments={})
            headers["Mcp-Name"] = "list_kinds"
        response = rpc(c, method, params, headers=headers)
        result = _ok(response)["result"]
        assert result["resultType"] == "complete", result
        assert "mcp-session-id" not in response.headers
        if method == "server/discover":
            assert "2026-07-28" in result["supportedVersions"]
            assert "tools" in result["capabilities"]
        elif method == "tools/list":
            assert [t["name"] for t in result["tools"]] == TOOLS
            assert result["ttlMs"] > 0 and result["cacheScope"] == "public"
        else:
            success(result)
            _public(result["structuredContent"])


def test_tool_descriptions_and_schemas(app: Any) -> None:
    """The ordered tool catalogue explains units, measurements, human payment and keys."""
    tools = _ok(rpc(TestClient(app), "tools/list"))["result"]["tools"]
    assert [t["name"] for t in tools] == TOOLS
    for tool in tools:
        assert tool["description"].strip()
        assert tool["inputSchema"]["type"] == "object"
        assert tool["inputSchema"]["additionalProperties"] is False
    description = tools[1]["description"]
    assert "centimetres" in description and "sofa: width, depth, height" in description
    assert "a person" in description and "pays" in description
    assert "partner key" in tools[-1]["description"].lower()


def test_list_kinds(app: Any) -> None:
    """Kinds list all furniture or resolve the L-shape alias to corner sofas only."""
    c = TestClient(app)
    all_kinds = success(call(c, "list_kinds"))["kinds"]
    assert len(all_kinds) > 1 and any(k["kind"] == "sofa" for k in all_kinds)
    assert [k["kind"] for k in success(call(c, "list_kinds", {"kind": "L-shape"}))["kinds"]] == [
        "corner_sofa"
    ]


def test_find_cover_matches_v2(app: Any) -> None:
    """Matching returns the same ranked JSON as v2, in structured and text content."""
    c = TestClient(app)
    data = success(call(c, "find_cover", SOFA))
    assert data["results"][0]["code"] == CODE
    assert data == _ok(c.post("/api/v2/match", json=SOFA))


@pytest.mark.parametrize(
    ("tool", "args", "path", "method"),
    [
        ("get_quote", SOFA, "/api/v2/quote", "post"),
        ("get_cover", {"code": CODE}, f"/api/v2/covers/{CODE}", "get"),
    ],
)
def test_quote_and_cover(app: Any, tool: str, args: Any, path: str, method: str) -> None:
    """Quote and cover tools preserve the API's public facts and prices."""
    c = TestClient(app)
    data = success(call(c, tool, args))
    response = getattr(c, method)(path, **({"json": args} if method == "post" else {}))
    assert data == _ok(response)
    assert data["price"]["amount_eur"] > 0


def test_order_link_creates_no_order(app: Any) -> None:
    """Order links leave order rows untouched and reserve payment for the person."""
    with sqlite3.connect(app.state.auth.path) as db:
        before = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    data = success(call(TestClient(app), "create_order_link", SOFA))
    assert data["agent_may_pay"] is False
    assert "/api/v2/go/" in data["order_url"]
    with sqlite3.connect(app.state.auth.path) as db:
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == before


def test_photo_suggestion(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Recognition refuses anonymous callers and decodes a partner's photo without AI."""
    c = TestClient(app)
    refusal(call(c, "suggest_from_photo"), "key_needed")
    calls = []

    async def fake(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return {
            "product": "sofa",
            "sizes": SIZES,
            "check": ["depth_cm"],
            "summary": "a sofa",
            "recognised": None,
            "comparable": None,
            "match": None,
        }

    monkeypatch.setattr(shop_suggest, "run_suggestion", fake)
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    key = _key(_admin(app))
    data = success(
        call(
            c,
            "suggest_from_photo",
            {
                "photos": [
                    {"data": base64.b64encode(buf.getvalue()).decode(), "mime_type": "image/png"}
                ]
            },
            headers={"Authorization": f"Bearer {key['key']}"},
        )
    )
    assert data["kind"] == "sofa" and data["measure_these"] == ["depth"]
    assert data["sizes"] == {"width": 230, "depth": 90, "height": 85}
    assert len(calls) == 1 and len(calls[0][1]) == 1


@pytest.mark.parametrize(
    ("args", "code", "field"),
    [
        ({k: v for k, v in SOFA.items() if k != "depth"}, "missing_size", "depth"),
        ({**SOFA, "kind": "unknown"}, "unknown_kind", "kind"),
        ({**SOFA, "width": 5}, "out_of_range", "width"),
    ],
)
def test_size_errors_have_hints(app: Any, args: Any, code: str, field: str) -> None:
    """Invalid kinds and missing or out-of-range sizes return actionable tool errors."""
    refusal(call(TestClient(app), "find_cover", args), code, field)


@pytest.mark.parametrize("field", ["email", "name", "address"])
def test_personal_fields_refused(app: Any, field: str) -> None:
    """Personal fields are refused with an explicit no-personal-data hint."""
    data = refusal(
        call(TestClient(app), "find_cover", {**SOFA, field: "private"}), "unknown_field", field
    )
    assert "no personal data" in data["hint"]


def test_unknown_tool(app: Any) -> None:
    """An unknown tool returns JSON-RPC invalid params rather than a tool success."""
    body = _ok(rpc(TestClient(app), "tools/call", {"name": "not_a_tool", "arguments": {}}))
    assert body["error"]["code"] == -32602, body


@pytest.mark.parametrize(
    ("args", "code"),
    [({"code": "missing-cover"}, "unknown_cover"), ({"code": CODE, "extra": "x"}, "unknown_field")],
)
def test_cover_errors(app: Any, args: Any, code: str) -> None:
    """Cover lookup rejects unknown codes and additional fields with hints."""
    refusal(call(TestClient(app), "get_cover", args), code)


def test_shared_hourly_window(limited: Any) -> None:
    """MCP and v2 share one address window and refuse its fourth counted call."""
    c = TestClient(limited, client=("127.0.0.1", 12345))
    headers = {"x-forwarded-for": "192.0.2.1"}
    success(call(c, "list_kinds", headers=headers))
    assert c.get("/api/v2/kinds", headers=headers).status_code == 200
    success(call(c, "list_kinds", headers=headers))
    data = refusal(call(c, "list_kinds", headers=headers), "rate_limited")
    assert data["retry_after_s"] > 0
    assert c.get("/api/v2/kinds", headers=headers).status_code == 429
    success(call(c, "list_kinds", headers={"x-forwarded-for": "192.0.2.2"}))


def test_protocol_window(factory: Any) -> None:
    """Protocol messages have their own HTTP cap and Retry-After header."""
    c = TestClient(factory(limits={"limits.agent_mcp_per_hour": 2}))
    assert rpc(c, "initialize", initialization("2025-06-18")).status_code == 200
    assert rpc(c, "tools/list").status_code == 200
    response = rpc(c, "tools/list")
    assert response.status_code == 429, response.text
    assert int(response.headers["retry-after"]) > 0


def test_partner_scope_and_invalid_keys(limited: Any) -> None:
    """Partner limits survive the wrapper and invalid or revoked keys never become anonymous."""
    admin = _admin(limited)
    key = _key(admin)
    c = TestClient(limited)
    result = call(c, "list_kinds", headers={"Authorization": f"Bearer {key['key']}"})
    success(result)
    limits = {k.lower(): v for k, v in result["_meta"]["ratelimit"].items()}
    assert limits["x-ratelimit-scope"] == "partner" and limits["ratelimit-limit"] == "10"
    refusal(call(c, "list_kinds", headers={"Authorization": "Bearer unknown"}), "unknown_key")
    assert admin.post(f"/api/admin/agent-api/keys/{key['id']}/revoke").status_code == 200
    refusal(call(c, "list_kinds", headers={"x-api-key": key["key"]}), "unknown_key")


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("find_cover", SOFA),
        ("get_cover", {"code": CODE}),
        ("create_order_link", {"kind": "sofa", "cover_code": CODE}),
    ],
)
def test_company_prices_never_cross_callers(app: Any, tool: str, args: Any) -> None:
    """Company keys receive only their own ex-VAT prices while anonymous prices include VAT."""
    admin = _admin(app)
    keys = []
    for name, price in (("Dealer A", 512.5), ("Dealer B", 623.75)):
        cid = app.state.b2b.add_company(
            {"name": name, "email": f"{name[-1]}@dealer.example", "price_list": "b2b"}, "active"
        )
        app.state.b2b.change_company(cid, {"fixed": {CODE: price}})
        keys.append(_key(admin, cid))
    c = TestClient(app)
    for key, name, price, other in (
        (keys[0], "Dealer A", 512.5, 623.75),
        (keys[1], "Dealer B", 623.75, 512.5),
        (None, None, None, None),
    ):
        data = success(call(c, tool, args, headers={"x-api-key": key["key"]} if key else {}))
        result = data["results"][0] if tool == "find_cover" else data
        basis = data["price_basis"]
        assert basis["channel"] == ("b2b" if key else "b2c")
        assert basis["vat_included"] is (key is None)
        assert result["price"]["vat_included"] is (key is None)
        if key:
            assert basis["company"] == name
            assert result["price"]["amount_eur"] == price
            assert str(other) not in json.dumps(data)
        else:
            assert "512.5" not in json.dumps(data) and "623.75" not in json.dumps(data)


def test_preview_exposure(factory: Any) -> None:
    """Only enabled shops or a preview with the Worker's valid link key expose MCP."""
    a = factory(enabled=False)
    c = TestClient(a)
    assert rpc(c, "initialize", initialization("2025-06-18")).status_code == 404
    key = _ok(_admin(a).post("/api/admin/shop/link-key"))["key"]
    for site, with_key, status in (
        ("preview.s2dio.living", True, 200),
        ("preview.s2dio.living", False, 404),
        ("shop.s2dio.living", True, 404),
    ):
        headers = {
            "x-forwarded-host": "covers.suns.nu",
            "x-forwarded-proto": "https",
            "x-site-host": site,
            **({"x-link-key": key} if with_key else {}),
        }
        response = rpc(c, "initialize", initialization("2025-06-18"), headers=headers)
        assert response.status_code == status, (site, with_key, response.text)


def test_methods_and_cors(app: Any) -> None:
    """GET is unsupported; OPTIONS answers our own pages only, without credentials."""
    c = TestClient(app)
    assert c.get("/mcp").status_code == 405
    own = {"origin": "http://testserver"}
    response = c.options("/mcp", headers=own)
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "http://testserver"
    assert "POST" in response.headers["access-control-allow-methods"]
    for header in ("Authorization", "Mcp-Protocol-Version", "Mcp-Method", "Mcp-Name"):
        assert header in response.headers["access-control-allow-headers"]
    assert "access-control-allow-credentials" not in response.headers


def test_a_foreign_origin_is_refused(factory: Any) -> None:
    """Codex's review: the spec's Origin rule (DNS rebinding). No Origin (an MCP client) and
    the site's own origin pass; another site's page is a 403, on the preview too."""
    a = factory(enabled=False)
    key = _ok(_admin(a).post("/api/admin/shop/link-key"))["key"]
    c = TestClient(a)
    preview = {"x-site-host": "preview.s2dio.living", "x-link-key": key}
    assert rpc(c, "tools/list", headers=preview).status_code == 200
    ok = rpc(c, "tools/list", headers={**preview, "origin": "https://preview.s2dio.living"})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "https://preview.s2dio.living"
    for origin in ("https://evil.example", "null", "https://preview.s2dio.living.evil.example"):
        for r in (
            rpc(c, "tools/list", headers={**preview, "origin": origin}),
            c.options("/mcp", headers={**preview, "origin": origin}),
        ):
            assert r.status_code == 403, (origin, r.text)
            assert "access-control-allow-origin" not in r.headers
    # without the Worker's key the preview's origin is not ours either
    r = rpc(
        c,
        "tools/list",
        headers={"x-site-host": "preview.s2dio.living", "origin": "https://preview.s2dio.living"},
    )
    assert r.status_code in (403, 404)


def test_the_protocol_window_forgets_idle_callers() -> None:
    """Codex's review: idle addresses are forgotten after an hour and the window never holds
    more than its cap, whatever the number of addresses."""
    from coverapi.agent_mcp import Window

    w = Window(max_callers=100)
    for i in range(250):
        assert w.hit(f"a{i}", 5, now=1000.0 + i) == 0
        assert len(w.hits) <= 100
    assert "a249" in w.hits and "a0" not in w.hits
    assert w.hit("late", 5, now=1000.0 + 250 + 3600 + 61) == 0
    assert len(w.hits) <= 100
    assert all(w.hits[k] for k in w.hits)
    assert set(w.hits) == {"late"}
    for _ in range(5):
        w.hit("busy", 5, now=9000.0)
    assert w.hit("busy", 5, now=9000.0) > 0
