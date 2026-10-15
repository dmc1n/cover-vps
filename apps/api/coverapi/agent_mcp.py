"""The MCP server for AI agents (ADR-145, phase 2 of ADR-139): /mcp.

A remote Model Context Protocol server over Streamable HTTP, so Claude, ChatGPT and other
agents can use the shop as tools. Built with the official MCP Python SDK (`mcp`, lowlevel
`Server` + `StreamableHTTPSessionManager`), stateless and with JSON answers (no SSE streams,
no sessions): it speaks the 2026-07-28 protocol (per-request `_meta`, `server/discover`) and
the handshake protocols 2024-11-05 … 2025-11-25 (`initialize`), as the SDK negotiates.

Every tool is a thin wrapper over one /api/v2 request, made in-process through the v2
sub-app with the caller's own headers (its address, its partner key, the Worker's
x-site-host and key): the same code, the same limits, the same price scoping, the same
refusals. So:

- anonymous callers get the public prices and the anonymous limits; a partner key
  (`Authorization: Bearer cvk_…` or `X-Api-Key`) its limits, and a key linked to a B2B
  company that company's prices ex VAT, exactly as the API;
- `suggest_from_photo` (a paid AI call) answers only a partner key;
- `create_order_link` only makes a link: a person opens it, checks, gives the address and
  pays on the site. No tool orders or pays; no personal data is taken or given.

/mcp answers only where the agent API does (`agent_api.agent_on`: the preview, or the shop
setting `agent_api_enabled`); the Worker passes it like /api/v2. The protocol's own messages
(initialize, tools/list, server/discover) are free like the API's docs but count on a
generous hourly window per address (`limits.agent_mcp_per_hour`); each tools/call is one
counted /api/v2 request on top.
"""

from __future__ import annotations

import base64
import binascii
import json
import threading
import time
from collections import deque
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any
from urllib.parse import quote

import httpx
import mcp_types as types
from fastapi import FastAPI
from mcp.server.caching import CacheHint
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.exceptions import MCPError
from starlette.requests import Request
from starlette.routing import Route

from coverapi import agent_api

SERVER_NAME = "s2dio-covers"
MIB = 1024 * 1024
HOUR_MS = int(agent_api.HOUR_S * 1000)
# headers that belong to this HTTP exchange, not to the caller: never passed on to /api/v2
DROP = {
    "host",
    "content-length",
    "content-type",
    "transfer-encoding",
    "accept",
    "accept-encoding",
    "connection",
    "origin",
    "last-event-id",
    "mcp-session-id",
    "mcp-protocol-version",
    "mcp-method",
    "mcp-name",
}
CORS = {
    "Access-Control-Expose-Headers": "Mcp-Protocol-Version, Mcp-Session-Id, Retry-After",
    "Vary": "Origin",
}
MAX_CALLERS = 20000  # the protocol window forgets idle addresses beyond this many
_current: ContextVar[Request | None] = ContextVar("mcp_http_request", default=None)


# ---- the tools: names, descriptions written for models, input schemas ------------------------


def kinds_text() -> str:
    """Which sizes each kind takes (from config/agent_kinds.json), one line per kind."""
    lines = []
    for k, v in agent_api.kinds_doc()["kinds"].items():
        sizes = []
        for s in v["sizes"]:
            if s.get("type") == "boolean":
                sizes.append(f"{s['name']} (yes/no)")
            elif s.get("requires"):
                sizes.append(f"{s['name']} (when {s['requires']} is true)")
            else:
                sizes.append(s["name"] + ("" if s["required"] else " (optional)"))
        bbq = " [barbecue: only while offered, see list_kinds]" if v.get("barbecue") else ""
        lines.append(f"- {k}: {', '.join(sizes)}{bbq}")
    return "\n".join(lines)


