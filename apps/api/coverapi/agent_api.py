"""The API for AI agents and models (ADR-135, docs/plans/agent-access.md): /api/v2.

"AI passes the sizes and the best cover's result comes straight back" (owner, 14 Oct 2026). A
versioned JSON API of its own, with stable English field names, mounted as a FastAPI sub-app
so it has its own OpenAPI (/api/v2/openapi.json) and docs (/api/v2/docs):

- POST /match       the furniture's kind and sizes -> existing covers (fit %, why, size
                    differences, price, delivery, picture, 3D, order link) and made to measure;
- POST /quote       the made-to-measure price for sizes and options;
- POST /order-link  a short-lived link that opens the configurator prefilled at the checkout;
                    it creates nothing paid: a person fills in the delivery and pays on the site;
- GET  /covers, /covers/{code}, /kinds; GET /preview.glb and a cover's picture and 3D;
- POST /suggest     sizes from a photo or a shop link: a partner key only (a paid AI call).

Who calls (`Caller`): anyone without a key (B2C prices incl. VAT; `limits.agent_per_hour` per
address, `limits.agent_anon_per_day` for all anonymous callers together), a partner key from
Settings → Website & API keys (higher limits, photo recognition within a daily budget), a
partner key linked to a B2B company or that company's B2B session on /api/b2b/v2 (the
company's own prices ex VAT, ADR-104; order links into the B2B shop). One company's prices
never reach another caller. Nothing internal is answered: no cost, margin, model files,
patterns, people or orders; nothing personal is accepted (unknown fields are refused).

The whole API answers only where `agent_on`: the shop setting `agent_api_enabled` (off on the
live shop until the owner's go), the preview website (preview.<domain>, through the Worker's
key), or a logged-in colleague. Usage is counted per key or "anonymous" per day in app.db
(counts only) and shown in Settings → Website & API keys.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, create_model
from starlette.exceptions import HTTPException as StarletteHTTPException

API_VERSION = "2.0.0"
KINDS_JSON = Path(__file__).resolve().parents[3] / "config" / "agent_kinds.json"
KEY_PREFIX = "cvk_"
HOUR_S = 3600.0
MM_PER_CM = 10.0
PERCENT = 100.0
CODE = re.compile(r"^(suns|drawing|bbq)-[a-z0-9-]{1,120}$")  # = match_list.STOCK_MODEL
TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
UNCOUNTED = ("/openapi.json", "/docs", "/")  # reading about the API is free
SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  hash TEXT NOT NULL UNIQUE,
  shown TEXT NOT NULL,
  created REAL NOT NULL,
  created_by TEXT,
  company_id INTEGER,
  revoked REAL
);
CREATE TABLE IF NOT EXISTS agent_usage (
  day TEXT NOT NULL,
  who TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, who, endpoint)
);
CREATE TABLE IF NOT EXISTS agent_links (
  token TEXT PRIMARY KEY,
  created REAL NOT NULL,
  expires REAL NOT NULL,
  who TEXT NOT NULL,
  channel TEXT NOT NULL,
  target TEXT NOT NULL
);
"""


# ---- kinds of furniture and their sizes (config/agent_kinds.json) -----------------------------


@lru_cache(maxsize=1)
def kinds_doc() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(KINDS_JSON.read_text(encoding="utf-8"))
    return doc


def _norm(name: str) -> str:
    return re.sub(r"[\s-]+", "_", str(name).strip().lower())


def find_kind(name: str) -> tuple[str, dict[str, Any]] | None:
    """A kind by its name or one of its aliases ("L-shape" -> corner_sofa)."""
    want = _norm(name)
    kinds = kinds_doc()["kinds"]
    if want in kinds:
        return want, kinds[want]
    for k, v in kinds.items():
        if want in (_norm(a) for a in v.get("aliases", [])):
            return k, v
    return None


def kinds_of_product(product: str) -> list[str]:
    return [k for k, v in kinds_doc()["kinds"].items() if v["product"] == product]


def size_names() -> dict[str, str]:
    """Every size name an agent may send (names and aliases of every kind) -> its type."""
    out: dict[str, str] = {}
    for v in kinds_doc()["kinds"].values():
        for s in v["sizes"]:
            for n in [s["name"], *s.get("aliases", [])]:
                out.setdefault(n, s.get("type", "number"))
    return out


def size_help(name: str) -> str:
    """What a size name means across the kinds (for the OpenAPI description)."""
    seen = []
    for k, v in kinds_doc()["kinds"].items():
        for s in v["sizes"]:
            if name == s["name"] or name in s.get("aliases", []):
                alias = "" if name == s["name"] else f" (another name for {s['name']})"
                seen.append(f"{k}: {s['means']}{alias}")
    return "Centimetres unless unit is mm. " + " | ".join(seen[:6])


# ---- errors an agent can act on --------------------------------------------------------------


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        hint: str = "",
        field: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.hint = status, code, message, hint
        self.field, self.headers = field, headers or {}


def error_body(
    code: str, message: str, hint: str = "", field: str | None = None, docs: str = "/api/v2/docs"
) -> dict[str, Any]:
    return {"error": code, "message": message, "hint": hint, "field": field, "docs": docs}


# ---- the request models (flat JSON; sizes by name) -------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")  # nothing personal, nothing unknown


def _sizes_model(name: str, base: type[BaseModel]) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for n, t in sorted(size_names().items()):
        if t == "boolean":
            fields[n] = (bool | None, Field(default=None, description=size_help(n)))
        else:
            fields[n] = (
                float | None,
                Field(default=None, ge=0, le=100000, description=size_help(n)),
            )
    model: type[BaseModel] = create_model(name, __base__=base, **fields)
    return model


class _FurnitureBase(_Base):
    kind: str = Field(
        max_length=40,
        description="The kind of furniture: sofa, corner_sofa, chair, side_table, footstool, "
        "lounger, daybed, dining_set, round_dining_set, bbq_kamado, bbq_kamado_table, bbq_gas, "
        "bbq_pellet, bbq_fire_table, or an alias (GET /kinds lists them with the sizes each "
        "needs and how to measure).",
        examples=["sofa"],
    )
    unit: Literal["cm", "mm"] = Field(
        default="cm", description="The unit of every size in this request: cm (default) or mm."
    )
    left_right: Literal["left", "right"] | None = Field(
        default=None,
        description="corner_sofa only: which hand the L is, as the maker names it ('corner set "
        "left'). Leave it out when unsure: covers of both hands are then shown.",
    )
    colour: str | None = Field(
        default=None,
        max_length=40,
        description="A fabric colour from GET /kinds (colours). Default: the first one.",
    )
    product_name: str | None = Field(
        default=None,
        max_length=200,
        description="The furniture's product or family name if known (e.g. 'SUNS Kota 2-seater'). "
        "Used as text only, to prefer a cover made for that family among equal fits.",
    )
    product_url: str | None = Field(
        default=None,
        max_length=500,
        description="The furniture's product page. Read as text only (its words help like "
        "product_name); the page is never fetched here. Photo or page recognition: POST /suggest "
        "with a partner key.",
    )
    lang: Literal["nl", "en", "de", "fr"] = Field(
        default="en", description="Language of the links' pages and of the delivery texts."
    )


class _MatchBase(_FurnitureBase):
    top: int = Field(default=3, ge=1, le=10, description="At most this many existing covers.")


class _QuoteBase(_FurnitureBase):
    vents: bool = Field(default=True, description="Air vents (standard; one per metre of hem).")
    support: Literal["none", "balloons"] = Field(
        default="none",
        description="Tables: support balloons under the cover so rain runs off a flat top "
        "(sold next to the cover).",
    )


