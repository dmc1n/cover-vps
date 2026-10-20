"""The dealer embed (ADR-150, docs/plans/dealer-embed.md): our configurator on a B2B dealer's own
website, in the dealer's look, at the dealer's prices.

- **A dealer site** (`dealer_sites`) belongs to a B2B company (ADR-104): its public key
  (`dpk_…`, in the snippet; names the site, opens nothing secret), its secret key (`dsk_…`,
  SHA-256 only; the dealer's server reads a quote back with it), its allow-listed origins and
  its settings (theme, texts and languages, kinds and colours, layout, 3D, checkout mode and end
  action, pricing). Admins manage them (Shop → Dealer embeds, `/api/admin/embeds`).
- **The API** `/api/embed/v1/<dpk>/…` (config, quote, scene, checkout, order, event) answers a
  browser only from the site's own origins (or our own website, which hosts the frame and the
  checkout): CORS per dealer, a foreign `Origin` is a 403 before anything runs, a POST needs an
  `Origin`. `GET /api/embed/v1/verify/<quote>` is for the dealer's server (Bearer `dsk_…`).
- **Prices** are computed here only: our B2B price for the company (`b2b.unit_price`) plus the
  dealer's margin, or a price list (a channel of the published price set, never the company's
  purchase list); VAT and the dealer's rounding. Answers carry the amount, the currency, VAT
  included or not and its rate; never the purchase price, the margin, a cost or the costing.
- **Checkout**, per site: ours (a hosted page in the dealer's look, `/embed/v1/checkout/<t>`,
  Turnstile and Mollie through the shop's own order code, the order flagged `dealer`) or the
  dealer's (`dealer_orders`: the dealer is mailed, confirms on `/embed/v1/confirm/<t>`, which
  makes a B2B order on account; or the dealer's own cart, by event).
- **The frame** (`/embed/v1/frame`) is the fallback for site builders without scripts: the same
  component on our page, `frame-ancestors` exactly the site's origins.
- **Preview only:** everything answers only with the shop setting `dealer_embed_enabled`, on the
  preview website or for a logged-in colleague. The demo dealers (config/embed_demo.json) answer
  only on the preview or for a colleague, and never order, mail or count.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import secrets
import sqlite3
import threading
import time
from collections import deque
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

CONFIG = Path(__file__).resolve().parents[3] / "config"
TEXTS_JSON = CONFIG / "embed_texts.json"
DEMO_JSON = CONFIG / "embed_demo.json"
PUBLIC_PREFIX, SECRET_PREFIX = "dpk_", "dsk_"
PUBLIC_KEY = re.compile(r"^dpk_[A-Za-z0-9_-]{6,64}$")
QUOTE_ID = re.compile(r"^[0-9a-f]{16}$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
LANGS = ("nl", "en", "de", "fr")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
FONT = re.compile(r"^[A-Za-z0-9 ,'\"-]{1,120}$")
ROUNDINGS = ("none", "1", "5", "10", "0.90", "0.95", "0.99")
LAYOUTS = ("full", "compact")
CHECKOUTS = ("ours", "dealer")
END_ACTIONS = {"ours": ("checkout",), "dealer": ("send_order", "cart")}
SUPPORTED = ("dining_set", "round_set")  # the kinds sold with balloons or a frame under them
OWN_TEXTS = {"title": 120, "intro": 600, "cta": 60, "thanks": 400}
EVENTS = ("load", "quote", "checkout", "order", "cart")
MAX_DOMAINS = 10
MARGIN_MAX = 500.0
RADIUS_MAX = 40
PERCENT = 100.0
DAY_S, HOUR_S, MINUTE_S = 86400.0, 3600.0, 60.0
STATUS_SHOWN = {
    "awaiting_payment": "status_awaiting_payment",
    "paid": "status_paid",
    "waiting_production": "status_paid",
    "in_production": "status_paid",
    "sewn": "status_paid",
    "shipped": "status_paid",
    "cancelled": "status_cancelled",
    "failed": "status_failed",
}
TURNSTILE = "https://challenges.cloudflare.com"
MOLLIE_FORMS = "https://www.mollie.com https://*.mollie.com"

SCHEMA = """
CREATE TABLE IF NOT EXISTS dealer_sites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL NOT NULL,
  updated REAL,
  company_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  public_key TEXT NOT NULL UNIQUE,
  secret_hash TEXT,
  secret_shown TEXT,
  domains TEXT NOT NULL DEFAULT '[]',
  settings TEXT NOT NULL DEFAULT '{}',
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS dealer_usage (
  day TEXT NOT NULL,
  site_id INTEGER NOT NULL,
  event TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, site_id, event)
);
CREATE TABLE IF NOT EXISTS dealer_checkouts (
  token TEXT PRIMARY KEY,
  created REAL NOT NULL,
  expires REAL NOT NULL,
  site_id INTEGER NOT NULL,
  site_key TEXT NOT NULL,
  quote_id TEXT NOT NULL,
  lang TEXT NOT NULL,
  order_id INTEGER
);
CREATE TABLE IF NOT EXISTS dealer_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL NOT NULL,
  site_id INTEGER NOT NULL,
  company_id INTEGER NOT NULL,
  token TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  quote_id TEXT NOT NULL,
  customer TEXT NOT NULL,
  lang TEXT NOT NULL,
  price_eur REAL NOT NULL,
  purchase_eur REAL NOT NULL,
  b2b_order INTEGER,
  decided REAL,
  idempotency_key TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS dealer_orders_once ON dealer_orders(site_id, idempotency_key);
"""

SITE_DEFAULTS: dict[str, Any] = {
    "theme": {
        "primary": "#1f4d3a",
        "accent": "#c8a24a",
        "text": "#1d1d1f",
        "background": "#ffffff",
        "surface": "#f4f3ef",
        "border": "#cfcabd",
        "radius_px": 10,
        "font": "inherit",  # the dealer page's own font
        "heading_font": "inherit",
        "logo_url": "",
    },
    "lang": "nl",
    "languages": list(LANGS),
    "texts": {},  # {lang: {title, intro, cta, thanks}}; empty: ours (config/embed_texts.json)
    "kinds": [],  # empty: every kind we offer
    "colours": [],  # empty: every fabric colour
    "layout": "full",
    "view3d": True,
    "checkout": "dealer",  # the safe default: nothing is paid to us until the owner says so
    "end_action": "send_order",
    "pricing": {
        "mode": "margin",  # margin over our B2B price, or "list": a channel of the price set
        "margin_pct": 40.0,  # to confirm per dealer
        "kind_margin_pct": {},
        "list": "b2c",
        "rounding": "1",
        "show_vat": True,
    },
    "return_url": "",  # our checkout: back to the dealer's site after paying
    "shipping": "customer",  # our checkout: the customer pays our rate, or "included"
    "dealer_confirms": True,  # dealer mode: the dealer confirms each order before it is made
    "deliver_to": "dealer",  # dealer mode: the B2B order is delivered to the dealer or "customer"
    "customer_mail": True,  # dealer mode: the customer gets a short "sent to <dealer>" mail
    "notify_email": "",  # dealer mode: where its orders go; empty: the company's e-mail
}


# ---- texts, demo dealers -----------------------------------------------------------------------


@lru_cache(maxsize=1)
def _texts() -> dict[str, dict[str, str]]:
    doc: dict[str, Any] = json.loads(TEXTS_JSON.read_text(encoding="utf-8"))
    return doc["texts"]  # type: ignore[no-any-return]


def texts(lang: str, own: dict[str, Any] | None = None) -> dict[str, str]:
    """Every text in one language (English where one is missing), the dealer's own on top."""
    out = {k: str(v.get(lang) or v.get("en") or "") for k, v in _texts().items()}
    for k, v in ((own or {}).get(lang) or {}).items():
        if k in OWN_TEXTS and str(v or "").strip():
            out[k] = str(v).strip()
    return out


@lru_cache(maxsize=1)
def demo_sites() -> dict[str, dict[str, Any]]:
    doc: dict[str, Any] = json.loads(DEMO_JSON.read_text(encoding="utf-8"))
    return doc["sites"]  # type: ignore[no-any-return]