UNITS = (
    "All sizes are of the FURNITURE (not the cover), in centimetres; send unit='mm' to give "
    "millimetres instead. Answers give cm and mm."
)
PAYS = (
    "You cannot order or pay: a person opens the order link, checks the choice, gives the "
    "delivery address and pays on the site."
)
NEVER_GUESS = (
    "Never guess sizes: ask the person to measure as list_kinds explains (sizes outside the "
    "range are refused with a hint)."
)


def _plain(schema: dict[str, Any]) -> dict[str, Any]:
    """A pydantic JSON schema made plain for models: `X | None` as X, no titles."""
    props: dict[str, Any] = {}
    for name, p in schema.get("properties", {}).items():
        p = dict(p)
        branches = p.pop("anyOf", None)
        if branches:
            real = [b for b in branches if b.get("type") != "null"]
            if len(real) == 1:
                p = {**real[0], **p}
        p.pop("title", None)
        if p.get("default") is None:
            p.pop("default", None)
        props[name] = p
    out: dict[str, Any] = {
        "type": "object",
        "properties": props,
        "additionalProperties": False,
    }
    if schema.get("required"):
        out["required"] = list(schema["required"])
    return out


def tools() -> list[types.Tool]:
    """The six tools, always in this order (the 2026-07-28 spec: deterministic, the same for
    every caller; suggest_from_photo says itself that it needs a partner key)."""
    kinds = kinds_text()
    read_only = types.ToolAnnotations(
        read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )
    return [
        types.Tool(
            name="list_kinds",
            title="Kinds of furniture and how to measure",
            description=(
                "The kinds of furniture S2DIO makes outdoor covers for, the sizes each kind needs "
                "(required or optional, the range in cm, what each size means and how to measure "
                "it), the fabric colours and the rules. Call this first when unsure which sizes "
                "to ask the person for. Give `kind` for one kind only (aliases like 'L-shape' "
                "work).\n\nKinds and their sizes:\n" + kinds
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "maxLength": 40,
                        "description": "Optional: only this kind (or one of its aliases).",
                    }
                },
                "additionalProperties": False,
            },
            annotations=read_only,
        ),
        types.Tool(
            name="find_cover",
            title="Find the best cover for a piece of furniture",
            description=(
                "Give the kind of furniture and its sizes; get a ranked list: existing covers "
                "that fit (code, fit %, 'good' or 'possible', why, the size differences, the "
                "price, a picture, a 3D preview and an order link) and the made-to-measure "
                "cover (price, lead time, order link). "
                + UNITS
                + " Prices are the public prices in EUR incl. VAT (a business partner key: that "
                "business's prices ex VAT). corner_sofa: give left_right when known. "
                + NEVER_GUESS
                + " "
                + PAYS
                + "\n\nSizes per kind:\n"
                + kinds
            ),
            input_schema=_plain(agent_api.MatchIn.model_json_schema()),
            annotations=read_only,
        ),
        types.Tool(
            name="get_quote",
            title="Price of a made-to-measure cover",
            description=(
                "The price of a cover cut and sewn to these sizes, with options: air vents "
                "(standard) and, for tables, support balloons so rain runs off a flat top. "
                + UNITS
                + " Returns the price (EUR, incl. VAT for the public; a business key: ex VAT), the "
                "cover's own sizes, the lead time and an order link. "
                + PAYS
                + "\n\nSizes per kind:\n"
                + kinds
            ),
            input_schema=_plain(agent_api.QuoteIn.model_json_schema()),
            annotations=read_only,
        ),
        types.Tool(
            name="get_cover",
            title="One existing cover",
            description=(
                "One existing cover by its code (from find_cover): the furniture sizes it fits "
                "(cm and mm), the price, the delivery promise, a picture, a 3D preview, its page "
                "and an order link. " + PAYS
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "maxLength": 130,
                        "description": "The cover's code, e.g. 'suns-2-seater-kota'.",
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["en", "nl", "de", "fr"],
                        "description": "Language of the links' pages (default en).",
                    },
                },
                "required": ["code"],
                "additionalProperties": False,
            },
            annotations=read_only,
        ),
        types.Tool(
            name="create_order_link",
            title="A link for the person to order and pay",
            description=(
                "A short-lived link (24 h) that opens our configurator with these choices, "
                "straight at the checkout, for the PERSON to open. It creates no order and no "
                "payment: the person checks the cover, gives name and delivery address, accepts "
                "the terms and pays on the site (a business: logs in and orders on account). "
                "Give cover_code (from find_cover) to order that existing cover, or leave it out "
                "for made to measure. " + UNITS + " Show the link to the person; never open it "
                "or try to pay yourself.\n\nSizes per kind:\n" + kinds
            ),
            input_schema=_plain(agent_api.LinkIn.model_json_schema()),
            annotations=types.ToolAnnotations(
                read_only_hint=False,
                destructive_hint=False,
                idempotent_hint=False,
                open_world_hint=False,
            ),
        ),
        types.Tool(
            name="suggest_from_photo",
            title="Kind and sizes from a product page or photos (partner key only)",
            description=(
                "PARTNER KEY ONLY (send Authorization: Bearer <key>); anonymous calls are "
                "refused with key_needed. Recognises the furniture from its product page (url) "
                "and/or up to 3 small photos (base64, at most about 1.5 MB together over MCP) "
                "and suggests the kind and sizes in cm, with the sizes the person must still "
                "measure. A paid AI call within the key's daily budget. Then let the person "
                "measure what it lists and call find_cover."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "maxLength": 2000,
                        "description": "The furniture's product page (fetched safely by us).",
                    },
                    "photos": {
                        "type": "array",
                        "maxItems": 3,
                        "description": "Up to 3 photos of the furniture.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "data": {"type": "string", "description": "Base64 image bytes."},
                                "mime_type": {
                                    "type": "string",
                                    "enum": ["image/jpeg", "image/png", "image/webp"],
                                },
                            },
                            "required": ["data", "mime_type"],
                            "additionalProperties": False,
                        },
                    },
                    "lang": {"type": "string", "enum": ["en", "nl", "de", "fr"]},
                },
                "additionalProperties": False,
            },
            annotations=types.ToolAnnotations(
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=False,
                open_world_hint=True,
            ),
        ),
    ]