class _LinkBase(_QuoteBase):
    cover_code: str | None = Field(
        default=None,
        max_length=130,
        description="An existing cover's code from POST /match: the link orders that cover. "
        "Without it the link opens made to measure for the sizes given.",
    )


# the request models: the base's fields plus every size name of every kind (each optional, with
# what it means per kind), so the OpenAPI lists them; the type checker sees the bases
if TYPE_CHECKING:
    MatchIn = _MatchBase
    QuoteIn = _QuoteBase
    LinkIn = _LinkBase
else:
    MatchIn = _sizes_model("MatchIn", _MatchBase)
    QuoteIn = _sizes_model("QuoteIn", _QuoteBase)
    LinkIn = _sizes_model("LinkIn", _LinkBase)


def furniture_fields(
    req: BaseModel, sizes_optional: bool = False
) -> tuple[str, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """(kind, its spec, the configurator's fields, the sizes we assumed) for a request, or an
    ApiError that says exactly what is missing or wrong."""
    from coverengine.quote import PRODUCTS

    found = find_kind(req.kind)  # type: ignore[attr-defined]
    if found is None:
        raise ApiError(
            400,
            "unknown_kind",
            f"unknown kind {req.kind!r}",  # type: ignore[attr-defined]
            "Use one of: " + ", ".join(kinds_doc()["kinds"]) + " (GET /api/v2/kinds).",
            "kind",
        )
    kind, spec = found
    ranges = PRODUCTS[spec["product"]]["fields"]
    given = {n: getattr(req, n) for n in size_names() if getattr(req, n, None) is not None}
    scale = 1 / MM_PER_CM if req.unit == "mm" else 1.0  # type: ignore[attr-defined]
    own = {n for s in spec["sizes"] for n in [s["name"], *s.get("aliases", [])]}
    stray = sorted(set(given) - own)
    if stray:
        raise ApiError(
            400,
            "unknown_size",
            f"{stray[0]} is not a size of kind {kind}",
            f"Kind {kind} takes: " + ", ".join(s["name"] for s in spec["sizes"]) + ".",
            stray[0],
        )
    fields: dict[str, Any] = {}
    assumed: list[dict[str, Any]] = []
    toggles = {
        s["name"]: bool(given.get(s["name"])) for s in spec["sizes"] if s.get("type") == "boolean"
    }
    for s in spec["sizes"]:
        names = [s["name"], *s.get("aliases", [])]
        values = [(n, given[n]) for n in names if n in given]
        if len({v for _, v in values}) > 1:
            raise ApiError(
                400,
                "conflicting_sizes",
                f"{values[0][0]} and {values[1][0]} differ for kind {kind}",
                f"Send one of {', '.join(names)}.",
                s["name"],
            )
        default, lo, hi = ranges[s["field"]]
        if s.get("type") == "boolean":
            if values:
                fields[s["field"]] = bool(values[0][1])
            continue
        if s.get("requires") and not toggles.get(s["requires"]):
            continue  # a size that belongs to an unticked yes/no (a flat lounger's headrest)
        if not values:
            if s["required"] and not sizes_optional:
                when = f" (needed because {s['requires']} is true)" if s.get("requires") else ""
                raise ApiError(
                    400,
                    "missing_size",
                    f"{s['name']} missing for kind {kind}{when}",
                    f'Add "{s["name"]}": {s["means"]} {s["how"]} In cm, between {lo} and {hi}.',
                    s["name"],
                )
            if not s["required"]:
                assumed.append(
                    {
                        "size": s["name"],
                        "value_cm": default,
                        "why": "not given; the configurator's default",
                    }
                )
            continue
        v = round(float(values[0][1]) * scale, 1)
        if not lo <= v <= hi:
            raise ApiError(
                400,
                "out_of_range",
                f"{s['name']} {v} cm is outside {lo}–{hi} cm for kind {kind}",
                "Check the unit (cm unless unit is mm) and how to measure "
                "(GET /api/v2/kinds). Furniture outside this range: ask us; we make "
                "such covers by hand.",
                s["name"],
            )
        fields[s["field"]] = v
    if getattr(req, "left_right", None):
        if spec["product"] == "corner_sofa":
            fields["side"] = req.left_right  # type: ignore[attr-defined]
    return kind, spec, fields, assumed


class NewKey(BaseModel):
    """An admin's new partner key: who it is for, and a B2B company for its own prices."""

    name: str = Field(min_length=1, max_length=60)
    company_id: int | None = None


# ---- who calls -------------------------------------------------------------------------------


@dataclass
class Caller:
    kind: Literal["anonymous", "key", "b2b"]
    visitor: str
    key_id: int | None = None
    key_name: str | None = None
    company: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def who(self) -> str:
        """The usage line this caller counts on (never an address)."""
        if self.key_id is not None:
            return f"key:{self.key_id}"
        if self.company is not None:
            return f"b2b:{self.company['id']}"
        return "anonymous"

    @property
    def partner(self) -> bool:
        return self.kind != "anonymous"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _day(now: float | None = None) -> str:
    return datetime.fromtimestamp(now or time.time(), UTC).strftime("%Y-%m-%d")


class Usage:
    """Counts per day, caller and endpoint in app.db (no addresses, no contents)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.totals: dict[tuple[str, str], int] = {}
        self.photos: dict[tuple[str, str], int] = {}

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def total(self, day: str, who: str) -> int:
        with self.lock:
            if (day, who) not in self.totals:
                with self._db() as db:
                    row = db.execute(
                        "SELECT COALESCE(SUM(count), 0) FROM agent_usage WHERE day=? AND who=?",
                        (day, who),
                    ).fetchone()
                self.totals[(day, who)] = int(row[0])
            return self.totals[(day, who)]

    def count(self, day: str, who: str, endpoint: str) -> None:
        self.total(day, who)
        with self.lock, self._db() as db:
            db.execute(
                "INSERT INTO agent_usage (day, who, endpoint, count) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(day, who, endpoint) DO UPDATE SET count = count + 1",
                (day, who, endpoint),
            )
            self.totals[(day, who)] = self.totals.get((day, who), 0) + 1
            if len(self.totals) > 5000:  # noqa: PLR2004 - forget the days gone by
                self.totals = {k: v for k, v in self.totals.items() if k[0] == day}

    def reserve(self, who: str, endpoint: str, limit: int) -> bool:
        """Take one of today's `limit` slots for this caller and endpoint, atomically (one
        SQLite write transaction): False when none is left. Taken before any paid work starts."""
        day = _day()
        with self.lock, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT count FROM agent_usage WHERE day=? AND who=? AND endpoint=?",
                (day, who, endpoint),
            ).fetchone()
            if (int(row[0]) if row else 0) >= limit:
                return False
            db.execute(
                "INSERT INTO agent_usage (day, who, endpoint, count) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(day, who, endpoint) DO UPDATE SET count = count + 1",
                (day, who, endpoint),
            )
            self.totals[(day, who)] = self.totals.get((day, who), 0) + 1
        return True

    def endpoint_today(self, who: str, endpoint: str) -> int:
        with self._db() as db:
            row = db.execute(
                "SELECT count FROM agent_usage WHERE day=? AND who=? AND endpoint=?",
                (_day(), who, endpoint),
            ).fetchone()
        return int(row[0]) if row else 0

    def summary(self, days: int = 7) -> list[dict[str, Any]]:
        since = _day(time.time() - (days - 1) * 86400)
        with self._db() as db:
            rows = db.execute(
                "SELECT day, who, endpoint, count FROM agent_usage WHERE day>=? "
                "ORDER BY day DESC, who, endpoint",
                (since,),
            ).fetchall()
        return [{"day": d, "who": w, "endpoint": e, "count": c} for d, w, e, c in rows]


class Limiter:
    """The hourly window per caller (in memory) and the daily caps (from the usage counts)."""

    def __init__(self, usage: Usage) -> None:
        self.usage = usage
        self.hits: dict[str, deque[float]] = {}
        self.lock = threading.Lock()

    def hit(self, caller: Caller, p: Any, now: float | None = None) -> dict[str, str]:
        """Count one request; the rate-limit headers, or ApiError 429."""
        now = time.time() if now is None else now
        day = _day(now)
        if caller.partner:
            per_hour, per_day = (
                int(p["limits.agent_key_per_hour"]),
                int(p["limits.agent_key_per_day"]),
            )
            key, daily_who = caller.who, caller.who
        else:
            per_hour, per_day = int(p["limits.agent_per_hour"]), int(p["limits.agent_anon_per_day"])
            key, daily_who = f"anon:{caller.visitor}", "anonymous"
        with self.lock:
            times = self.hits.setdefault(key, deque())
            while times and now - times[0] >= HOUR_S:
                times.popleft()
            reset = int(times[0] + HOUR_S - now) + 1 if times else int(HOUR_S)
            headers = {
                "RateLimit-Limit": str(per_hour),
                "RateLimit-Remaining": str(max(0, per_hour - len(times) - 1)),
                "RateLimit-Reset": str(reset),
                "X-RateLimit-Scope": "partner" if caller.partner else "anonymous",
            }
            if len(times) >= per_hour:
                headers["RateLimit-Remaining"] = "0"
                raise ApiError(
                    429,
                    "rate_limited",
                    f"at most {per_hour} requests an hour"
                    + (" per address without a key" if not caller.partner else ""),
                    f"Wait {reset} s. A free partner key (ask S2DIO) gives higher limits."
                    if not caller.partner
                    else f"Wait {reset} s.",
                    headers={**headers, "Retry-After": str(reset)},
                )
            if self.usage.total(day, daily_who) >= per_day:
                midnight = int(86400 - now % 86400) + 1
                raise ApiError(
                    429,
                    "daily_limit",
                    "the anonymous use of today is used up"
                    if not caller.partner
                    else "this key's requests of today are used up",
                    f"Try again after midnight UTC (in {midnight} s), or use a partner key."
                    if not caller.partner
                    else f"Try again after midnight UTC (in {midnight} s).",
                    headers={**headers, "RateLimit-Remaining": "0", "Retry-After": str(midnight)},
                )
            times.append(now)
            if len(self.hits) > 20000:  # noqa: PLR2004 - forget idle callers
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] >= HOUR_S]:
                    del self.hits[k]
        return headers


# ---- the app ---------------------------------------------------------------------------------


def agent_on(auth: Any, request: Request) -> bool:
    """The agent API answers here: the shop setting `agent_api_enabled` (the live shop, after the
    owner's go), the preview website (preview.<domain> through the Worker's key, as the
    barbecues, ADR-119), or a logged-in colleague trying it on the studio."""
    from coverapi.security import SESSION_COOKIE
    from coverapi.shop import SHOP_DEFAULTS, SHOP_SETTING, link_ok, merged

    s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
    if s.get("agent_api_enabled"):
        return True
    if request.headers.get("x-forwarded-host", "").startswith("preview.") and link_ok(
        auth, request
    ):
        return True
    return auth.session_user(request.cookies.get(SESSION_COOKIE)) is not None


def site_root(auth: Any, request: Request) -> str:
    """The website the links open: the host the Worker answered for (the preview's own links
    stay on the preview), else the shop's domain or this server's /shop/."""
    from coverapi.shop import link_ok, shop_root

    host = request.headers.get("x-forwarded-host", "")
    if host and link_ok(auth, request) and re.fullmatch(r"[a-z0-9.-]+(:\d+)?", host):
        return f"https://{host}/"
    return shop_root(auth, request)


def api_root(auth: Any, request: Request) -> str:
    from coverapi.shop import link_ok

    host = request.headers.get("x-forwarded-host", "")
    if host and link_ok(auth, request) and re.fullmatch(r"[a-z0-9.-]+(:\d+)?", host):
        return f"https://{host}/api/v2"
    scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else request.url.scheme
    return f"{scheme}://{request.headers.get('host', 'localhost')}/api/v2"


def install(app: FastAPI, auth: Any, data: Path, store: Any) -> FastAPI:  # noqa: C901, PLR0915
    """The /api/v2 sub-app (and the same at /api/b2b/v2 for a B2B session), its tables, the
    admin's key routes. Returns the sub-app (the pages module reads its OpenAPI)."""
    from coverengine import costing
    from coverengine import match as mt
    from coverengine import quote as q
    from coverengine.errors import CoverError

    from coverapi import b2b as b2b_mod
    from coverapi import match_list, prices
    from coverapi.security import _address, require
    from coverapi.shop import (
        SHOP_DEFAULTS,
        SHOP_SETTING,
        b2c_cover_price,
        bbq_on,
        link_ok,
        merged,
        shop_params,
        site_languages,
    )

    with sqlite3.connect(auth.path) as db:
        db.executescript(SCHEMA)
    usage = Usage(auth.path)
    limiter = Limiter(usage)
    from coverapi.ratelimit import GlobalCap

    agent_cap = GlobalCap()
    recognising: set[str] = set()  # callers whose photo recognition is running (one each)
    app.state.agent_usage = usage

    sub = FastAPI(
        title="S2DIO covers — agent API",
        version=API_VERSION,
        description=API_DESCRIPTION,
        openapi_url="/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    sub.state.auth = auth

    def settings() -> dict[str, Any]:
        return merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})

    def visitor(request: Request) -> str:
        from coverapi.ratelimit import visitor_key

        a = _address(request)
        if link_ok(auth, request):  # through the website: its visitor's own address
            a = request.headers.get("x-client-ip") or a
        return visitor_key(a)  # an IPv6 visitor as its /64 network (ADR-123)

    def on_b2b_mount(request: Request) -> bool:
        return str(request.scope.get("root_path", "")).endswith("/api/b2b/v2")

    def caller_of(request: Request) -> Caller:
        """The caller: a partner key (X-Api-Key or Authorization: Bearer), a B2B session on
        /api/b2b/v2, or anonymous. A wrong key is refused, never taken as anonymous."""
        key = request.headers.get("x-api-key", "").strip()
        bearer = request.headers.get("authorization", "")
        if not key and bearer.lower().startswith("bearer "):
            key = bearer[7:].strip()
        vis = visitor(request)
        if key:
            with sqlite3.connect(auth.path) as db:
                row = db.execute(
                    "SELECT id, name, company_id FROM agent_keys WHERE hash=? AND revoked IS NULL",
                    (hash_key(key),),
                ).fetchone()
            if row is None:
                raise ApiError(
                    401,
                    "unknown_key",
                    "this API key is unknown or revoked",
                    "Leave the key out to use the API anonymously (public prices, "
                    "lower limits), or ask S2DIO for a new key.",
                )
            company = None
            if row[2] is not None:
                try:
                    company = app.state.b2b.company(int(row[2]))
                except HTTPException:
                    company = None
                if company is None or company["status"] != "active":
                    raise ApiError(
                        403,
                        "company_inactive",
                        "the business account of this key is not active",
                        "Ask S2DIO; until then leave the key out for public prices.",
                    )
            return Caller("b2b" if company else "key", vis, int(row[0]), str(row[1]), company)
        if on_b2b_mount(request):
            got = app.state.b2b.session_user(request.cookies.get(b2b_mod.COOKIE))
            if got is None:
                raise ApiError(
                    401,
                    "login_needed",
                    "please log in to the B2B shop first",
                    "Without a business login use /api/v2 (public prices incl. VAT), "
                    "or a partner key linked to your business account.",
                )
            return Caller("b2b", vis, company=got[1])
        return Caller("anonymous", vis)

    def rel_path(request: Request) -> str:
        path = request.scope.get("path", "")
        root = str(request.scope.get("root_path", ""))
        return path[len(root) :] if root and path.startswith(root) else path

    def cors(resp: Response, request: Request) -> Response:
        if not on_b2b_mount(request):  # the B2B mount is our own pages' only (its cookie)
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Expose-Headers"] = (
                "RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset, Retry-After, "
                "X-RateLimit-Scope"
            )
        return resp

    def err(e: ApiError, request: Request) -> JSONResponse:
        docs = f"{api_root(auth, request)}/docs"
        r = JSONResponse(
            error_body(e.code, e.message, e.hint, e.field, docs),
            e.status,
            headers={**e.headers, "Cache-Control": "no-store"},
        )
        return cors(r, request)  # type: ignore[return-value]

    @sub.middleware("http")
    async def door(request: Request, call_next: Any) -> Response:
        if request.method == "OPTIONS":  # CORS preflight: GET and the POSTs, without cookies
            r = Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, X-Api-Key, Authorization",
                    "Access-Control-Max-Age": "600",
                },
            )
            return cors(r, request)
        if not agent_on(auth, request):
            return err(
                ApiError(404, "not_found", "not here", "This API is not open on this address yet."),
                request,
            )
        rel = rel_path(request)
        counted = rel not in UNCOUNTED and not rel.startswith("/go/")
        headers: dict[str, str] = {}
        if counted:
            try:
                caller = caller_of(request)
                headers = limiter.hit(caller, shop_params(auth))
            except ApiError as e:
                return err(e, request)
            request.state.caller = caller
            endpoint = re.sub(r"/covers/[^/]+", "/covers/{code}", rel)
            usage.count(_day(), caller.who, f"{request.method} {endpoint}"[:60])
        resp: Response = await call_next(request)
        for k, v in headers.items():
            resp.headers[k] = v
        resp.headers.setdefault("Cache-Control", "no-store")
        resp.headers["Vary"] = "X-Api-Key, Authorization, Cookie"
        return cors(resp, request)

    @sub.exception_handler(ApiError)
    async def api_error(request: Request, e: ApiError) -> JSONResponse:
        return err(e, request)

    @sub.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, e: StarletteHTTPException) -> JSONResponse:
        code = {
            400: "bad_request",
            401: "unauthorised",
            403: "forbidden",
            404: "not_found",
            413: "too_large",
            429: "rate_limited",
            502: "upstream",
            503: "resting",
        }.get(e.status_code, "error")
        return err(ApiError(e.status_code, code, str(e.detail)), request)

    @sub.exception_handler(RequestValidationError)
    async def invalid(request: Request, e: RequestValidationError) -> JSONResponse:
        first = e.errors()[0] if e.errors() else {}
        loc = [str(x) for x in first.get("loc", []) if x not in ("body", "query")]
        name = loc[-1] if loc else None
        if first.get("type") == "extra_forbidden":
            hint = (
                "This API takes no personal data or unknown fields: the customer gives "
                "name and address on our site. Allowed fields: see /api/v2/openapi.json."
            )
            return err(
                ApiError(400, "unknown_field", f"{name} is not accepted", hint, name), request
            )
        if first.get("type") == "missing":
            return err(
                ApiError(
                    400,
                    "missing_field",
                    f"{name} missing",
                    "GET /api/v2/kinds lists what each kind needs.",
                    name,
                ),
                request,
            )
        return err(
            ApiError(
                400,
                "invalid_field",
                f"{name}: {first.get('msg', 'invalid')}",
                "Sizes are plain numbers (cm unless unit is mm); yes/no fields true or false.",
                name,
            ),
            request,
        )

    # ---- shared pieces ---------------------------------------------------------------------
    def caller(request: Request) -> Caller:
        c: Caller = request.state.caller
        return c

    def products_on(request: Request) -> set[str]:
        return set(q.options(shop_params(auth), bbq_on(auth, request))["products"])

    def check_product(spec: dict[str, Any], kind: str, request: Request) -> None:
        if spec["product"] not in products_on(request):
            raise ApiError(
                400,
                "unknown_kind",
                f"kind {kind} is not offered yet",
                "GET /api/v2/kinds lists the kinds offered now.",
                "kind",
            )

    def check_colour(colour: str | None) -> str | None:
        if colour is None:
            return None
        cs = q.colours(shop_params(auth))
        hit = next((c for c in cs if c.lower() == colour.strip().lower()), None)
        if hit is None:
            raise ApiError(
                400,
                "unknown_colour",
                f"unknown colour {colour!r}",
                "Use one of: " + ", ".join(cs) + ".",
                "colour",
            )
        return hit

    def lang_root(request: Request, lang: str) -> str:
        langs = site_languages(auth)
        root = site_root(auth, request)
        return root if not langs or lang == langs[0] or lang not in langs else f"{root}{lang}/"

    def text_in(t: dict[str, Any] | None, lang: str) -> str | None:
        t = t or {}
        out = str(t.get(lang) or t.get("en") or "").strip()
        return out or None

    def order_url(
        request: Request,
        c: Caller,
        product: str,
        fields: dict[str, Any],
        lang: str,
        stock: str | None = None,
        colour: str | None = None,
        vents: bool = True,
        support: str = "none",
        checkout: bool = False,
    ) -> str:
        """The configurator (or the B2B shop) prefilled with these choices. Opening it creates
        nothing; a person orders and pays there."""
        sizes = {k: v for k, v in fields.items() if k != "side"}
        qs: dict[str, str] = {"product": product, "sizes": json.dumps(sizes, separators=(",", ":"))}
        if stock:
            qs["stock"] = stock
        if colour:
            qs["colour"] = colour
        if not vents:
            qs["vents"] = "0"
        if support != "none":
            qs["support"] = support
        if checkout:
            qs["checkout"] = "1"
        qs["from"] = "agent"
        if c.company is not None:
            return f"{site_root(auth, request)}b2b/?{urlencode(qs)}#configure"
        return f"{lang_root(request, lang)}configure?{urlencode(qs)}"

    def price_of(c: Caller, full: dict[str, Any], stock: str | None) -> dict[str, Any]:
        """The caller's own price: B2C incl. VAT, or the caller's company's price ex VAT. Never
        a cost, a margin or another company's price."""
        ps = prices.current(auth)
        if c.company is not None:
            u = b2b_mod.unit_price(
                ps, c.company, full["price"]["costing"]["channels"], stock, "none", 1
            )
            return {
                "amount_eur": u["cover_eur"],
                "currency": "EUR",
                "vat_included": False,
                "vat_pct": b2b_mod.vat_pct(ps, c.company),
                "price_list": "your business prices",
                "source": {
                    "list": "price_list",
                    "list_fixed": "fixed",
                    "company_fixed": "your_fixed_price",
                }.get(u["source"], "price_list"),
                "indicative": bool(full["price"]["placeholder_prices"]),
            }
        off = float(settings()["matching"].get("stock_discount_pct") or 0)
        sale, source, disc = b2c_cover_price(ps, full["price"]["sale_eur"], stock, off)
        out = {
            "amount_eur": sale,
            "currency": "EUR",
            "vat_included": True,
            "vat_pct": float(ps["channels"]["b2c"]["vat_pct"]),
            "price_list": "public",
            "source": {"fixed": "fixed", "stock": "from_its_sizes", "custom": "made_to_measure"}[
                source
            ],
            "indicative": bool(full["price"]["placeholder_prices"]) and source != "fixed",
        }
        if disc:
            out["discount_pct"] = disc
        return out

    def support_price(c: Caller, full: dict[str, Any], support: str) -> dict[str, Any] | None:
        if support != "balloons":
            return None
        ps = prices.current(auth)
        if c.company is not None:
            u = b2b_mod.unit_price(
                ps,
                c.company,
                full["price"]["costing"]["channels"],
                None,
                "balloons",
                int(full["balloons"] or 1),
            )
            return {
                "amount_eur": u["support_eur"],
                "currency": "EUR",
                "vat_included": False,
                "count": int(full["balloons"] or 1),
            }
        each = costing.accessory_price(ps, "balloon", "b2c")["gross_eur"]
        return {
            "amount_eur": round(full["balloons"] * each, 2),
            "currency": "EUR",
            "vat_included": True,
            "count": int(full["balloons"] or 0),
        }

    def proposal(
        product: str, fields: dict[str, Any], colour: str | None, vents: bool = True
    ) -> dict[str, Any]:
        # all agents together at most limits.quotes_per_minute proposals a minute (ADR-123), on a
        # cap of their own: agents never use up the shop's (they write no files)
        if not agent_cap.hit():
            raise ApiError(
                429,
                "busy",
                "many prices are asked just now",
                "Try again in a minute.",
                headers={"Retry-After": "60"},
            )
        try:
            return q.proposal(
                product,
                {**fields, "vents": vents, "colour": colour},
                shop_params(auth),
                prices.current(auth),
            )
        except CoverError as exc:
            raise ApiError(
                400, "not_buildable", str(exc), "Check the sizes against GET /api/v2/kinds."
            ) from None

    def sizes_out(fields: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
        """The configurator's fields back in the API's names, cm and mm."""
        out: dict[str, Any] = {}
        for s in spec["sizes"]:
            if s["field"] not in fields:
                continue
            v = fields[s["field"]]
            if s.get("type") == "boolean":
                out[s["name"]] = bool(v)
            else:
                out[f"{s['name']}_cm"] = v
                out[f"{s['name']}_mm"] = round(float(v) * MM_PER_CM)
        return out

    def lead_time(lang: str) -> str | None:
        return text_in(settings().get("custom_lead_time"), lang)

    def delivery(lang: str) -> str | None:
        return text_in(settings().get("stock_delivery_note"), lang)

    def preview_url(request: Request, product: str, fields: dict[str, Any]) -> str:
        sizes = {k: v for k, v in fields.items() if k != "side"}
        return f"{api_root(auth, request)}/preview.glb?" + urlencode(
            {"product": product, "sizes": json.dumps(sizes, separators=(",", ":"))}
        )

    def cover_card(code: str, request: Request) -> dict[str, Any]:
        if not CODE.match(code):
            raise ApiError(
                404,
                "unknown_cover",
                f"no cover {code!r}",
                "Cover codes come from POST /api/v2/match or GET /api/v2/covers.",
                "code",
            )
        card = mt.card(store.models / code, None, match_list.for_data(data), shop_params(auth))
        if card is None or card["kind"] not in products_on(request):
            raise ApiError(
                404,
                "unknown_cover",
                f"no cover {code!r} in our range now",
                "Cover codes come from POST /api/v2/match or GET /api/v2/covers.",
                "code",
            )
        return card

    def fits_of(card: dict[str, Any]) -> dict[str, Any]:
        length, width, height = card["size_cm"]
        return {
            "length_cm": length,
            "width_cm": width,
            "height_cm": height,
            "length_mm": round(length * MM_PER_CM),
            "width_mm": round(width * MM_PER_CM),
            "height_mm": round(height * MM_PER_CM),
            "height_is_maximum": bool(card.get("height_max")),
            "about": "The furniture this cover fits (not the cover itself): length is the "
            "longer side seen from above, width the shorter, height from the ground.",
        }

    def cover_facts(
        card: dict[str, Any],
        request: Request,
        c: Caller,
        lang: str,
        colour: str | None = None,
        with_price: bool = True,
    ) -> dict[str, Any]:
        product = card["kind"]
        fields = mt.fields_for(product, card["size_cm"])
        api = api_root(auth, request)
        out: dict[str, Any] = {
            "code": card["model_id"],
            "name": card["name"],
            "product": product,
            "kinds": kinds_of_product(product),
            "source": card.get("source") or "suns",
            "fits": fits_of(card),
            "left_right": card.get("side"),
            "families": card.get("families") or [],
            "delivery": delivery(lang),
            "picture_url": f"{api}/covers/{card['model_id']}/picture.jpg"
            if card.get("photo")
            else None,
            "preview_3d_url": f"{api}/covers/{card['model_id']}/preview.glb",
            "page_url": f"{site_root(auth, request)}covers/{card['model_id']}",
            "order_url": order_url(request, c, product, fields, lang, card["model_id"], colour),
        }
        if with_price:
            out["price"] = price_of(c, proposal(product, fields, colour), card["model_id"])
        return out

    def why_of(m: dict[str, Any]) -> str:
        words = {"length": "length", "width": "width", "height": "height"}
        parts = []
        exact = [words[d["size"]] for d in m["sizes"] if d["verdict"] == "exact"]
        if exact:
            parts.append("within the cover's own room on " + ", ".join(exact))
        for d in m["sizes"]:
            if d["verdict"] != "exact":
                parts.append(
                    f"{words[d['size']]} {abs(d['difference_cm']):g} cm "
                    f"{'roomier' if d['verdict'] == 'roomier' else 'tighter'}"
                )
        return "; ".join(parts) + f" (fit {m['score_pct']:g} %)"

    # ---- the routes ------------------------------------------------------------------------
    @sub.get("/", include_in_schema=False)
    def index(request: Request) -> dict[str, Any]:
        api = api_root(auth, request)
        return {
            "name": "S2DIO covers agent API",
            "version": API_VERSION,
            "openapi": f"{api}/openapi.json",
            "docs": f"{api}/docs",
            "kinds": f"{api}/kinds",
            "llms": f"{site_root(auth, request)}llms.txt",
        }

    @sub.get("/kinds", summary="The kinds of furniture, the sizes each needs, how to measure")
    def kinds(request: Request) -> dict[str, Any]:
        """Every kind we make covers for, with its sizes (required or not, the range in cm, what
        it means, how to measure it) and a link to the measuring guide. Read this first."""
        from coverengine.quote import PRODUCTS

        doc = kinds_doc()
        on = products_on(request)
        site = site_root(auth, request)
        out = []
        for k, v in doc["kinds"].items():
            if v["product"] not in on:
                continue
            ranges = PRODUCTS[v["product"]]["fields"]
            sizes = []
            for s in v["sizes"]:
                d, lo, hi = ranges[s["field"]]
                boolean = s.get("type") == "boolean"
                sizes.append(
                    {
                        "name": s["name"],
                        "aliases": s.get("aliases", []),
                        "type": "boolean" if boolean else "number",
                        "unit": None if boolean else "cm",
                        "required": bool(s["required"]),
                        "required_when": s.get("requires"),
                        "min_cm": lo,
                        "max_cm": hi,
                        "default": d if (boolean or not s["required"]) else None,
                        "means": s["means"],
                        "how_to_measure": s["how"],
                    }
                )
            out.append(
                {
                    "kind": k,
                    "label": v["label"],
                    "product": v["product"],
                    "aliases": v.get("aliases", []),
                    "barbecue": bool(v.get("barbecue")),
                    "how": v.get("how", ""),
                    "left_right": v.get("left_right"),
                    "sizes": sizes,
                    "guide_url": f"{site}measure/{k}",
                }
            )
        return {
            "how_to_measure": doc["general"],
            "guide_url": f"{site}measure",
            "colours": q.colours(shop_params(auth)),
            "kinds": out,
            "rules": RULES,
        }

    @sub.post("/match", summary="The best covers for this furniture: existing and made to measure")
    def match(req: MatchIn, request: Request) -> dict[str, Any]:
        """Give the kind and the sizes; get a ranked list: the existing covers that fit (fit %,
        why, the size differences, price, delivery, picture, 3D, order link) and the
        made-to-measure cover (price, lead time, order link). An unsure fit says so."""
        c = caller(request)
        kind, spec, fields, assumed = furniture_fields(req)
        check_product(spec, kind, request)
        colour = check_colour(req.colour)
        p = shop_params(auth)
        hint = " ".join(
            x for x in (req.product_name, re.sub(r"[/:._?=&-]+", " ", req.product_url or "")) if x
        )
        try:
            r = mt.match(
                spec["product"],
                fields,
                store.models,
                p,
                top=8,  # param-ok: candidates
                listing=match_list.for_data(data),
                hint=hint or None,
            )
        except (ValueError, CoverError) as exc:
            raise ApiError(400, "not_matchable", str(exc), "Check the sizes.") from None
        top = min(int(req.top), int(p["limits.agent_results_max"]))
        good, choice = float(r["threshold_pct"]), float(r["choice_pct"])
        existing: list[dict[str, Any]] = []
        for m in r["matches"]:
            if float(m["score_pct"]) < choice or len(existing) >= top:
                continue
            card = mt.card(store.models / m["model_id"], None, match_list.for_data(data), p)
            if card is None:
                continue
            facts = cover_facts(card, request, c, req.lang, colour)
            existing.append(
                {
                    "type": "existing",
                    "code": m["model_id"],
                    "name": m["name"],
                    "fit_pct": m["score_pct"],
                    "confidence": "good" if float(m["score_pct"]) >= good else "possible",
                    "why": why_of(m),
                    "size_differences": [
                        {
                            "size": d["size"],
                            "yours_cm": d["customer_cm"],
                            "cover_fits_cm": d["cover_cm"],
                            "difference_cm": d["difference_cm"],
                            "difference_mm": round(d["difference_cm"] * MM_PER_CM),
                            "verdict": d["verdict"],
                        }
                        for d in m["sizes"]
                    ],
                    **{
                        k: facts[k]
                        for k in (
                            "price",
                            "delivery",
                            "picture_url",
                            "preview_3d_url",
                            "page_url",
                            "order_url",
                            "fits",
                            "left_right",
                        )
                    },
                }
            )
        full = proposal(spec["product"], fields, colour)
        custom = {
            "type": "made_to_measure",
            "name": f"Made to measure: {spec['label']}",
            "fit_pct": 100.0,
            "confidence": "good",
            "why": "cut and sewn to your sizes",
            "price": price_of(c, full, None),
            "lead_time": lead_time(req.lang),
            "cover_sizes_cm": full["sizes_cm"],
            "vents": full["vents"],
            "preview_3d_url": preview_url(request, spec["product"], fields),
            "order_url": order_url(request, c, spec["product"], fields, req.lang, colour=colour),
        }
        sure = [e for e in existing if e["confidence"] == "good"]
        unsure = [e for e in existing if e["confidence"] != "good"]
        results = [*sure, custom, *unsure]
        for i, x in enumerate(results, 1):
            x["rank"] = i
        notes = []
        if not existing:
            notes.append("No existing cover fits well enough: made to measure is the answer.")
        if unsure:
            notes.append(
                "A 'possible' fit is not sure: check its size differences, or choose "
                "made to measure."
            )
        if spec["product"] == "corner_sofa" and not req.left_right:
            notes.append(
                "left_right not given: covers of both hands may be listed; check which "
                "hand the customer's corner sofa is."
            )
        if str(p["match.mode"]) == "shadow" and existing:
            notes.append(
                "Our team still confirms existing-cover matches by hand for now; the "
                "configurator shows the same fit."
            )
        if spec["product"] in ("dining_set", "round_set"):
            notes.append(
                "A flat table top holds rain; the configurator shows where the water "
                "goes and may advise support balloons (sold next to the cover)."
            )
        if custom["lead_time"] is None:
            notes.append("Made to measure: the lead time is confirmed after the order.")
        notes.append(
            "Opening an order_url orders nothing: a person checks the choice, gives "
            "the delivery address and pays on the site."
        )
        return {
            "kind": kind,
            "product": spec["product"],
            "your_sizes": sizes_out(fields, spec),
            "left_right": req.left_right,
            "assumed": assumed,
            "decision": r["decision"],
            "thresholds": {"good_pct": good, "possible_pct": choice},
            "price_basis": basis(c),
            "results": results,
            "notes": notes,
        }

    def basis(c: Caller) -> dict[str, Any]:
        if c.company is not None:
            return {
                "channel": "b2b",
                "vat_included": False,
                "currency": "EUR",
                "company": c.company["name"],
            }
        return {
            "channel": "b2c",
            "vat_included": True,
            "currency": "EUR",
            "shipping": "added at checkout per country",
        }

    @sub.post("/quote", summary="The made-to-measure price for these sizes and options")
    def quote(req: QuoteIn, request: Request) -> dict[str, Any]:
        """The price of a cover cut and sewn to these sizes (incl. VAT for the public; a business
        key or login: the company's own price ex VAT), the cover's own sizes and a link."""
        c = caller(request)
        kind, spec, fields, assumed = furniture_fields(req)
        check_product(spec, kind, request)
        colour = check_colour(req.colour)
        if req.support != "none" and spec["product"] not in ("dining_set", "round_set"):
            raise ApiError(
                400,
                "invalid_field",
                "support balloons are for tables only",
                "Leave support out for this kind.",
                "support",
            )
        full = proposal(spec["product"], fields, colour, req.vents)
        sp = support_price(c, full, req.support)
        price = price_of(c, full, None)
        total = round(price["amount_eur"] + (sp["amount_eur"] if sp else 0), 2)
        return {
            "kind": kind,
            "product": spec["product"],
            "your_sizes": sizes_out(fields, spec),
            "assumed": assumed,
            "colour": full["colour"],
            "vents": full["vents"],
            "price": price,
            "support": req.support,
            "support_price": sp,
            "total_eur": total,
            "price_basis": basis(c),
            "cover_sizes_cm": full["sizes_cm"],
            "pieces": len(full["pieces"]),
            "lead_time": lead_time(req.lang),
            "preview_3d_url": preview_url(request, spec["product"], fields),
            "order_url": order_url(
                request,
                c,
                spec["product"],
                fields,
                req.lang,
                colour=colour,
                vents=req.vents,
                support=req.support,
            ),
            "notes": [
                "A proposal from rough sizes; the definitive pattern is made after the order.",
                "Opening order_url orders nothing: a person orders and pays on the site.",
            ],
        }

    @sub.post("/order-link", summary="A short-lived link that opens the checkout prefilled")
    def order_link(req: LinkIn, request: Request) -> dict[str, Any]:
        """A link for the person to open: our configurator with these choices, straight to the
        checkout. It creates no order and no payment; the person checks, gives the delivery
        address and pays on the site (Mollie). An agent never pays. The link expires."""
        c = caller(request)
        p = shop_params(auth)
        stock = None
        if req.cover_code:
            card = cover_card(req.cover_code, request)
            stock = card["model_id"]
            kind, spec, fields, assumed = furniture_fields(req, sizes_optional=True)
            if spec["product"] != card["kind"]:
                raise ApiError(
                    400,
                    "kind_mismatch",
                    f"cover {stock} is for {', '.join(kinds_of_product(card['kind']))}, not {kind}",
                    "Send the kind the cover is for.",
                    "kind",
                )
            fields = {**fields, **mt.fields_for(card["kind"], card["size_cm"])}
        else:
            kind, spec, fields, assumed = furniture_fields(req)
        check_product(spec, kind, request)
        colour = check_colour(req.colour)
        full = proposal(spec["product"], fields, colour, req.vents if not stock else True)
        target = order_url(
            request,
            c,
            spec["product"],
            fields,
            req.lang,
            stock,
            colour,
            req.vents if not stock else True,
            req.support,
            checkout=True,
        )
        hours = float(p["limits.agent_link_hours"])
        token, now = secrets.token_urlsafe(24), time.time()
        with sqlite3.connect(auth.path) as db:
            db.execute("DELETE FROM agent_links WHERE expires < ?", (now - 7 * 86400,))
            db.execute(
                "INSERT INTO agent_links (token, created, expires, who, channel, target) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (token, now, now + hours * HOUR_S, c.who, "b2b" if c.company else "b2c", target),
            )
        expires = datetime.fromtimestamp(now + hours * HOUR_S, UTC).isoformat(timespec="seconds")
        nxt = (
            [
                "The person opens the link and logs in to the B2B shop.",
                "They check the cover and add it to the order list; the order is placed on "
                "account by a person with the company's login.",
            ]
            if c.company
            else [
                "The person opens the link: the configurator shows this cover and its price.",
                "At the checkout they give their name and delivery address and accept the terms.",
                "They pay on the site (Mollie). Nothing is ordered before that.",
            ]
        )
        return {
            "order_url": f"{api_root(auth, request)}/go/{token}",
            "expires_at": expires,
            "expires_in_s": int(hours * HOUR_S),
            "channel": "b2b" if c.company else "b2c",
            "kind": kind,
            "cover_code": stock,
            "your_sizes": sizes_out(fields, spec),
            "assumed": assumed,
            "colour": full["colour"],
            "price": price_of(c, full, stock),
            "opens": target,
            "what_happens_next": nxt,
            "agent_may_pay": False,
            "price_basis": basis(c),
        }

    @sub.get("/go/{token}", include_in_schema=False)
    def go(token: str, request: Request) -> Response:
        """The order link a person opens: to the configurator, or a page saying it expired."""
        row = None
        if TOKEN.match(token):
            with sqlite3.connect(auth.path) as db:
                row = db.execute(
                    "SELECT expires, target FROM agent_links WHERE token=?", (token,)
                ).fetchone()
        if row is not None and float(row[0]) > time.time():
            return RedirectResponse(
                str(row[1]),
                status_code=302,
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )
        start = f"{site_root(auth, request)}configure"
        html = (
            f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="robots" '
            f'content="noindex"><title>Link expired</title><body style="font:16px/1.5 '
            f'system-ui;margin:3rem auto;max-width:36rem;padding:0 1rem"><h1>This link has '
            f"expired</h1><p>Order links are valid for a short time. Start again in our "
            f'<a href="{start}">configurator</a>: your sizes take a minute.</p></body></html>'
        )
        return HTMLResponse(html, status_code=410, headers={"Cache-Control": "no-store"})

    @sub.get("/covers", summary="Every existing cover of our range (sizes, no prices)")
    def covers(request: Request) -> dict[str, Any]:
        """Our existing covers: code, name, the kinds it is for and the furniture sizes it fits.
        Prices per cover: GET /covers/{code}."""
        p = shop_params(auth)
        on = products_on(request)
        site, api = site_root(auth, request), api_root(auth, request)
        items = [
            {
                "code": cd["model_id"],
                "name": cd["name"],
                "product": cd["kind"],
                "kinds": kinds_of_product(cd["kind"]),
                "fits": fits_of(cd),
                "left_right": cd.get("side"),
                "url": f"{api}/covers/{cd['model_id']}",
                "page_url": f"{site}covers/{cd['model_id']}",
            }
            for cd in mt.cards(store.models, None, match_list.for_data(data), p)
            if cd["kind"] in on
        ]
        return {"count": len(items), "covers": items}

    @sub.get("/covers/{code}", summary="One existing cover's public facts and price")
    def cover(
        code: str, request: Request, lang: Literal["nl", "en", "de", "fr"] = "en"
    ) -> dict[str, Any]:
        """One cover: the furniture sizes it fits, the price (yours), delivery, picture, 3D and
        an order link."""
        c = caller(request)
        out = cover_facts(cover_card(code, request), request, c, lang)
        out["price_basis"] = basis(c)
        return out

    @lru_cache(maxsize=64)
    def glb(product: str, sizes_json: str) -> bytes:
        return q.preview_glb(product, json.loads(sizes_json), shop_params(auth))

    @sub.get("/covers/{code}/preview.glb", summary="A cover's 3D preview (glTF binary)")
    def cover_glb(code: str, request: Request) -> Response:
        card = cover_card(code, request)
        sizes = mt.fields_for(card["kind"], card["size_cm"])
        body = glb(card["kind"], json.dumps(sizes, sort_keys=True))
        return Response(
            body, media_type="model/gltf-binary", headers={"Cache-Control": "public, max-age=3600"}
        )

    @sub.get("/covers/{code}/picture.jpg", summary="A cover's product photo, when it has one")
    def cover_picture(code: str, request: Request) -> Response:
        card = cover_card(code, request)
        path = store.models / card["model_id"] / "product.jpg"
        if not card.get("photo") or not path.is_file():
            raise ApiError(404, "no_picture", "this cover has no picture", "")
        return Response(
            path.read_bytes(),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @sub.get("/preview.glb", summary="A made-to-measure cover's 3D preview (glTF binary)")
    def preview(request: Request, product: str, sizes: str = "{}") -> Response:
        """The links in /match and /quote answers point here (product and the configurator's
        sizes as JSON)."""
        if product not in products_on(request) or len(sizes) > 2000:  # noqa: PLR2004
            raise ApiError(
                404, "unknown_kind", "no such product", "Use the preview_3d_url from an answer."
            )
        try:
            given = json.loads(sizes)
            if not isinstance(given, dict):
                raise ValueError
            body = glb(product, json.dumps(given, sort_keys=True))
        except (ValueError, CoverError):
            raise ApiError(
                400,
                "invalid_field",
                "sizes are not valid for this product",
                "Use the preview_3d_url from an answer.",
                "sizes",
            ) from None
        return Response(
            body, media_type="model/gltf-binary", headers={"Cache-Control": "public, max-age=3600"}
        )

    @sub.post("/suggest", summary="Sizes from a photo or a product page (partner key only)")
    async def suggest(
        request: Request,
        url: str = Form(
            "",
            max_length=2000,  # noqa: B008
            description="A product page of the furniture (fetched safely here).",
        ),
        lang: str = Form("en", pattern=r"^[a-z]{2}$"),  # noqa: B008
        photos: list[UploadFile] = File(  # noqa: B008
            default_factory=list,  # noqa: B008
            description="Up to 3 photos of the furniture.",
        ),
    ) -> dict[str, Any]:
        """Recognise the furniture from up to 3 photos and/or its product page and suggest the
        kind and sizes, with the sizes the person must still measure. This costs us an AI
        call: a partner key only, within the key's daily limits. Never anonymous."""
        from coverengine import spend

        from coverapi import shop_suggest

        c = caller(request)
        if c.key_id is None:  # a partner key only: not anonymous, not a B2B login
            raise ApiError(
                401,
                "key_needed",
                "photo and page recognition needs a partner key",
                "Without a key, measure the furniture (GET /api/v2/kinds says how) "
                "and use POST /api/v2/match.",
            )
        p = shop_params(auth)
        if not photos and not url.strip():
            raise ApiError(400, "missing_field", "give photos or a url", "", "photos")
        if len(photos) > shop_suggest.MAX_PHOTOS:
            raise ApiError(
                400, "invalid_field", f"at most {shop_suggest.MAX_PHOTOS} photos", "", "photos"
            )
        # one recognition at a time per caller (the euro check below then sees every earlier
        # call's cost in the ledger), and today's slot taken atomically before any await, so
        # parallel requests cannot pass the same check (Codex's review)
        if c.who in recognising:
            raise ApiError(
                429,
                "busy",
                "this key's previous recognition is still running",
                "Wait for its answer, then ask again.",
                headers={"Retry-After": "30"},
            )
        tomorrow = {"Retry-After": str(int(86400 - time.time() % 86400) + 1)}
        who = f"agent:{c.who}"
        if spend.visitor_eur(who) >= float(p["limits.agent_key_eur_day"]):
            raise ApiError(
                429,
                "daily_limit",
                "this key's AI budget of today is used up",
                "Try again tomorrow, or give the sizes yourself (POST /match).",
                headers=tomorrow,
            )
        if not usage.reserve(c.who, "AI suggest", int(p["limits.agent_key_photos_per_day"])):
            raise ApiError(
                429,
                "daily_limit",
                "this key's recognitions of today are used up",
                "Try again tomorrow, or give the sizes yourself (POST /match).",
                headers=tomorrow,
            )
        recognising.add(c.who)
        try:
            try:
                pngs = await shop_suggest.read_photos(p, photos)
            except shop_suggest.SuggestError as exc:
                raise ApiError(400, "invalid_field", str(exc), "", "photos") from None
            out = await shop_suggest.run_suggestion(p, pngs, url, lang, who, store.models, data)
        finally:
            recognising.discard(c.who)
        product = out["product"]
        kinds = kinds_of_product(product)
        spec = kinds_doc()["kinds"][kinds[0]]
        back = {s["field"]: s["name"] for s in spec["sizes"]}
        rec = out.get("recognised") or {}
        comp = out.get("comparable") or {}
        best = out.get("match")
        return {
            "kind": kinds[0],
            "other_kinds": kinds[1:],
            "product": product,
            "sizes": {back[f]: v for f, v in out["sizes"].items() if f in back},
            "measure_these": [back[f] for f in out["check"] if f in back],
            "summary": out.get("summary"),
            "recognised": {"name": rec.get("name"), "url": rec.get("url")} if rec else None,
            "comparable": {"name": comp.get("name"), "url": comp.get("url")} if comp else None,
            "match": {"code": best["model_id"], "name": best["name"], "fit_pct": best["score_pct"]}
            if best
            else None,
            "next": "Let the person measure the sizes in measure_these, then POST /api/v2/match.",
        }

    # ---- the admin: partner keys and the counts (Settings → Website & API keys) --------------
    def key_rows() -> list[dict[str, Any]]:
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT id, name, shown, created, created_by, company_id, revoked "
                    "FROM agent_keys ORDER BY revoked IS NOT NULL, id DESC"
                )
            ]
        names = {c["id"]: c["name"] for c in app.state.b2b.companies()}
        for r in rows:
            r["company"] = names.get(r["company_id"]) if r["company_id"] else None
        return rows

    @app.get("/api/admin/agent-api")
    def agent_admin(request: Request) -> dict[str, Any]:
        require(request, "admin")
        p = shop_params(auth)
        lim = {
            k.split(".", 1)[1]: p[k]
            for k in (
                "limits.agent_per_hour",
                "limits.agent_anon_per_day",
                "limits.agent_key_per_hour",
                "limits.agent_key_per_day",
                "limits.agent_key_photos_per_day",
                "limits.agent_key_eur_day",
                "limits.agent_link_hours",
            )
        }
        return {
            "enabled_on_live": bool(settings().get("agent_api_enabled")),
            "limits": lim,
            "keys": key_rows(),
            "usage": usage.summary(),
            "companies": [
                {"id": c["id"], "name": c["name"], "status": c["status"]}
                for c in app.state.b2b.companies()
            ],
        }

    @app.post("/api/admin/agent-api/keys")
    def agent_new_key(req: NewKey, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        if req.company_id is not None:
            app.state.b2b.company(req.company_id)  # 404 when there is no such company
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        with sqlite3.connect(auth.path) as db:
            cur = db.execute(
                "INSERT INTO agent_keys (name, hash, shown, created, created_by, "
                "company_id) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    req.name.strip(),
                    hash_key(key),
                    key[:8] + "…",
                    time.time(),
                    admin.username,
                    req.company_id,
                ),
            )
        auth.log(admin, "agent API key made", {"name": req.name, "company": req.company_id})
        return {
            "id": cur.lastrowid,
            "name": req.name,
            "key": key,
            "note": "shown once: give it to the partner now",
        }

    @app.post("/api/admin/agent-api/keys/{kid}/revoke")
    def agent_revoke(kid: int, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        with sqlite3.connect(auth.path) as db:
            db.execute(
                "UPDATE agent_keys SET revoked=? WHERE id=? AND revoked IS NULL", (time.time(), kid)
            )
        auth.log(admin, "agent API key revoked", {"id": kid})
        return agent_admin(request)

    # for the website's pages (agent_pages): the kinds and a cover's public facts, as the public
    # (anonymous) sees them
    sub.state.kinds = kinds

    def cover_public(code: str, request: Request, lang: str = "en") -> dict[str, Any]:
        """A cover page's facts with the public price, counted like an anonymous API call
        (the page computes a price: its visitor's hourly and the anonymous daily limits)."""
        anon = Caller("anonymous", visitor(request))
        limiter.hit(anon, shop_params(auth))
        usage.count(_day(), anon.who, "GET page /covers/{code}")
        return cover_facts(cover_card(code, request), request, anon, lang)

    sub.state.cover_public = cover_public
    sub.state.covers = covers
    sub.state.site_root = lambda request: site_root(auth, request)
    sub.state.api_root = lambda request: api_root(auth, request)
    sub.state.feeds_root = lambda request: api_root(auth, request).removesuffix("api/v2")
    app.mount("/api/v2", sub)
    app.mount("/api/b2b/v2", sub)  # a B2B session's own prices (its cookie's path is /api/b2b/)
    app.state.agent_api = sub
    return sub


RULES = [
    "Open to everyone without a key, within limits (per address an hour, all anonymous use "
    "together a day). A free partner key gives higher limits and photo recognition.",
    "Prices are the public prices incl. VAT; a business key or login gets that business's own "
    "prices ex VAT.",
    "An agent never orders or pays: order links open our site, where a person checks the "
    "choice, gives the delivery address and pays.",
    "No personal data is accepted or returned.",
    "Never guess sizes: measure the furniture as GET /kinds says, or ask the person.",
]

API_DESCRIPTION = """
The API of S2DIO / SUNS: premium covers for outdoor furniture and barbecues, made to measure,
and the existing covers of our range. Written for AI agents and their users.

**Flow.** 1. `GET /kinds`: the kinds of furniture and the sizes each needs (in cm) with how to
measure them. 2. `POST /match` with the kind and sizes: a ranked list of existing covers that
fit (fit %, why, size differences, price, delivery promise, picture, 3D preview, order link)
and the made-to-measure cover (price, lead time, order link). 3. Give the person an
`order_url`, or `POST /order-link` for a short-lived link straight to the checkout.

**Rules.** Open without a key, within limits (headers `RateLimit-Limit`, `RateLimit-Remaining`,
`RateLimit-Reset`; on 429 `Retry-After`). Public prices incl. VAT; a business key: that business's
prices ex VAT. An agent never orders or pays: a person completes the order and the payment on
our site. No personal data is accepted or returned. Photo recognition (`POST /suggest`) needs a
partner key.

**Errors** are JSON: `{"error": code, "message": ..., "hint": what to do, "field": ...}`.

**Units.** Sizes in centimetres unless `unit` is `mm`; answers give cm and mm.
"""