def merged(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merged(base[k], v) if isinstance(base.get(k), dict) and isinstance(v, dict) else v
    return out


# ---- checking what an admin saves ---------------------------------------------------------------


def norm_origin(value: str) -> str | None:
    """An origin as browsers send it ("https://www.dealer.nl"), or None when it is not one: https
    only (http for localhost), no path, no wildcard, no user or query."""
    v = str(value or "").strip().rstrip("/").lower()
    try:
        u = urlparse(v)
        port = u.port
    except ValueError:
        return None
    host = u.hostname or ""
    local = host in ("localhost", "127.0.0.1")
    if u.scheme not in ("https", "http") or (u.scheme == "http" and not local):
        return None
    if not re.fullmatch(r"[a-z0-9.-]{1,253}", host) or "." not in host and not local:
        return None
    if u.path or u.query or u.fragment or u.username or u.password or "*" in v:
        return None
    return f"{u.scheme}://{host}" + (f":{port}" if port else "")


def purchase_lists(company: dict[str, Any]) -> set[str]:
    """The lists a dealer buys at: never a list its customers see (ADR-150)."""
    return {"b2b", str(company.get("price_list") or "b2b")}


class SettingsError(ValueError):
    pass


def clean_settings(  # noqa: C901 - one check per setting, in one place
    raw: dict[str, Any],
    channels: dict[str, Any],
    company: dict[str, Any],
    products: set[str],
    colours: list[str],
    domains: list[str],
) -> dict[str, Any]:
    """The settings as saved: every value checked (colours, fonts, the logo's address, the kinds
    and colours we offer, the checkout and its end action, the pricing); SettingsError says
    which one is wrong."""
    s = merged(SITE_DEFAULTS, raw or {})
    s = {k: s[k] for k in SITE_DEFAULTS}  # nothing unknown is kept
    t = {k: s["theme"].get(k, v) for k, v in SITE_DEFAULTS["theme"].items()}
    for k in ("primary", "accent", "text", "background", "surface", "border"):
        if not HEX.match(str(t[k])):
            raise SettingsError(f"theme.{k}: a colour as #rrggbb")
    for k in ("font", "heading_font"):
        if not FONT.match(str(t[k])):
            raise SettingsError(f"theme.{k}: font names, commas and quotes only")
    try:
        t["radius_px"] = int(t["radius_px"])
    except (TypeError, ValueError):
        raise SettingsError("theme.radius_px: a whole number") from None
    if not 0 <= t["radius_px"] <= RADIUS_MAX:
        raise SettingsError(f"theme.radius_px: 0 to {RADIUS_MAX}")
    logo = str(t["logo_url"] or "").strip()
    if logo:
        u = urlparse(logo)
        if u.scheme != "https" or not u.hostname or re.search(r"[\s\"'<>()\\]", logo):
            raise SettingsError("theme.logo_url: an https address")
    t["logo_url"] = logo[:500]
    s["theme"] = t
    if s["lang"] not in LANGS:
        raise SettingsError(f"lang: one of {', '.join(LANGS)}")
    s["languages"] = [x for x in LANGS if x in (s["languages"] or [])] or [s["lang"]]
    if s["lang"] not in s["languages"]:
        s["languages"].insert(0, s["lang"])
    own: dict[str, dict[str, str]] = {}
    for lang, d in (s["texts"] or {}).items():
        if lang not in LANGS or not isinstance(d, dict):
            continue
        own[lang] = {k: str(d.get(k) or "")[:n] for k, n in OWN_TEXTS.items() if d.get(k)}
    s["texts"] = own
    bad = [k for k in s["kinds"] if k not in products]
    if bad:
        raise SettingsError(f"kinds: unknown {', '.join(map(str, bad))}")
    bad = [c for c in s["colours"] if c not in colours]
    if bad:
        raise SettingsError(f"colours: unknown {', '.join(map(str, bad))}")
    if s["layout"] not in LAYOUTS:
        raise SettingsError("layout: full or compact")
    s["view3d"] = bool(s["view3d"])
    if s["checkout"] not in CHECKOUTS:
        raise SettingsError("checkout: ours or dealer")
    if s["end_action"] not in END_ACTIONS[s["checkout"]]:
        s["end_action"] = END_ACTIONS[s["checkout"]][0]
    p = {k: s["pricing"].get(k, v) for k, v in SITE_DEFAULTS["pricing"].items()}
    if p["mode"] not in ("margin", "list"):
        raise SettingsError("pricing.mode: margin or list")
    try:
        p["margin_pct"] = float(p["margin_pct"])
        p["kind_margin_pct"] = {
            str(k): float(v) for k, v in (p["kind_margin_pct"] or {}).items() if v not in (None, "")
        }
    except (TypeError, ValueError):
        raise SettingsError("pricing: a margin is a number (%)") from None
    for m in (p["margin_pct"], *p["kind_margin_pct"].values()):
        if not 0 <= m <= MARGIN_MAX:
            raise SettingsError(f"pricing: a margin from 0 to {MARGIN_MAX:g} %")
    if any(k not in products for k in p["kind_margin_pct"]):
        raise SettingsError("pricing.kind_margin_pct: an unknown kind")
    if p["mode"] == "list":
        if p["list"] not in channels:
            raise SettingsError("pricing.list: no such price list")
        if p["list"] in purchase_lists(company):
            raise SettingsError("pricing.list: the dealer's purchase list is never shown")
    if str(p["rounding"]) not in ROUNDINGS:
        raise SettingsError(f"pricing.rounding: one of {', '.join(ROUNDINGS)}")
    p["rounding"] = str(p["rounding"])
    p["show_vat"] = bool(p["show_vat"])
    s["pricing"] = p
    ret = str(s["return_url"] or "").strip()
    if ret:
        u = urlparse(ret)
        if norm_origin(f"{u.scheme}://{u.netloc}") not in domains:
            raise SettingsError("return_url: an address on one of the site's domains")
    s["return_url"] = ret[:500]
    if s["shipping"] not in ("customer", "included"):
        raise SettingsError("shipping: customer or included")
    if s["deliver_to"] not in ("dealer", "customer"):
        raise SettingsError("deliver_to: dealer or customer")
    for k in ("dealer_confirms", "customer_mail"):
        s[k] = bool(s[k])
    mail = str(s["notify_email"] or "").strip()
    if mail and not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}", mail, re.I):
        raise SettingsError("notify_email: an e-mail address")
    s["notify_email"] = mail
    return s


# ---- the dealer's price, on the server only --------------------------------------------------


def dealer_price(
    ps: dict[str, Any],
    company: dict[str, Any],
    costing_channels: dict[str, Any],
    pricing: dict[str, Any],
    product: str,
    support: str,
    supports: int,
) -> dict[str, Any]:
    """The end customer's price of one cover (with its support) on a dealer's site, and what the
    dealer buys it at. `amount`, `vat_included` and `vat_pct` may be shown; `purchase_eur`,
    `net_eur` and `gross_eur` stay on the server (the record, the dealer's mail)."""
    from coverengine import costing

    from coverapi import b2b

    purchase = float(
        b2b.unit_price(ps, company, costing_channels, None, support, supports)["unit_eur"]
    )
    vat = float(ps["channels"]["b2c"]["vat_pct"])
    if pricing["mode"] == "list":
        ch = str(pricing["list"])
        if ch not in ps["channels"] or ch in purchase_lists(company):
            raise HTTPException(409, "this dealer's price list is not available")
        net = float(costing_channels[ch]["net_eur"])
        if support in ("balloons", "frame"):
            each = float(
                costing.accessory_price(ps, "balloon" if support == "balloons" else "frame", ch)[
                    "net_eur"
                ]
            )
            net += each * (supports if support == "balloons" else 1)
        vat = float(ps["channels"][ch]["vat_pct"])
    else:
        m = float((pricing.get("kind_margin_pct") or {}).get(product, pricing["margin_pct"]))
        net = purchase * (1 + m / PERCENT)
    show = bool(pricing["show_vat"])
    shown = costing.round_price(net * (1 + vat / PERCENT) if show else net, pricing["rounding"])
    gross, net = (
        (shown, shown / (1 + vat / PERCENT)) if show else (shown * (1 + vat / PERCENT), shown)
    )
    return {
        "amount": round(shown, 2),
        "vat_included": show,
        "vat_pct": vat,
        "net_eur": round(net, 2),
        "gross_eur": round(gross, 2),
        "purchase_eur": round(purchase, 2),
    }


def public_price(p: dict[str, Any], indicative: bool) -> dict[str, Any]:
    """What a browser may see of a dealer price: built from a whitelist."""
    return {
        "amount": p["amount"],
        "currency": "EUR",
        "vat_included": p["vat_included"],
        "vat_pct": p["vat_pct"],
        "indicative": bool(indicative),
    }


def _day(now: float | None = None) -> str:
    return datetime.fromtimestamp(now or time.time(), UTC).strftime("%Y-%m-%d")


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def esc(x: Any) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


# ---- requests ------------------------------------------------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuoteIn(_In):
    product: str = Field(max_length=40)
    sizes: dict[str, Any] = Field(default_factory=dict)
    colour: str | None = Field(default=None, max_length=40)
    support: str = Field(default="none", pattern=r"^(none|balloons|frame)$")
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")


class CheckoutIn(_In):
    quote_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")


class DealerOrderIn(_In):
    quote_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    phone: str = Field(default="", max_length=40)
    street: str = Field(default="", max_length=160)
    postcode: str = Field(default="", max_length=20)
    city: str = Field(default="", max_length=80)
    country: str = Field(default="NL", min_length=2, max_length=2)
    note: str = Field(default="", max_length=2000)
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")
    website: str = Field(default="", max_length=200)  # the honeypot
    # one form, one order: the page sends the same key again on a retry (Codex, round 1)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{8,128}$")


class EventIn(_In):
    type: str = Field(pattern=r"^cart$")
    quote_id: str = Field(pattern=r"^[0-9a-f]{16}$")


class NewSiteIn(_In):
    company_id: int
    name: str = Field(min_length=1, max_length=80)


class SiteChangeIn(_In):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    domains: list[str] | None = None
    active: bool | None = None
    settings: dict[str, Any] | None = None


EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.I)