INSTRUCTIONS = """S2DIO / SUNS: premium covers for outdoor furniture and barbecues, made to measure,
and existing covers of our range.

Flow: 1. list_kinds tells which sizes a kind of furniture needs and how to measure them (cm).
2. find_cover with the kind and the furniture's sizes gives the best existing covers and the
made-to-measure cover, each with its price and an order link. 3. create_order_link gives a
short-lived link straight to the checkout. Show links to the person.

Rules: a person always orders and pays on our site; you never pay. Never guess sizes: ask the
person to measure. No personal data (names, e-mail, addresses) is accepted. Public prices are
in EUR incl. VAT; a business partner key gets that business's prices ex VAT. Errors come back
with a hint saying what to change."""


# ---- one /api/v2 request in-process, with the caller's own headers ---------------------------


class V2Error(Exception):
    def __init__(self, status: int, body: dict[str, Any], headers: dict[str, str]) -> None:
        super().__init__(body.get("message", "error"))
        self.status, self.body, self.headers = status, body, headers


async def call_v2(
    sub: FastAPI,
    request: Request,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
) -> tuple[Any, dict[str, str]]:
    """The v2 sub-app answers as if the caller had asked it directly (its address, key and
    the Worker's headers): its limits, gate and scoping hold. JSON back, or V2Error."""
    headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP}
    client = (request.client.host, request.client.port) if request.client else ("127.0.0.1", 0)
    host = request.headers.get("host", "localhost")
    transport = httpx.ASGITransport(
        app=sub, raise_app_exceptions=False, root_path="/api/v2", client=client
    )
    async with httpx.AsyncClient(transport=transport, base_url=f"http://{host}") as c:
        r = await c.request(
            method,
            "/api/v2" + path,
            json=body,
            params=params,
            data=data,
            files=files,
            headers=headers,
        )
    kept = {
        k: v
        for k, v in r.headers.items()
        if k.lower().startswith("ratelimit-") or k.lower() in ("retry-after", "x-ratelimit-scope")
    }
    try:
        out = r.json()
    except ValueError:
        out = {"error": "error", "message": r.text[:300] or f"HTTP {r.status_code}", "hint": ""}
    if r.status_code >= 400:  # noqa: PLR2004
        raise V2Error(r.status_code, out if isinstance(out, dict) else {}, kept)
    return out, kept


