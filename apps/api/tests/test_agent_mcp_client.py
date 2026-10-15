"""The MCP server (/mcp, ADR-145) with the official MCP client library (`mcp.Client`), in both
protocol eras: the initialize handshake (2025-11-25) and the stateless 2026-07-28 protocol."""

import json
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest
from coverapi.main import create_app
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

CODE = "suns-2-seater-kota"
TOOLS = [
    "list_kinds",
    "find_cover",
    "get_quote",
    "get_cover",
    "create_order_link",
    "suggest_from_photo",
]


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>studio</html>")
    (web / "shop.html").write_text(
        "<html><head><!--SSR-HEAD--></head><body><!--SSR-BODY--></body></html>"
    )
    a = create_app(tmp_path / "data", web_dir=web, login_required=True)
    d = a.state.store.models / CODE
    d.mkdir(parents=True)
    (d / "cover.json").write_text(
        json.dumps({"notes": "SUNS: SUNS-2 Seater-Kota", "category": "Lounge › Sofasets"})
    )
    (d / "model.json").write_text(json.dumps({"size_mm": [2300, 900, 850]}))
    a.state.auth.set_setting("shop", {"agent_api_enabled": True})
    return a


async def _session(app: Any, mode: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://studio.test", headers=headers
    )
    out: dict[str, Any] = {}
    async with (
        http,
        Client(streamable_http_client("http://studio.test/mcp", http_client=http), mode=mode) as c,
    ):
        out["version"] = c.session.protocol_version
        out["tools"] = await c.list_tools()
        out["find"] = await c.call_tool(
            "find_cover", {"kind": "sofa", "width": 230, "depth": 90, "height": 85}
        )
        out["missing"] = await c.call_tool("find_cover", {"kind": "sofa", "width": 230})
        out["photo"] = await c.call_tool("suggest_from_photo", {"url": "https://example.com/x"})
        out["link"] = await c.call_tool(
            "create_order_link",
            {"kind": "sofa", "width": 230, "depth": 90, "height": 85, "cover_code": CODE},
        )
    return out


@pytest.mark.parametrize(("mode", "version"), [("legacy", "2025-11-25"), ("auto", "2026-07-28")])
def test_the_official_client_finds_a_cover(app: Any, mode: str, version: str) -> None:
    """The SDK's own client negotiates, lists the six tools and finds the Kota cover for a
    230 × 90 × 85 cm sofa; errors carry a hint; no photo recognition without a key; an order
    link is a link only."""
    got = anyio.run(_session, app, mode)
    assert got["version"] == version
    assert [t.name for t in got["tools"].tools] == TOOLS
    find = got["find"]
    assert not find.is_error
    first = find.structured_content["results"][0]
    assert (first["code"], first["confidence"], first["price"]["vat_included"]) == (
        CODE,
        "good",
        True,
    )
    assert json.loads(find.content[0].text) == find.structured_content
    missing = got["missing"]
    assert missing.is_error and missing.structured_content["error"] == "missing_size"
    assert missing.structured_content["field"] == "depth" and missing.structured_content["hint"]
    assert got["photo"].is_error and got["photo"].structured_content["error"] == "key_needed"
    link = got["link"].structured_content
    assert link["agent_may_pay"] is False and "/api/v2/go/" in link["order_url"]


def test_the_official_client_is_refused_where_the_api_is_off(app: Any) -> None:
    """Where the agent API is off (the live shop), /mcp is a 404 for the SDK's client too."""
    app.state.auth.set_setting("shop", {"agent_api_enabled": False})
    with pytest.raises(Exception):  # noqa: B017 - the SDK's error type differs per era
        anyio.run(_session, app, "legacy")


def test_a_key_is_passed_as_bearer(app: Any) -> None:
    """A wrong partner key sent by the client (Authorization: Bearer) is refused, never taken
    as anonymous."""
    got = anyio.run(_session, app, "auto", {"Authorization": "Bearer cvk_wrong"})
    assert got["find"].is_error and got["find"].structured_content["error"] == "unknown_key"