# ---- the store -----------------------------------------------------------------------------------


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _site(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["domains"] = json.loads(d["domains"] or "[]")
        d["settings"] = merged(SITE_DEFAULTS, json.loads(d["settings"] or "{}"))
        d["active"] = bool(d["active"])
        d["demo"] = False
        return d

    def by_key(self, public_key: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM dealer_sites WHERE public_key=?", (public_key,)
            ).fetchone()
        return self._site(row) if row else None

    def by_id(self, sid: int) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT * FROM dealer_sites WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such dealer site")
        return self._site(row)

    def by_secret(self, secret: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM dealer_sites WHERE secret_hash=?", (_h(secret),)
            ).fetchone()
        return self._site(row) if row else None

    def sites(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM dealer_sites ORDER BY active DESC, name").fetchall()
        return [self._site(r) for r in rows]

    def add(self, company_id: int, name: str) -> int:
        key = PUBLIC_PREFIX + secrets.token_urlsafe(18)
        with self.lock, self._db() as db:
            cur = db.execute(
                "INSERT INTO dealer_sites (created, updated, company_id, name, public_key) "
                "VALUES (?, ?, ?, ?, ?)",
                (time.time(), time.time(), company_id, name, key),
            )
        return int(cur.lastrowid or 0)

    def change(self, sid: int, cols: dict[str, Any]) -> None:
        cols = {**cols, "updated": time.time()}
        for k in ("domains", "settings"):
            if k in cols:
                cols[k] = json.dumps(cols[k])
        if "active" in cols:
            cols["active"] = int(bool(cols["active"]))
        sets = ", ".join(f"{k}=?" for k in cols)
        with self.lock, self._db() as db:
            db.execute(
                f"UPDATE dealer_sites SET {sets} WHERE id=?",  # noqa: S608 - our columns
                (*cols.values(), sid),
            )

    def count(self, sid: int, event: str) -> None:
        with self.lock, self._db() as db:
            db.execute(
                "INSERT INTO dealer_usage (day, site_id, event, count) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(day, site_id, event) DO UPDATE SET count = count + 1",
                (_day(), sid, event),
            )

    def today(self, sid: int, event: str) -> int:
        with self._db() as db:
            row = db.execute(
                "SELECT count FROM dealer_usage WHERE day=? AND site_id=? AND event=?",
                (_day(), sid, event),
            ).fetchone()
        return int(row[0]) if row else 0

    def usage(self, sid: int, days: int = 30) -> list[dict[str, Any]]:
        since = _day(time.time() - (days - 1) * DAY_S)
        with self._db() as db:
            rows = db.execute(
                "SELECT day, event, count FROM dealer_usage WHERE site_id=? AND day>=? "
                "ORDER BY day DESC",
                (sid, since),
            ).fetchall()
            paid = db.execute(
                "SELECT date(created, 'unixepoch') AS day, COUNT(*), SUM(total_eur) FROM orders "
                "WHERE json_extract(data, '$.dealer.site_id')=? AND created>=? AND status IN "
                "('paid','waiting_production','in_production','sewn','shipped') GROUP BY day",
                (sid, time.time() - days * DAY_S),
            ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            out.setdefault(r["day"], {"day": r["day"], **dict.fromkeys(EVENTS, 0)})[r["event"]] = r[
                "count"
            ]
        for day, n, eur in paid:
            d = out.setdefault(day, {"day": day, **dict.fromkeys(EVENTS, 0)})
            d["paid"], d["paid_eur"] = int(n), round(float(eur or 0), 2)
        return sorted(out.values(), key=lambda d: d["day"], reverse=True)


# ---- the app -------------------------------------------------------------------------------------


def install(app: FastAPI, auth: Any, data: Path, store: Any) -> None:  # noqa: C901, PLR0915
    from coverengine import quote as q
    from coverengine.errors import CoverError

    from coverapi import b2b as b2b_mod
    from coverapi import mailer, prices
    from coverapi import shipping as delivery
    from coverapi.ratelimit import quote_cap, visitor_key
    from coverapi.security import SESSION_COOKIE, _address, env_value, require
    from coverapi.shop import (
        SHOP_DEFAULTS,
        SHOP_SETTING,
        bbq_on,
        link_ok,
        preview_site,
        shop_params,
        site_host,
        turnstile_ok,
    )
    from coverapi.shop import merged as shop_merged

    db = Store(auth.path)
    app.state.dealer_embed = db
    quotes = data / "embed_quotes"
    quotes.mkdir(parents=True, exist_ok=True)
    windows: dict[str, deque[float]] = {}
    wlock = threading.Lock()

    def shop_settings() -> dict[str, Any]:
        return shop_merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})

    def staff(request: Request) -> bool:
        return auth.session_user(request.cookies.get(SESSION_COOKIE)) is not None

    def embed_on(request: Request) -> bool:
        """The live shop after the owner's go, the preview website, a colleague."""
        if shop_settings().get("dealer_embed_enabled"):
            return True
        return preview_site(auth, request) or staff(request)

    def visitor(request: Request) -> str:
        a = _address(request)
        if link_ok(auth, request):
            a = request.headers.get("x-client-ip") or a
        return visitor_key(a)

    def limits() -> Any:
        return shop_params(auth)

    def window(key: str, per: int, span: float) -> None:
        now = time.time()
        with wlock:
            times = windows.setdefault(key, deque())
            while times and now - times[0] >= span:
                times.popleft()
            if len(times) >= per:
                retry = int(times[0] + span - now) + 1
                raise HTTPException(
                    429,
                    "too many requests; please wait a little",
                    headers={"Retry-After": str(retry)},
                )
            times.append(now)
            if len(windows) > 20000:  # noqa: PLR2004 - forget the idle visitors
                for k in [k for k, v in windows.items() if not v or now - v[-1] >= span]:
                    del windows[k]

    def site_base(request: Request) -> str:
        """Where the hosted pages are: the website the Worker answered for, else this server."""
        host = site_host(request)
        if host and link_ok(auth, request) and re.fullmatch(r"[a-z0-9.-]+(:\d+)?", host):
            return f"https://{host}"
        scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        return f"{scheme}://{request.headers.get('host', 'localhost')}"

    def own_origins(request: Request) -> set[str]:
        """Our own pages that show the component: the website the Worker answered for (the
        frame, the demo) and, for a logged-in colleague, the studio's own address."""
        out: set[str] = set()
        host = site_host(request)
        if host and link_ok(auth, request):
            o = norm_origin(f"https://{host}")
            if o:
                out.add(o)
        if staff(request):
            h = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
            out |= {f"https://{h}", f"http://{h}"}
        return out

    # ---- which site, and may this page ask -------------------------------------------------------
    def demo_site(key: str, request: Request) -> dict[str, Any] | None:
        d = demo_sites().get(key)
        if d is None or not (preview_site(auth, request) or staff(request)):
            return None
        return {
            "id": 0,
            "company_id": 0,
            "name": d["name"],
            "public_key": key,
            "domains": [],
            "settings": merged(SITE_DEFAULTS, d["settings"]),
            "active": True,
            "demo": True,
        }

    def site_of(key: str, request: Request) -> dict[str, Any]:
        """The active dealer site of this public key (404 for anything else, whatever the
        reason: the gate, an unknown or inactive key, a blocked company)."""
        if not embed_on(request) or not PUBLIC_KEY.match(key or ""):
            raise HTTPException(404, "not here")
        site = demo_site(key, request) or db.by_key(key)
        if site is None or not site["active"]:
            raise HTTPException(404, "no such dealer")
        if not site["demo"] and company_of(site)["status"] != "active":
            raise HTTPException(404, "no such dealer")
        return site

    def company_of(site: dict[str, Any]) -> dict[str, Any]:
        if site["demo"]:  # our B2B list, no company's own prices
            return {
                "id": 0,
                "name": site["name"],
                "price_list": "b2b",
                "fixed": {},
                "reverse_charge": False,
                "status": "active",
                "email": "",
            }
        try:
            c: dict[str, Any] = app.state.b2b.company(int(site["company_id"]))
        except HTTPException:
            raise HTTPException(404, "no such dealer") from None
        return c

    def origin_allowed(site: dict[str, Any], request: Request) -> str | None:
        """The page's origin when it may use this site ("" without an Origin header: a same-site
        GET); None when it may not."""
        origin = request.headers.get("origin")
        if origin is None:
            return "" if request.method in ("GET", "HEAD") else None
        o = norm_origin(origin)
        if o and (o in site["domains"] or o in own_origins(request)):
            return o
        return None

    def cors(resp: Response, origin: str) -> Response:
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Vary"] = "Origin"
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Expose-Headers"] = "Retry-After"
        return resp

    def guard(key: str, request: Request) -> tuple[dict[str, Any], str]:
        site = site_of(key, request)
        origin = origin_allowed(site, request)
        if origin is None:
            raise HTTPException(403, "this website may not show this configurator")
        p = limits()
        window(
            f"m:{site['public_key']}:{visitor(request)}",
            int(p["limits.embed_per_minute"]),
            MINUTE_S,
        )
        return site, origin

    def count(site: dict[str, Any], event: str) -> None:
        if not site["demo"]:
            db.count(int(site["id"]), event)

    @app.middleware("http")
    async def embed_errors(request: Request, call_next: Any) -> Any:
        """Errors of the embed API carry the CORS header of an allowed page, so the component
        can show them; every answer is no-store."""
        path = request.url.path
        if path.startswith("/embed/v1/") and path.endswith(".js"):
            # the component's script for any page, as the Worker serves it (module scripts
            # need CORS)
            if not embed_on(request):  # both switches, the script too (Codex, round 1)
                return Response("not here", status_code=404)
            script: Response = await call_next(request)
            script.headers["Access-Control-Allow-Origin"] = "*"
            script.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
            return script
        if not path.startswith("/api/embed/v1/"):
            return await call_next(request)
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        origin = request.headers.get("origin")
        parts = path.split("/")  # "", api, embed, v1, <key>, ...
        key = parts[4] if len(parts) > 4 else ""  # noqa: PLR2004
        if origin and "access-control-allow-origin" not in response.headers:
            try:  # an error for a page that may ask: readable by that page
                ok = origin_allowed(site_of(key, request), request)
            except HTTPException:
                ok = None
            if ok:
                response.headers["Access-Control-Allow-Origin"] = ok
                response.headers["Vary"] = "Origin"
                response.headers["Access-Control-Expose-Headers"] = "Retry-After"
        return response

    def labels(lang: str) -> tuple[dict[str, str], dict[str, str]]:
        ui = app.state.site.read("live").get("ui") or {}

        def pick(group: str) -> dict[str, str]:
            return {
                k: str(v.get(lang) or v.get("en") or k)
                for k, v in (ui.get(group) or {}).items()
                if isinstance(v, dict)
            }

        return pick("product"), pick("field")

    def lang_of(site: dict[str, Any], asked: str | None) -> str:
        s = site["settings"]
        return str(asked if asked in s["languages"] else s["lang"])

    def offered(site: dict[str, Any], request: Request) -> tuple[dict[str, Any], list[str]]:
        p = shop_params(auth)
        opts = q.options(p, bbq_on(auth, request))
        kinds = site["settings"]["kinds"]
        products = {k: v for k, v in opts["products"].items() if not kinds or k in kinds}
        allowed = site["settings"]["colours"]
        colours = [c for c in q.colours(p) if not allowed or c in allowed]
        return products, colours

    # ---- the public API ------------------------------------------------------------------------
    @app.options("/api/embed/v1/{key}/{rest:path}")
    def preflight(key: str, rest: str, request: Request) -> Response:
        site = site_of(key, request)
        origin = origin_allowed(site, request)
        if not origin:
            raise HTTPException(403, "this website may not show this configurator")
        r = Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Methods": "GET, POST",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "600",
            },
        )
        return cors(r, origin)

    @app.get("/api/embed/v1/{key}/config")
    def config(key: str, request: Request, lang: str | None = None) -> Response:
        site, origin = guard(key, request)
        s = site["settings"]
        lg = lang_of(site, lang)
        names, fields = labels(lg)
        products, colours = offered(site, request)
        company = company_of(site)
        doc = {
            "dealer": {
                "name": company["name"] if not site["demo"] else site["name"],
                "key": site["public_key"],
            },
            "lang": lg,
            "languages": s["languages"],
            "texts": texts(lg, s["texts"]),
            "theme": s["theme"],
            "layout": s["layout"],
            "view3d": s["view3d"],
            "checkout": s["checkout"],
            "end_action": s["end_action"],
            "show_vat": s["pricing"]["show_vat"],
            "shipping_extra": s["checkout"] == "ours" and s["shipping"] == "customer",
            "products": [
                {
                    "key": k,
                    "label": names.get(k) or v["label"],
                    "supports": k in SUPPORTED,
                    "fields": [
                        {**f, "label": fields.get(f["key"]) or f["key"]} for f in v["fields"]
                    ],
                }
                for k, v in products.items()
            ],
            "colours": colours,
            "origins": sorted(site["domains"]),  # where the frame may tell its parent
            "demo": site["demo"],
        }
        count(site, "load")
        return cors(JSONResponse(doc), origin)

    def load_quote(site: dict[str, Any], qid: str) -> dict[str, Any]:
        path = quotes / f"{qid}.json"
        if not QUOTE_ID.match(qid) or not path.is_file():
            raise HTTPException(404, "this price has expired; please make it again")
        rec: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("embed", {}).get("site") != site["public_key"]:
            raise HTTPException(404, "this price has expired; please make it again")
        return rec

    @app.post("/api/embed/v1/{key}/quote")
    def quote(key: str, req: QuoteIn, request: Request) -> Response:
        site, origin = guard(key, request)
        s, p = site["settings"], limits()
        products, colours = offered(site, request)
        if req.product not in products:
            raise HTTPException(400, "this dealer does not offer this kind of furniture")
        if req.colour is not None and req.colour not in colours:
            raise HTTPException(400, "this dealer does not offer this colour")
        colour = req.colour or (colours[0] if site["settings"]["colours"] else None)
        if req.support != "none" and req.product not in SUPPORTED:
            raise HTTPException(400, "a support is only for a table")
        if not site["demo"] and db.today(int(site["id"]), "quote") >= int(
            p["limits.embed_site_quotes_per_day"]
        ):
            raise HTTPException(
                429,
                "this dealer's prices of today are used up",
                headers={"Retry-After": str(int(DAY_S - time.time() % DAY_S))},
            )
        if not quote_cap(app).hit():
            raise HTTPException(
                429,
                "many prices are asked just now; please try again soon",
                headers={"Retry-After": "30"},
            )
        ps = prices.current(auth)
        given = {**req.sizes, "vents": True, "colour": colour}
        try:
            full = q.proposal(req.product, given, shop_params(auth), ps)
            glb = (
                q.scene_glb(req.product, given, shop_params(auth), req.support)
                if s["view3d"]
                else None
            )
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        n = int(full["balloons"] or 1)
        price = dealer_price(
            ps,
            company_of(site),
            full["price"]["costing"]["channels"],
            s["pricing"],
            req.product,
            req.support,
            n,
        )
        indicative = bool(full["price"]["placeholder_prices"])
        qid = q.new_id()
        # the record in the shop's own shape (the order and production read it), server only
        record = {
            "time": time.time(),
            "input": {
                "product": req.product,
                "sizes": req.sizes,
                "colour": colour,
                "vents": True,
                "support": req.support,
                "stock_model": None,
                "match_token": None,
            },
            "quote": full,
            "rain": None,
            "support_eur": 0.0,
            "stock": None,
            "match_token": None,
            "embed": {
                "site": site["public_key"],
                "site_id": site["id"],
                "company_id": site["company_id"],
                "demo": site["demo"],
                "lang": lang_of(site, req.lang),
                **price,
                "indicative": indicative,
            },
        }
        (quotes / f"{qid}.json").write_text(json.dumps(record), encoding="utf-8")
        if glb is not None:
            (quotes / f"{qid}.glb").write_bytes(glb)
        count(site, "quote")
        doc = {
            "id": qid,
            "product": full["product"],
            "sizes_cm": full["sizes_cm"],
            "colour": full["colour"],
            "support": req.support,
            "pieces": len(full["pieces"]),
            "price": public_price(price, indicative),
            "scene": f"/api/embed/v1/{key}/scene/{qid}.glb" if glb is not None else None,
        }
        return cors(JSONResponse(doc), origin)

    @app.get("/api/embed/v1/{key}/scene/{qid}.glb")
    def scene(key: str, qid: str, request: Request) -> Response:
        site, origin = guard(key, request)
        load_quote(site, qid)
        path = quotes / f"{qid}.glb"
        if not path.is_file():
            raise HTTPException(404, "no 3D for this price")
        return cors(Response(path.read_bytes(), media_type="model/gltf-binary"), origin)

    def order_limits(site: dict[str, Any], request: Request) -> None:
        p = limits()
        window(f"o:{visitor(request)}", int(p["limits.embed_orders_per_hour"]), HOUR_S)
        if not site["demo"] and db.today(int(site["id"]), "order") + db.today(
            int(site["id"]), "checkout"
        ) >= int(p["limits.embed_site_orders_per_day"]):
            raise HTTPException(429, "this dealer's orders of today are used up")

    @app.post("/api/embed/v1/{key}/checkout")
    def checkout(key: str, req: CheckoutIn, request: Request) -> Response:
        """Our checkout in the dealer's look: a link to the hosted page, for this price only."""
        site, origin = guard(key, request)
        s = site["settings"]
        if s["checkout"] != "ours":
            raise HTTPException(409, "this dealer takes the orders itself")
        rec = load_quote(site, req.quote_id)
        if rec["embed"]["net_eur"] < rec["embed"]["purchase_eur"]:
            raise HTTPException(409, "this price cannot be ordered here; please contact the dealer")
        order_limits(site, request)
        token = secrets.token_urlsafe(24)
        hours = float(limits()["limits.embed_checkout_hours"])
        with db._db() as c:
            c.execute(
                "INSERT INTO dealer_checkouts (token, created, expires, site_id, site_key, "
                "quote_id, lang) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    token,
                    time.time(),
                    time.time() + hours * HOUR_S,
                    site["id"],
                    site["public_key"],
                    req.quote_id,
                    lang_of(site, req.lang),
                ),
            )
        count(site, "checkout")
        url = f"{site_base(request)}/embed/v1/checkout/{token}"
        return cors(JSONResponse({"checkout_url": url}), origin)

    @app.post("/api/embed/v1/{key}/event")
    def event(key: str, req: EventIn, request: Request) -> Response:
        """The dealer's own cart took a price (end action "cart"): counted, nothing else."""
        site, origin = guard(key, request)
        load_quote(site, req.quote_id)
        count(site, req.type)
        return cors(JSONResponse({"ok": True}), origin)

    @app.post("/api/embed/v1/{key}/order")
    def dealer_order(key: str, req: DealerOrderIn, request: Request) -> Response:
        """Dealer mode: the customer's order goes to the dealer, who confirms it."""
        site, origin = guard(key, request)
        s = site["settings"]
        if s["checkout"] != "dealer" or s["end_action"] != "send_order":
            raise HTTPException(409, "this dealer does not take orders this way")
        if req.website:  # the honeypot
            raise HTTPException(400, "this could not be sent")
        if not EMAIL.match(req.email.strip()):
            raise HTTPException(400, "please give a valid e-mail address")
        rec = load_quote(site, req.quote_id)
        if rec["embed"]["net_eur"] < rec["embed"]["purchase_eur"]:  # never under our B2B price
            raise HTTPException(409, "this price cannot be ordered here; please contact the dealer")
        if not site["demo"]:  # a retry of the same form: the order it made (Codex, round 1)
            with db._db() as c:
                done = c.execute(
                    "SELECT id FROM dealer_orders WHERE site_id=? AND idempotency_key=?",
                    (site["id"], req.idempotency_key),
                ).fetchone()
            if done:
                return cors(JSONResponse({"reference": f"D{done['id']}", "repeat": True}), origin)
        order_limits(site, request)
        lg = lang_of(site, req.lang)
        if site["demo"]:
            return cors(
                JSONResponse({"reference": "DEMO-" + secrets.token_hex(3).upper(), "demo": True}),
                origin,
            )
        token = secrets.token_urlsafe(24)
        customer = req.model_dump(exclude={"website", "quote_id", "lang", "idempotency_key"})
        customer["email"] = customer["email"].strip()
        customer["country"] = customer["country"].upper()
        try:
            with db._db() as c:
                cur = c.execute(
                    "INSERT INTO dealer_orders (created, site_id, company_id, token, status, "
                    "quote_id, customer, lang, price_eur, purchase_eur, idempotency_key) VALUES "
                    "(?, ?, ?, ?, 'sent', ?, ?, ?, ?, ?, ?)",
                    (
                        time.time(),
                        site["id"],
                        site["company_id"],
                        token,
                        req.quote_id,
                        json.dumps(customer),
                        lg,
                        rec["embed"]["amount"],
                        rec["embed"]["purchase_eur"],
                        req.idempotency_key,
                    ),
                )
                oid = int(cur.lastrowid or 0)
        except sqlite3.IntegrityError:  # the same key at the same moment: the other one won
            with db._db() as c:
                done = c.execute(
                    "SELECT id FROM dealer_orders WHERE site_id=? AND idempotency_key=?",
                    (site["id"], req.idempotency_key),
                ).fetchone()
            return cors(JSONResponse({"reference": f"D{done['id']}", "repeat": True}), origin)
        count(site, "order")
        ref = f"D{oid}"
        company = company_of(site)
        if not s["dealer_confirms"]:
            decide(oid, "confirm", "auto (dealer_confirms off)")
        mail_dealer(site, company, oid, ref, token, rec, customer, request)
        if s["customer_mail"]:
            t = texts(lg, s["texts"])
            dealer = company["name"]
            send(
                customer["email"],
                t["mail_customer_subject"].replace("{dealer}", dealer),
                t["mail_customer_text"].replace("{dealer}", dealer)
                + "\n\n"
                + t["sent_text"].replace("{dealer}", dealer).replace("{n}", ref)
                + "\n",
                f"embed-customer:{oid}",
            )
        return cors(JSONResponse({"reference": ref}), origin)

    # ---- mails ---------------------------------------------------------------------------------
    def send(to: str, subject: str, text: str, ref: str) -> None:
        try:
            mailer.queue(auth, to, subject, text, "embed", ref)
        except Exception:  # noqa: BLE001 - a mail never stops an order
            pass

    def describe(rec: dict[str, Any]) -> str:
        qd = rec["quote"]
        sizes = ", ".join(f"{k} {v}" for k, v in qd["sizes_cm"].items())
        support = rec["input"]["support"]
        return f"{qd['product']}: {sizes}; {qd['colour']}" + (
            f"; support {support}" if support != "none" else ""
        )

    def mail_dealer(
        site: dict[str, Any],
        company: dict[str, Any],
        oid: int,
        ref: str,
        token: str,
        rec: dict[str, Any],
        customer: dict[str, Any],
        request: Request,
    ) -> None:
        s = site["settings"]
        t = texts(s["lang"], {})
        to = s["notify_email"] or company.get("email") or ""
        e = rec["embed"]
        link = f"{site_base(request)}/embed/v1/confirm/{token}"
        c = customer
        body = (
            f"{t['confirm_title']} ({site['name']}) {ref}\n\n{describe(rec)}\n\n"
            f"{t['customer_price']}: EUR {e['amount']:.2f} "
            f"({t['incl_vat'] if e['vat_included'] else t['ex_vat']})\n"
            f"{t['your_price']}: EUR {e['purchase_eur']:.2f}\n\n"
            f"{c['name']} <{c['email']}> {c['phone']}\n{c['street']}, {c['postcode']} "
            f"{c['city']}, {c['country']}\n{c['note']}\n\n"
            + (
                f"{t['confirm_button']} / {t['decline_button']}: {link}\n"
                if s["dealer_confirms"]
                else ""
            )
        )
        if to:
            send(to, f"{t['confirm_title']}: {ref}", body, f"embed-dealer:{oid}")
        alert = str(auth.setting("alert_email", "rick@s2dio.industries"))
        send(
            alert,
            f"Dealer embed order {ref}: {company['name']}",
            f"Sent to {company['name']} from its website ({site['name']}).\n\n{body}",
            f"embed-studio:{oid}",
        )

    # ---- the dealer confirms: a B2B order on account ---------------------------------------------
    def decide(oid: int, action: str, who: str) -> dict[str, Any]:
        """Confirm (a B2B order on account at the dealer's purchase price, waiting for Send to
        production as every order, ADR-128) or decline, once. Returns the row."""
        with sqlite3.connect(auth.path, timeout=10) as c:
            c.row_factory = sqlite3.Row
            c.execute("BEGIN IMMEDIATE")
            row = dict(c.execute("SELECT * FROM dealer_orders WHERE id=?", (oid,)).fetchone())
            if row["status"] != "sent":
                return row
            if action == "decline":
                c.execute(
                    "UPDATE dealer_orders SET status='declined', decided=? WHERE id=?",
                    (time.time(), oid),
                )
                row["status"] = "declined"
                return row
            site = db.by_id(int(row["site_id"]))
            company = app.state.b2b.company(int(row["company_id"]))
            if company["status"] != "active":
                raise HTTPException(409, "the business account is not active")
            if not site["active"] or site["settings"]["checkout"] != "dealer":
                raise HTTPException(409, "this dealer site does not take orders any more")
            rec = json.loads((quotes / f"{row['quote_id']}.json").read_text(encoding="utf-8"))
            cust = json.loads(row["customer"])
            ps = prices.current(auth)
            bs = shop_merged(b2b_mod.DEFAULTS, auth.setting(b2b_mod.SETTING, {}) or {})
            unit = float(rec["embed"]["purchase_eur"])
            if float(rec["embed"]["net_eur"]) < unit:
                raise HTTPException(409, "this price is under the purchase price")
            qd = rec["quote"]
            line = {
                "quote_id": row["quote_id"],
                "qty": 1,
                "unit_eur": unit,
                "total_eur": unit,
                "product": qd["product"],
                "label": None,
                "stock_model": None,
                "colour": qd["colour"],
                "sizes_cm": qd["sizes_cm"],
                "support": rec["input"]["support"],
                "input": rec["input"],
            }
            if site["settings"]["deliver_to"] == "customer" and cust.get("street"):
                addr = {
                    "id": None,
                    "label": "customer",
                    "name": cust["name"],
                    "street": cust["street"],
                    "postcode": cust["postcode"],
                    "city": cust["city"],
                    "country": cust["country"],
                }
            else:
                addr = b2b_mod.invoice_address(company)
            net = round(unit + float(bs["shipping_eur"] or 0), 2)
            vat = round(net * b2b_mod.vat_pct(ps, company) / PERCENT, 2)
            po = f"WEB-D{oid}"
            note = f"From {site['name']}: {cust['name']} ({cust['city']})"
            bid = app.state.b2b.add_order(
                {
                    "company_id": company["id"],
                    "user_id": 0,
                    "po": po,
                    "note": note,
                    "address": addr,
                    "lines": [line],
                    "net_eur": net,
                    "vat_eur": vat,
                    "gross_eur": round(net + vat, 2),
                    "payment": "account",
                },
                f"embed-{oid}",
                c,
            )
            doc = {
                "customer": {
                    "name": addr.get("name") or company["name"],
                    "email": company.get("email") or "",
                    "phone": company.get("phone") or "",
                    "street": addr["street"],
                    "postcode": addr["postcode"],
                    "city": addr["city"],
                    "country": addr["country"],
                    "note": note,
                    "terms": True,
                    "lang": row["lang"],
                    "company": company["name"],
                    "vat_number": company.get("vat_number") or "",
                },
                "quote": rec,
                "shipping_eur": 0.0,
                "lang": row["lang"],
                "b2b": {
                    "order": bid,
                    "line": 1,
                    "lines": 1,
                    "company_id": company["id"],
                    "company": company["name"],
                    "po": po,
                    "qty": 1,
                    "unit_eur": unit,
                    "ex_vat": True,
                    "payment": "account",
                },
                "dealer": {
                    "site_id": site["id"],
                    "mode": "dealer",
                    "reference": f"D{oid}",
                    "end_price_eur": row["price_eur"],
                },
            }
            cur = c.execute(
                "INSERT INTO orders (created, token, status, email, data, total_eur, updated) "
                "VALUES (?, ?, 'waiting_production', ?, ?, ?, ?)",
                (
                    time.time(),
                    secrets.token_urlsafe(18),
                    company.get("email") or "",
                    json.dumps(doc),
                    unit,
                    time.time(),
                ),
            )
            line["order_id"] = int(cur.lastrowid or 0)
            c.execute("INSERT INTO b2b_dispatch(order_id) VALUES (?)", (line["order_id"],))
            c.execute("UPDATE b2b_orders SET lines=? WHERE id=?", (json.dumps([line]), bid))
            c.execute(
                "UPDATE dealer_orders SET status='confirmed', decided=?, b2b_order=? WHERE id=?",
                (time.time(), bid, oid),
            )
            row.update(status="confirmed", b2b_order=bid)
        auth.log(who, "dealer embed order confirmed", {"order": oid, "b2b_order": row["b2b_order"]})
        return row

    # ---- the dealer's server reads a quote back ------------------------------------------------
    @app.get("/api/embed/v1/verify/{qid}")
    def verify(qid: str, request: Request) -> dict[str, Any]:
        bearer = request.headers.get("authorization", "")
        secret = bearer[7:].strip() if bearer.lower().startswith("bearer ") else ""
        if not embed_on(request):
            raise HTTPException(404, "not here")
        window(f"v:{visitor(request)}", int(limits()["limits.embed_per_minute"]), MINUTE_S)
        site = db.by_secret(secret) if secret.startswith(SECRET_PREFIX) else None
        if site is None or not site["active"]:
            raise HTTPException(401, "unknown or revoked secret key")
        rec = load_quote(site, qid)
        e, qd = rec["embed"], rec["quote"]
        return {
            "id": qid,
            "created": rec["time"],
            "product": qd["product"],
            "sizes_cm": qd["sizes_cm"],
            "colour": qd["colour"],
            "support": rec["input"]["support"],
            "price": public_price(e, e.get("indicative", False)),
            "purchase": {"amount": e["purchase_eur"], "currency": "EUR", "vat_included": False},
        }

    # ---- the hosted pages: the frame, our checkout, the status page, the dealer's confirmation --
    def theme_css(theme: dict[str, Any]) -> str:
        t = {
            k: (v if HEX.match(str(v)) else SITE_DEFAULTS["theme"][k])
            for k, v in theme.items()
            if k in ("primary", "accent", "text", "background", "surface", "border")
        }
        font = theme.get("font") if FONT.match(str(theme.get("font"))) else "inherit"
        head = theme.get("heading_font") if FONT.match(str(theme.get("heading_font"))) else font
        font = "system-ui, sans-serif" if font == "inherit" else font
        head = font if head == "inherit" else head
        r = int(theme.get("radius_px") or 0)
        return (
            f":root{{--p:{t['primary']};--a:{t['accent']};--t:{t['text']};--bg:{t['background']};"
            f"--s:{t['surface']};--b:{t['border']};--r:{r}px}}"
            f"body{{margin:0;background:var(--bg);color:var(--t);font-family:{font};"
            "line-height:1.45}"
            f"h1,h2{{font-family:{head};font-weight:600}}"
            "main{max-width:560px;margin:0 auto;padding:24px 16px 48px}"
            "header{display:flex;align-items:center;gap:12px;margin-bottom:12px}"
            "header img{max-height:48px;max-width:180px}"
            ".card{background:var(--s);border:1px solid var(--b);border-radius:var(--r);"
            "padding:16px;margin:12px 0}"
            "label{display:block;margin:10px 0 4px;font-size:.92em}"
            "input,select,textarea{width:100%;box-sizing:border-box;padding:10px;font:inherit;"
            "border:1px solid var(--b);border-radius:calc(var(--r)/2);background:var(--bg);"
            "color:var(--t)}"
            ".check{display:flex;gap:8px;align-items:center}.check input{width:auto}"
            "button,.button{display:inline-block;margin-top:16px;padding:12px 20px;border:0;"
            "border-radius:var(--r);background:var(--p);color:var(--bg);font:inherit;"
            "font-weight:600;cursor:pointer;text-decoration:none}"
            "button.secondary{background:transparent;color:var(--t);border:1px solid var(--b)}"
            ".row{display:flex;justify-content:space-between;gap:12px}"
            ".muted{opacity:.75;font-size:.9em}.error{color:#b3261e}"
            ".trap{position:absolute;left:-9999px}"
        )

    def page(
        theme: dict[str, Any],
        lang: str,
        title: str,
        body: str,
        *,
        turnstile: bool = False,
        frame_ancestors: str = "'none'",
        status: int = 200,
        frame: bool = False,
    ) -> HTMLResponse:
        """A hosted page in the dealer's look: its own CSP (the dealer's logo host, Turnstile
        only where it is asked, the form to Mollie, who may frame it)."""
        logo = str(theme.get("logo_url") or "")
        u = urlparse(logo)
        img = f" https://{u.hostname}" if logo and u.scheme == "https" and u.hostname else ""
        scripts = f" {TURNSTILE}" if turnstile else ""
        frames = TURNSTILE if turnstile else "'none'"
        blob = " blob:" if frame else ""  # the 3D view's textures
        csp = (
            f"default-src 'self'; script-src 'self'{scripts}; style-src 'self' "
            f"'unsafe-inline'; img-src 'self' data:{blob}{img}; connect-src 'self'; "
            f"frame-src {frames}; object-src 'none'; base-uri 'none'; "
            f"form-action 'self' {MOLLIE_FORMS}; frame-ancestors {frame_ancestors}"
        )
        head = f'<header><img src="{esc(logo)}" alt=""></header>' if img and not frame else ""
        wide = "<style>main{max-width:none;padding:0}</style>" if frame else ""
        doc = (
            f'<!doctype html><html lang="{esc(lang)}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex">'
            f"<title>{esc(title)}</title><style>{theme_css(theme)}</style>{wide}"
            + (
                f'<script src="{TURNSTILE}/turnstile/v0/api.js" async defer></script>'
                if turnstile
                else ""
            )
            + f"</head><body><main>{head}{body}</main></body></html>"
        )
        return HTMLResponse(
            doc,
            status,
            headers={
                "Content-Security-Policy": csp,
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
            },
        )

    @app.get("/embed/v1/frame", include_in_schema=False)
    def frame(request: Request, dealer: str = "", lang: str = "") -> HTMLResponse:
        """The fallback for site builders that refuse scripts: the component on our page,
        framed only by the site's own origins."""
        site = site_of(dealer, request)
        s = site["settings"]
        lg = lang_of(site, lang or None)
        ancestors = " ".join(["'self'", *site["domains"]])
        body = (
            f'<s2dio-configurator dealer="{esc(site["public_key"])}" lang="{esc(lg)}" frame>'
            "</s2dio-configurator>"
            '<script type="module" src="/embed/v1/configurator.js"></script>'
        )
        # the component shows the logo itself; the page's CSP allows its host
        return page(
            s["theme"],
            lg,
            texts(lg, s["texts"])["title"],
            body,
            frame_ancestors=ancestors,
            frame=True,
        )

    def checkout_row(token: str, request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
        """The checkout and its site (still active, its company too; a demo's only where the
        demo answers)."""
        if not TOKEN.match(token or ""):
            raise HTTPException(404, "no such checkout")
        with db._db() as c:
            row = c.execute("SELECT * FROM dealer_checkouts WHERE token=?", (token,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such checkout")
        return dict(row), site_of(str(row["site_key"]), request)

    def countries() -> list[dict[str, Any]]:
        return [x for x in shop_settings()["shipping"] if x.get("country")]

    def checkout_form(
        site: dict[str, Any],
        rec: dict[str, Any],
        token: str,
        lang: str,
        error: str = "",
        values: dict[str, str] | None = None,
    ) -> str:
        t = texts(lang, site["settings"]["texts"])
        e, v = rec["embed"], values or {}
        vat = t["incl_vat"] if e["vat_included"] else t["ex_vat"]
        opts = "".join(
            f'<option value="{esc(x["country"])}"'
            f"{' selected' if x['country'] == v.get('country', 'NL') else ''}>"
            f"{esc(x.get('name') or x['country'])}</option>"
            for x in countries()
        )

        def field(name: str, kind: str = "text", required: bool = True) -> str:
            return (
                f'<label for="{name}">{esc(t[name])}</label><input id="{name}" name="{name}" '
                f'type="{kind}" value="{esc(v.get(name, ""))}"'
                f'{" required" if required else ""} maxlength="160">'
            )

        site_key = env_value("TURNSTILE_SITE_KEY")
        widget = (
            f'<div class="cf-turnstile" data-sitekey="{esc(site_key)}"></div>' if site_key else ""
        )
        demo = f'<p class="muted">{esc(t["demo"])}</p>' if site["demo"] else ""
        return (
            f"<h1>{esc(t['checkout_title'])}</h1>{demo}"
            f'<div class="card"><div class="row"><span>{esc(describe(rec))}</span>'
            f"<strong>EUR {e['amount']:.2f}</strong></div>"
            f'<div class="muted">{esc(vat)}'
            + (
                f" · {esc(t['shipping_extra'])}"
                if site["settings"]["shipping"] == "customer"
                else ""
            )
            + "</div></div>"
            + (f'<p class="error">{esc(error)}</p>' if error else "")
            + f'<form method="post" action="/embed/v1/checkout/{esc(token)}" class="card">'
            f"<h2>{esc(t['your_details'])}</h2>"
            + field("name")
            + field("email", "email")
            + field("phone", "tel", False)
            + field("street")
            + field("postcode")
            + field("city")
            + f'<label for="country">{esc(t["country"])}</label>'
            f'<select id="country" name="country">{opts}</select>'
            + field("note", "text", False)
            + '<input class="trap" name="website" tabindex="-1" autocomplete="off" '
            'aria-hidden="true">'
            f'<label class="check"><input type="checkbox" name="terms" value="1" required>'
            f"{esc(t['terms'])}</label>{widget}"
            f'<button type="submit">{esc(t["pay"])}</button></form>'
        )

    @app.get("/embed/v1/checkout/{token}", include_in_schema=False)
    def checkout_page(token: str, request: Request) -> HTMLResponse:
        row, site = checkout_row(token, request)
        lang = row["lang"]
        t = texts(lang, site["settings"]["texts"])
        theme = site["settings"]["theme"]
        if row["order_id"]:  # paid or on its way: the status page
            with db._db() as c:
                o = c.execute("SELECT token FROM orders WHERE id=?", (row["order_id"],)).fetchone()
            return RedirectResponse(f"/embed/v1/order/{o['token']}", 303)  # type: ignore[return-value]
        if row["expires"] < time.time():
            return page(theme, lang, t["checkout_title"], f"<p>{esc(t['expired'])}</p>", status=410)
        rec = load_quote(site, row["quote_id"])
        return page(
            theme,
            lang,
            t["checkout_title"],
            checkout_form(site, rec, token, lang),
            turnstile=bool(env_value("TURNSTILE_SITE_KEY")),
        )

    @app.post("/embed/v1/checkout/{token}", include_in_schema=False)
    async def checkout_post(token: str, request: Request) -> Response:  # noqa: C901
        origin = request.headers.get("origin")
        if origin is not None and norm_origin(origin) != norm_origin(site_base(request)):
            raise HTTPException(403, "request from another site")
        row, site = checkout_row(token, request)
        lang, s = row["lang"], site["settings"]
        t = texts(lang, s["texts"])
        theme = s["theme"]
        form = await request.form()
        v = {
            k: str(form.get(k) or "").strip()[:2000]
            for k in (
                "name",
                "email",
                "phone",
                "street",
                "postcode",
                "city",
                "country",
                "note",
                "terms",
                "website",
                "cf-turnstile-response",
            )
        }
        rec = load_quote(site, row["quote_id"])

        def again(msg: str, status: int = 400) -> HTMLResponse:
            return page(
                theme,
                lang,
                t["checkout_title"],
                checkout_form(site, rec, token, lang, msg, v),
                status=status,
                turnstile=bool(env_value("TURNSTILE_SITE_KEY")),
            )

        if row["expires"] < time.time():
            return page(theme, lang, t["checkout_title"], f"<p>{esc(t['expired'])}</p>", status=410)
        if site["demo"]:
            return again(t["demo"], 409)
        if v["website"]:
            return again(t["error"])
        required = ("name", "email", "street", "postcode", "city", "country")
        if any(not v[k] for k in required) or not v["terms"] or not EMAIL.match(v["email"]):
            return again(t["error"])
        if v["country"].upper() not in {x["country"].upper() for x in countries()}:
            return again(t["error"])
        with db._db() as c:
            done = c.execute(
                "SELECT order_id FROM dealer_checkouts WHERE token=?", (token,)
            ).fetchone()
        repeat = bool(done and done["order_id"])
        if not repeat and not turnstile_ok(v["cf-turnstile-response"], visitor(request)):
            return again(t["error"])
        e = rec["embed"]
        if e["net_eur"] < e["purchase_eur"]:
            return again(t["error"], 409)
        shipping, source = 0.0, "included"
        if s["shipping"] == "customer":
            rate = delivery.quote(
                shop_settings()["shipping"],
                v["country"],
                v["postcode"],
                rec["quote"].get("fabric_m2"),
                shop_params(auth),
            )
            if rate is None:
                return again(t["error"])
            shipping, source = rate.eur, rate.source
        company = company_of(site)
        order_token = secrets.token_urlsafe(18)
        base = site_base(request)
        customer = {
            k: v[k] for k in ("name", "email", "phone", "street", "postcode", "city", "note")
        } | {
            "country": v["country"].upper(),
            "terms": True,
            "lang": lang,
            "quote_id": row["quote_id"],
        }
        total = round(float(e["gross_eur"]) + shipping, 2)
        data_doc = {
            "customer": customer,
            "quote": rec,
            "shipping_eur": shipping,
            "shipping_source": source,
            "lang": lang,
            "stock": None,
            "status_url": f"{base}/embed/v1/order/{order_token}",
            "dealer": {
                "site_id": site["id"],
                "site": site["name"],
                "mode": "ours",
                "company_id": company["id"],
                "company": company["name"],
                "end_price_eur": e["gross_eur"],
                "end_net_eur": e["net_eur"],
                "purchase_eur": e["purchase_eur"],
                "margin_eur": round(e["net_eur"] - e["purchase_eur"], 2),
                "return_url": s["return_url"],
            },
        }
        with sqlite3.connect(auth.path, timeout=10) as c:
            c.execute("BEGIN IMMEDIATE")
            got = c.execute(
                "SELECT order_id FROM dealer_checkouts WHERE token=?", (token,)
            ).fetchone()
            if got and got[0]:
                oid, repeat = int(got[0]), True
            else:
                cur = c.execute(
                    "INSERT INTO orders (created, token, status, email, data, total_eur, updated,"
                    " idempotency_key) VALUES (?, ?, 'awaiting_payment', ?, ?, ?, ?, ?)",
                    (
                        time.time(),
                        order_token,
                        v["email"],
                        json.dumps(data_doc),
                        total,
                        time.time(),
                        f"embed-{token}",
                    ),
                )
                oid = int(cur.lastrowid or 0)
                c.execute("UPDATE dealer_checkouts SET order_id=? WHERE token=?", (oid, token))
        try:
            out = app.state.shop_finish_order(oid, request, repeat)
        except HTTPException:
            return again(t["error"], 502)
        return RedirectResponse(out.get("checkout_url") or out["status_url"], 303)

    @app.get("/embed/v1/order/{token}", include_in_schema=False)
    def order_status(token: str, request: Request) -> HTMLResponse:
        if not embed_on(request) or not re.fullmatch(r"[A-Za-z0-9_-]{16,40}", token):
            raise HTTPException(404, "no such order")
        with db._db() as c:
            row = c.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
        d = json.loads(row["data"]) if row else {}
        dealer = d.get("dealer") or {}
        if row is None or dealer.get("mode") != "ours":
            raise HTTPException(404, "no such order")
        site = db.by_id(int(dealer["site_id"]))
        lang = d.get("lang") or site["settings"]["lang"]
        t = texts(lang, site["settings"]["texts"])
        said = t[STATUS_SHOWN.get(row["status"], "status_other")]
        thanks = (
            site["settings"]["texts"].get(lang, {}).get("thanks")
            if row["status"] in ("paid", "waiting_production")
            else None
        )
        back = ""
        ret = site["settings"]["return_url"]
        if (
            ret
            and norm_origin(f"{urlparse(ret).scheme}://{urlparse(ret).netloc}") in site["domains"]
        ):
            back = (
                f'<a class="button" href="{esc(ret)}">'
                f"{esc(t['back_to'].replace('{dealer}', dealer.get('company') or ''))}</a>"
            )
        body = (
            f'<h1>{esc(t["status_title"])}</h1><div class="card">'
            f"<p><strong>{esc(t['order_n'].replace('{n}', str(row['id'])))}</strong></p>"
            f"<p>{esc(thanks or said)}</p><p>{esc(t['total'])}: EUR {row['total_eur']:.2f}</p>"
            f"</div>{back}"
        )
        return page(site["settings"]["theme"], lang, t["status_title"], body)

    def dealer_order_row(token: str) -> dict[str, Any]:
        if not TOKEN.match(token or ""):
            raise HTTPException(404, "no such order")
        with db._db() as c:
            row = c.execute("SELECT * FROM dealer_orders WHERE token=?", (token,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such order")
        return dict(row)

    def confirm_body(
        row: dict[str, Any], site: dict[str, Any], t: dict[str, str], msg: str = ""
    ) -> str:
        rec = json.loads((quotes / f"{row['quote_id']}.json").read_text(encoding="utf-8"))
        c = json.loads(row["customer"])
        days = float(limits()["limits.embed_confirm_days"])
        open_ = row["status"] == "sent" and row["created"] + days * DAY_S > time.time()
        buttons = (
            f'<form method="post"><button name="action" value="confirm">'
            f'{esc(t["confirm_button"])}</button> <button class="secondary" name="action" '
            f'value="decline">{esc(t["decline_button"])}</button></form>'
            if open_
            else ""
        )
        state = {
            "confirmed": t["confirmed"].replace("{n}", str(row.get("b2b_order") or "")),
            "declined": t["declined"],
        }.get(row["status"], "")
        if row["status"] == "sent" and not open_:
            state = t["expired"]
        head = f"<h1>{esc(t['confirm_title'])} D{row['id']}</h1>" + (
            f"<p><strong>{esc(msg or state)}</strong></p>" if (msg or state) else ""
        )
        if not open_:  # decided or expired: the link shows no customer and no price any more
            return head
        # the purchase price is only in the dealer's mail, never on a page a link opens
        # (Codex, round 1: a forwarded link must not reveal it)
        return (
            head + f'<div class="card"><p>{esc(describe(rec))}</p>'
            f"<p>{esc(t['customer_price'])}: EUR {row['price_eur']:.2f}</p>"
            f"<p>{esc(c['name'])} &lt;{esc(c['email'])}&gt; {esc(c.get('phone'))}<br>"
            f"{esc(c.get('street'))}, {esc(c.get('postcode'))} {esc(c.get('city'))}, "
            f"{esc(c.get('country'))}<br>{esc(c.get('note'))}</p></div>{buttons}"
        )

    @app.get("/embed/v1/confirm/{token}", include_in_schema=False)
    def confirm_page(token: str, request: Request) -> HTMLResponse:
        if not embed_on(request):
            raise HTTPException(404, "not here")
        row = dealer_order_row(token)
        site = db.by_id(int(row["site_id"]))
        t = texts(site["settings"]["lang"], {})
        return page(
            site["settings"]["theme"],
            site["settings"]["lang"],
            t["confirm_title"],
            confirm_body(row, site, t),
        )

    @app.post("/embed/v1/confirm/{token}", include_in_schema=False)
    async def confirm_post(token: str, request: Request) -> HTMLResponse:
        if not embed_on(request):
            raise HTTPException(404, "not here")
        origin = request.headers.get("origin")
        if origin is not None and norm_origin(origin) != norm_origin(site_base(request)):
            raise HTTPException(403, "request from another site")
        window(f"c:{visitor(request)}", int(limits()["limits.embed_per_minute"]), MINUTE_S)
        row = dealer_order_row(token)
        site = db.by_id(int(row["site_id"]))
        t = texts(site["settings"]["lang"], {})
        action = str((await request.form()).get("action") or "")
        days = float(limits()["limits.embed_confirm_days"])
        if action not in ("confirm", "decline"):
            raise HTTPException(400, "confirm or decline")
        if row["status"] == "sent" and row["created"] + days * DAY_S > time.time():
            row = decide(int(row["id"]), action, f"dealer:{site['company_id']}")
        return page(
            site["settings"]["theme"],
            site["settings"]["lang"],
            t["confirm_title"],
            confirm_body(row, site, t),
        )

    # ---- the admin: Shop → Dealer embeds ------------------------------------------------------
    def admin_doc(request: Request) -> dict[str, Any]:
        p = shop_params(auth)
        ps = prices.current(auth)
        opts = q.options(p, True)
        companies = {c["id"]: c for c in app.state.b2b.companies()}
        s = shop_settings()
        dom = str(s.get("domain") or "").removeprefix("https://").strip("/")
        sites = []
        for site in db.sites():
            c = companies.get(site["company_id"]) or {}
            sites.append(
                {
                    **{
                        k: site[k]
                        for k in (
                            "id",
                            "name",
                            "public_key",
                            "secret_shown",
                            "domains",
                            "settings",
                            "active",
                            "created",
                            "company_id",
                        )
                    },
                    "company": c.get("name"),
                    "company_status": c.get("status"),
                    "company_price_list": c.get("price_list"),
                    "usage": db.usage(int(site["id"])),
                    "orders": dealer_orders(int(site["id"])),
                }
            )
        return {
            "enabled_on_live": bool(s.get("dealer_embed_enabled")),
            "sites": sites,
            "companies": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "status": c["status"],
                    "price_list": c["price_list"],
                }
                for c in companies.values()
            ],
            "channels": {k: v.get("name", k) for k, v in ps["channels"].items()},
            "products": {k: v["label"] for k, v in opts["products"].items()},
            "colours": q.colours(p),
            "languages": list(LANGS),
            "roundings": list(ROUNDINGS),
            "defaults": SITE_DEFAULTS,
            "website": f"https://{dom}" if dom else site_base(request),
            "preview": f"https://preview.{dom.split('.', 1)[1]}" if "." in dom else None,
        }

    def dealer_orders(sid: int) -> list[dict[str, Any]]:
        with db._db() as c:
            rows = c.execute(
                "SELECT id, created, status, price_eur, purchase_eur, b2b_order, "
                "customer FROM dealer_orders WHERE site_id=? ORDER BY id DESC "
                "LIMIT 20",
                (sid,),
            ).fetchall()
        out = []
        for r in rows:
            cust = json.loads(r["customer"])
            out.append(
                {
                    **{
                        k: r[k]
                        for k in (
                            "id",
                            "created",
                            "status",
                            "price_eur",
                            "purchase_eur",
                            "b2b_order",
                        )
                    },
                    "customer": f"{cust.get('name')} ({cust.get('city')})",
                }
            )
        return out

    def checked(
        site: dict[str, Any], settings: dict[str, Any], domains: list[str]
    ) -> dict[str, Any]:
        p = shop_params(auth)
        company = app.state.b2b.company(int(site["company_id"]))
        try:
            return clean_settings(
                settings,
                prices.current(auth)["channels"],
                company,
                set(q.options(p, True)["products"]),
                q.colours(p),
                domains,
            )
        except SettingsError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/admin/embeds")
    def admin_list(request: Request) -> dict[str, Any]:
        require(request, "admin")
        return admin_doc(request)

    @app.post("/api/admin/embeds")
    def admin_add(req: NewSiteIn, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        app.state.b2b.company(req.company_id)  # 404 when there is none
        sid = db.add(req.company_id, req.name.strip())
        auth.log(admin, "dealer embed made", {"id": sid, "company": req.company_id})
        return {**admin_doc(request), "made": sid}

    @app.put("/api/admin/embeds/{sid}")
    def admin_change(sid: int, req: SiteChangeIn, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        site = db.by_id(sid)
        cols: dict[str, Any] = {}
        domains = site["domains"]
        if req.domains is not None:
            domains = []
            for d in req.domains:
                if not str(d).strip():
                    continue
                o = norm_origin(d)
                if o is None:
                    raise HTTPException(400, f"{d!r} is not a website address (https://…)")
                if o not in domains:
                    domains.append(o)
            if len(domains) > MAX_DOMAINS:
                raise HTTPException(400, f"at most {MAX_DOMAINS} domains")
            cols["domains"] = domains
        if req.settings is not None or req.domains is not None:
            raw = req.settings if req.settings is not None else site["settings"]
            cols["settings"] = checked(site, raw, domains)
        if req.name is not None:
            cols["name"] = req.name.strip()
        if req.active is not None:
            cols["active"] = req.active
        if cols:
            db.change(sid, cols)
            auth.log(admin, "dealer embed changed", {"id": sid, "fields": sorted(cols)})
        return admin_doc(request)

    @app.post("/api/admin/embeds/{sid}/secret")
    def admin_secret(sid: int, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        db.by_id(sid)
        secret = SECRET_PREFIX + secrets.token_urlsafe(32)
        db.change(sid, {"secret_hash": _h(secret), "secret_shown": secret[:8] + "…"})
        auth.log(admin, "dealer embed secret made", {"id": sid})
        return {"secret": secret, "note": "shown once: give it to the dealer for its server"}

    @app.get("/api/admin/embeds/{sid}/example")
    def admin_example(sid: int, request: Request, product: str = "sofa") -> dict[str, Any]:
        """What the dealer buys at and what its customer sees, for the default sizes (admins
        only: the purchase price never leaves the studio otherwise)."""
        require(request, "admin")
        site = db.by_id(sid)
        p = shop_params(auth)
        opts = q.options(p, True)["products"]
        if product not in opts:
            raise HTTPException(400, "unknown product")
        sizes = {f["key"]: f["default"] for f in opts[product]["fields"]}
        ps = prices.current(auth)
        full = q.proposal(product, {**sizes, "vents": True, "colour": None}, p, ps)
        price = dealer_price(
            ps,
            app.state.b2b.company(int(site["company_id"])),
            full["price"]["costing"]["channels"],
            site["settings"]["pricing"],
            product,
            "none",
            1,
        )
        return {"product": product, "sizes_cm": full["sizes_cm"], **price}

    return None


def snippet(website: str, key: str, lang: str = "nl") -> dict[str, str]:
    """The copy-paste snippets (also built in the studio page)."""
    q = urlencode({"dealer": key, "lang": lang})
    return {
        "script": (
            f'<script type="module" src="{website}/embed/v1/configurator.js"></script>\n'
            f'<s2dio-configurator dealer="{key}" lang="{lang}"></s2dio-configurator>'
        ),
        "iframe": (
            f'<iframe src="{website}/embed/v1/frame?{q}" title="Cover configurator" '
            'style="width:100%;height:900px;border:0" loading="lazy" '
            'sandbox="allow-scripts allow-same-origin allow-forms allow-popups '
            'allow-popups-to-escape-sandbox"></iframe>'
        ),
    }