def _result(body: Any, headers: dict[str, str]) -> types.CallToolResult:
    meta = {"ratelimit": headers} if headers else None
    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(body, ensure_ascii=False))],
        structured_content=body,
        _meta=meta,
    )


def _error(e: V2Error) -> types.CallToolResult:
    """The API's error as a tool error the model can act on: code, message, hint, field."""
    b = {k: e.body.get(k) for k in ("error", "message", "hint", "field", "docs")}
    b["status"] = e.status
    if "retry-after" in {k.lower() for k in e.headers}:
        b["retry_after_s"] = int(
            next(v for k, v in e.headers.items() if k.lower() == "retry-after")
        )
    text = f"{b['error']}: {b['message']}"
    if b.get("hint"):
        text += f" Hint: {b['hint']}"
    return types.CallToolResult(
        content=[types.TextContent(text=text)], structured_content=b, is_error=True
    )


def _refuse(code: str, message: str, hint: str, field: str | None = None) -> types.CallToolResult:
    return _error(
        V2Error(400, {"error": code, "message": message, "hint": hint, "field": field}, {})
    )


def _only(args: dict[str, Any], allowed: set[str]) -> types.CallToolResult | None:
    stray = sorted(set(args) - allowed)
    if stray:
        return _refuse(
            "unknown_field",
            f"{stray[0]} is not accepted",
            "This server takes no personal data or unknown fields: the customer gives name "
            "and address on our site. Allowed: " + ", ".join(sorted(allowed)) + ".",
            stray[0],
        )
    return None


# ---- the server -------------------------------------------------------------------------------


class Window:
    """The protocol's own messages per address an hour (in memory)."""

    def __init__(self, max_callers: int = MAX_CALLERS) -> None:
        self.hits: dict[str, deque[float]] = {}
        self.lock = threading.Lock()
        self.max_callers = max_callers
        self.swept = 0.0

    def hit(self, who: str, per_hour: int, now: float | None = None) -> int:
        """0 when allowed, else the seconds to wait."""
        now = time.time() if now is None else now
        with self.lock:
            if len(self.hits) >= self.max_callers and who not in self.hits:
                self._sweep(now)
            times = self.hits.setdefault(who, deque())
            while times and now - times[0] >= agent_api.HOUR_S:
                times.popleft()
            if len(times) >= per_hour:
                return int(times[0] + agent_api.HOUR_S - now) + 1
            times.append(now)
        return 0

    def _sweep(self, now: float) -> None:
        """Forget callers idle for an hour (their window is empty), at most once a minute
        (Codex's review: idle callers were never forgotten); still full: the callers seen
        longest ago go, so memory stays bounded whatever the number of addresses."""
        if now - self.swept >= agent_api.HOUR_S / 60:
            self.swept = now
            for k in [k for k, v in self.hits.items() if not v or now - v[-1] >= agent_api.HOUR_S]:
                del self.hits[k]
        if len(self.hits) >= self.max_callers:
            oldest = sorted(self.hits, key=lambda k: self.hits[k][-1] if self.hits[k] else 0.0)
            for k in oldest[: len(self.hits) - self.max_callers + 1]:
                del self.hits[k]


def build_server(sub: FastAPI) -> Server[Any]:
    from coverapi.shop_suggest import MAX_PHOTOS

    def http_request(ctx: ServerRequestContext[Any]) -> Request:
        r = ctx.request if isinstance(ctx.request, Request) else _current.get()
        if r is None:
            raise MCPError(types.INTERNAL_ERROR, "no HTTP request")
        return r

    async def list_tools(
        ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools())

    async def call_tool(  # noqa: C901, PLR0911
        ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        request = http_request(ctx)
        args = dict(params.arguments or {})
        name = params.name
        try:
            if name == "list_kinds":
                if bad := _only(args, {"kind"}):
                    return bad
                body, h = await call_v2(sub, request, "GET", "/kinds")
                want = args.get("kind")
                if want is not None:
                    found = agent_api.find_kind(str(want))
                    kinds = [k for k in body["kinds"] if found and k["kind"] == found[0]]
                    if not kinds:
                        return _refuse(
                            "unknown_kind",
                            f"unknown kind {want!r}",
                            "Leave kind out to list them all, or use one of: "
                            + ", ".join(k["kind"] for k in body["kinds"])
                            + ".",
                            "kind",
                        )
                    body = {**body, "kinds": kinds}
                return _result(body, h)
            if name == "find_cover":
                return _result(*await call_v2(sub, request, "POST", "/match", body=args))
            if name == "get_quote":
                return _result(*await call_v2(sub, request, "POST", "/quote", body=args))
            if name == "create_order_link":
                return _result(*await call_v2(sub, request, "POST", "/order-link", body=args))
            if name == "get_cover":
                if bad := _only(args, {"code", "lang"}):
                    return bad
                code = args.get("code")
                if not isinstance(code, str) or not code:
                    return _refuse(
                        "missing_field", "code missing", "Codes come from find_cover.", "code"
                    )
                lang = args.get("lang") or "en"
                return _result(
                    *await call_v2(
                        sub,
                        request,
                        "GET",
                        "/covers/" + quote(code, safe=""),
                        params={"lang": str(lang)},
                    )
                )
            if name == "suggest_from_photo":
                if bad := _only(args, {"url", "photos", "lang"}):
                    return bad
                photos = args.get("photos") or []
                if not isinstance(photos, list) or len(photos) > MAX_PHOTOS:
                    return _refuse("invalid_field", f"at most {MAX_PHOTOS} photos", "", "photos")
                files = []
                for i, p in enumerate(photos):
                    try:
                        raw = base64.b64decode(str(p.get("data", "")), validate=True)
                    except (binascii.Error, AttributeError, ValueError):
                        return _refuse(
                            "invalid_field",
                            f"photo {i + 1} is not base64",
                            "Send the image bytes base64-encoded in data, or give url instead.",
                            "photos",
                        )
                    mime = str(p.get("mime_type") or "image/jpeg")
                    files.append(("photos", (f"photo{i + 1}", raw, mime)))
                form = {"url": str(args.get("url") or ""), "lang": str(args.get("lang") or "en")}
                return _result(
                    *await call_v2(sub, request, "POST", "/suggest", data=form, files=files or None)
                )
        except V2Error as e:
            return _error(e)
        raise MCPError(
            types.INVALID_PARAMS,
            f"Unknown tool: {name}",
            {"tools": [t.name for t in tools()]},
        )

    return Server(
        SERVER_NAME,
        version=agent_api.API_VERSION,
        title="S2DIO covers",
        description="Find, price and link to order covers for outdoor furniture.",
        instructions=INSTRUCTIONS,
        # the list is the same for every caller and changes only with a release
        cache_hints={"tools/list": CacheHint(ttl_ms=HOUR_MS, scope="public")},
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def origin_ok(auth: Any, request: Request, origin: str) -> bool:
    """An Origin is valid only when it is one of our own sites: the website the Worker answered
    for (its x-site-host, trusted with its key) or the studio's configured public address.
    MCP clients are not browsers and send none (ADR-145, the spec's DNS-rebinding rule)."""
    from urllib.parse import urlsplit

    from coverapi.shop import link_ok, site_host

    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    if parts.scheme not in ("https", "http") or not parts.netloc:
        return False
    from coverapi.security import DEFAULT_PUBLIC_URL, PUBLIC_URL_KEY

    # configured addresses only: a request's own Host is the attacker's during DNS rebinding
    # (Codex's review, round 2)
    public = str(auth.setting(PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL) or DEFAULT_PUBLIC_URL)
    own = {urlsplit(public).netloc}
    if link_ok(auth, request):
        own.add(site_host(request))
    return parts.netloc.lower() in {h.lower() for h in own if h}


class McpEndpoint:
    """The ASGI app at /mcp: the agent API's gate, CORS, the protocol window, then the SDK's
    stateless Streamable HTTP handling (a fresh manager per request: nothing is kept between
    requests, and no app lifespan is needed)."""

    def __init__(self, auth: Any, sub: FastAPI) -> None:
        self.auth, self.sub = auth, sub
        self.server = build_server(sub)
        self.window = Window()

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        from coverapi.shop import shop_params

        request = Request(scope, receive)
        origin = request.headers.get("origin")
        allowed = origin is None or origin_ok(self.auth, request, origin)
        cors = {**CORS, "Cache-Control": "no-store"}
        if origin is not None and allowed:
            cors["Access-Control-Allow-Origin"] = origin

        async def with_cors(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                hs = list(message.get("headers", []))
                for k, v in cors.items():
                    if not any(h[0].lower() == k.lower().encode() for h in hs):
                        hs.append((k.lower().encode(), v.encode()))
                message = {**message, "headers": hs}
            await send(message)

        async def reply(status: int, body: Any, headers: dict[str, str] | None = None) -> None:
            raw = json.dumps(body).encode() if body is not None else b""
            hs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
            if body is not None:
                hs.append((b"content-type", b"application/json"))
            await with_cors({"type": "http.response.start", "status": status, "headers": hs})
            await with_cors({"type": "http.response.body", "body": raw})

        # live first: where the agent API is off /mcp does not exist, whatever is sent
        if not agent_api.agent_on(self.auth, request):
            await reply(
                404,
                agent_api.error_body(
                    "not_found", "not here", "This MCP server is not open on this address yet."
                ),
            )
            return
        if not allowed:  # the spec: an Origin present and not ours is a 403 (DNS rebinding)
            await reply(
                403,
                agent_api.error_body(
                    "forbidden_origin",
                    "requests from this web page's origin are not accepted",
                    "Call /mcp from an MCP client (server side), not from another site's page.",
                ),
            )
            return
        if request.method == "OPTIONS":  # CORS preflight (our own pages only); no credentials
            await reply(
                204,
                None,
                {
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, "
                    "X-Api-Key, Mcp-Protocol-Version, Mcp-Session-Id, Mcp-Method, Mcp-Name",
                    "Access-Control-Max-Age": "600",
                },
            )
            return
        if request.method != "POST":  # no SSE stream to open (GET) and no session to end
            await reply(
                405,
                {"error": "method_not_allowed", "message": "POST JSON-RPC messages to /mcp"},
                {"Allow": "POST, OPTIONS"},
            )
            return
        p = shop_params(self.auth)
        wait = self.window.hit(self.sub.state.visitor(request), int(p["limits.agent_mcp_per_hour"]))
        if wait:
            await reply(
                429,
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": types.INTERNAL_ERROR,
                        "message": f"too many MCP requests from this address; wait {wait} s",
                    },
                },
                {"Retry-After": str(wait)},
            )
            return
        manager = StreamableHTTPSessionManager(
            self.server,
            json_response=True,
            stateless=True,
            max_request_body_size=int(float(p["limits.body_mb"]) * MIB),
        )
        token = _current.set(request)
        try:
            async with manager.run():
                await manager.handle_request(scope, receive, with_cors)
        finally:
            _current.reset(token)


def install(app: FastAPI, auth: Any, sub: FastAPI) -> None:
    """/mcp on the studio (the website passes it like /api/v2; ADR-145)."""
    endpoint = McpEndpoint(auth, sub)
    app.router.routes.append(Route("/mcp", endpoint=endpoint))
    app.state.agent_mcp = endpoint
