"""The cover webshop's back end (ADR-062, docs/plans/cover-webshop.md): its settings, the
site's content with the AI CMS (draft, preview, live, history), the configurator's proposals
with the rain check, orders with Mollie payments, and an order's way into production.

Everything the owner has not given yet is a setting on the admin page (Shop settings). Empty
settings show as placeholders in the shop, and payments work as soon as a Mollie key is set.
"""

from __future__ import annotations

import copy
import json
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

SHOP_SETTING = "shop"
PREVIEW_SETTING = "shop_preview_token"
MOLLIE_API = "https://api.mollie.com/v2"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Every setting the shop needs; empty means "still to fill in" (the admin page shows them).
SHOP_DEFAULTS: dict[str, Any] = {
    "company": {
        "name": "",
        "legal_name": "",
        "kvk": "",
        "vat_number": "",
        "street": "",
        "postcode": "",
        "city": "",
        "country": "NL",
        "email": "",
        "phone": "",
        "iban": "",
    },  # fmt: skip
    "domain": "",
    "prices": {
        "confirmed": False,
        "fabric_eur_per_m": None,
        "labour_eur_per_hour": None,
        "vent_eur": None,
        "cord_eur_per_m": None,
        "balloon_eur": None,
        "frame_eur": None,
        "markup_pct": None,
        "vat_pct": None,
    },  # fmt: skip
    "shipping": [
        {"country": "NL", "name": "Netherlands", "eur": None},
        {"country": "BE", "name": "Belgium", "eur": None},
        {"country": "DE", "name": "Germany", "eur": None},
    ],
    "payment": {"mollie_key": "", "bank_transfer": True},
    "products": {
        "balloon": {"name": "Support balloon", "size": "", "photo": ""},
        "frame": {"name": "Cover frame", "size": "", "photo": ""},
    },  # fmt: skip
    "colours": "",
    "film_url": "",
    "notify_email": "",
}

# The site's text, NL and EN; the AI CMS edits this (draft), a person publishes it (live).
CONTENT_DEFAULTS: dict[str, Any] = {
    "meta": {
        "title": {
            "nl": "Hoezen op maat voor je tuinmeubels",
            "en": "Made-to-measure covers for your garden furniture",
        },
        "description": {
            "nl": "Ontwerp in een paar minuten je eigen hoes op maat: geef de maten, "
            "zie hem in 3D, zie waar de regen heen loopt, en bestel.",
            "en": "Design your own made-to-measure cover in minutes: give the sizes, "
            "see it in 3D, see where the rain goes, and order.",
        },
    },
    "hero": {
        "title": {"nl": "Jouw hoes. Precies op maat.", "en": "Your cover. Made to measure."},
        "subtitle": {
            "nl": "Vul de maten in, zie je hoes in 3D en zie waar de regen naartoe "
            "loopt. Wij snijden en naaien hem voor je.",
            "en": "Fill in the sizes, see your cover in 3D and where the rain runs. "
            "We cut and sew it for you.",
        },
        "cta": {"nl": "Ontwerp je hoes", "en": "Design your cover"},
    },
    "steps": [
        {
            "title": {"nl": "Maten invullen", "en": "Give the sizes"},
            "text": {
                "nl": "Een paar grove maten van je set zijn genoeg.",
                "en": "A few rough sizes of your set are enough.",
            },
        },
        {
            "title": {"nl": "Zien in 3D", "en": "See it in 3D"},
            "text": {
                "nl": "Je hoes over je meubels, met de regen erop: je ziet of het water afloopt.",
                "en": "Your cover over your furniture, with the rain on it: you see that the "
                "water runs off.",
            },
        },
        {
            "title": {"nl": "Op maat gesneden", "en": "Cut to measure"},
            "text": {
                "nl": "Onze software maakt het patroon, de snijtafel snijdt het met weinig afval.",
                "en": "Our software makes the pattern; the cutting table cuts it with little "
                "waste.",
            },
        },
        {
            "title": {"nl": "Genaaid en bezorgd", "en": "Sewn and delivered"},
            "text": {
                "nl": "In onze werkplaats genaaid en bij je thuis bezorgd.",
                "en": "Sewn in our workshop and delivered to your door.",
            },
        },
    ],
    "green": {
        "title": {"nl": "Zo groen werken we", "en": "How green we work"},
        "points": [
            {
                "nl": "Alleen op bestelling gemaakt: geen voorraad, geen overproductie.",
                "en": "Made only to order: no stock, no overproduction.",
            },
            {
                "nl": "De snijtafel legt de stukken zo dat er zo min mogelijk stof overblijft.",
                "en": "The cutting table lays the pieces so as little fabric as possible is left.",
            },
            {
                "nl": "Duurzame, PFAS-vrije stof die jaren meegaat.",
                "en": "Durable, PFAS-free fabric that lasts for years.",
            },
            {"nl": "Lokaal gemaakt, en te repareren.", "en": "Made locally, and repairable."},
        ],
    },
    "faq": [
        {
            "q": {
                "nl": "Hoe nauwkeurig moeten mijn maten zijn?",
                "en": "How exact must my sizes be?",
            },
            "a": {
                "nl": "Grove maten op de centimeter zijn genoeg: wij geven de hoes een paar "
                "centimeter ruimte.",
                "en": "Rough sizes to the centimetre are enough: we give the cover a few "
                "centimetres of room.",
            },
        },
        {
            "q": {
                "nl": "Waarom ballonnen onder een tafelhoes?",
                "en": "Why balloons under a table cover?",
            },
            "a": {
                "nl": "Op een vlakke tafel blijft regen staan. Een ballon tilt het midden op, "
                "zodat het water afloopt. De configurator laat het zien.",
                "en": "Rain stays on a flat table. A balloon lifts the middle so the water runs "
                "off. The configurator shows it.",
            },
        },
        {
            "q": {
                "nl": "Kan ik een hoes op maat terugsturen?",
                "en": "Can I return a made-to-measure cover?",
            },
            "a": {
                "nl": "Een hoes op maat wordt speciaal voor jou gemaakt; daarom geldt het "
                "herroepingsrecht niet. Past hij niet door onze fout, dan maken we hem "
                "opnieuw.",
                "en": "A made-to-measure cover is made for you alone, so the right of "
                "withdrawal does not apply. If it does not fit through our mistake, we "
                "make it again.",
            },
        },
    ],
    "legal": {
        "terms": {"nl": "", "en": ""},
        "privacy": {"nl": "", "en": ""},
        "warranty": {"nl": "", "en": ""},
    },
}

CMS_SYSTEM = """You edit the content of a webshop for made-to-measure outdoor furniture covers.
You get the current content (JSON, with Dutch "nl" and English "en" texts) and a colleague's
instruction. Change only what the instruction asks; keep both languages in step (translate);
keep the tone: clear, warm, short sentences, no hype. Never invent facts (prices, guarantees,
certificates, numbers) that are not in the content or the instruction. Answer with JSON only:
{"changes": [{"path": "hero.title.nl", "value": "..."}, ...], "summary": "one sentence"}
Paths use dots and list indexes (faq.0.q.en). To add a list item give the next index; to remove
one give the value null. Search engines and AI assistants read this site: keep facts precise and
answers self-contained."""


class CmsCommand(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class ShopQuote(BaseModel):
    product: str = Field(max_length=40)
    sizes: dict[str, Any] = Field(default_factory=dict)
    colour: str | None = Field(default=None, max_length=40)
    vents: bool = True
    support: str = Field(default="none", pattern=r"^(none|balloons|frame)$")


class OrderIn(BaseModel):
    quote_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    street: str = Field(min_length=1, max_length=160)
    postcode: str = Field(min_length=1, max_length=20)
    city: str = Field(min_length=1, max_length=80)
    country: str = Field(min_length=2, max_length=2)
    note: str | None = Field(default=None, max_length=2000)
    terms: bool


ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL NOT NULL,
  token TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  email TEXT NOT NULL,
  data TEXT NOT NULL,
  total_eur REAL NOT NULL,
  mollie_id TEXT,
  model_id TEXT,
  updated REAL
)"""
STATUSES = ("awaiting_payment", "paid", "in_production", "sewn", "shipped", "cancelled", "failed")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.I)


def merged(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merged(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def set_path(doc: Any, path: str, value: Any) -> None:
    """Set doc[path] for a dotted path with list indexes; None removes a list item."""
    keys = path.split(".")
    cur = doc
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur.setdefault(k, {})
    last = keys[-1]
    if isinstance(cur, list):
        i = int(last)
        if value is None:
            if i < len(cur):
                cur.pop(i)
        elif i == len(cur):
            cur.append(value)
        else:
            cur[i] = value
    else:
        if value is None:
            cur.pop(last, None)
        else:
            cur[last] = value


class Site:
    """The site's content: draft.json (edited), live.json (shown), history/ (every publish)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "history").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        for name in ("draft", "live"):
            if not (root / f"{name}.json").is_file():
                self._write(name, CONTENT_DEFAULTS)

    def _write(self, name: str, doc: dict[str, Any]) -> None:
        tmp = self.root / f"{name}.tmp"
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / f"{name}.json")

    def read(self, name: str) -> dict[str, Any]:
        doc: dict[str, Any] = json.loads((self.root / f"{name}.json").read_text(encoding="utf-8"))
        return merged(CONTENT_DEFAULTS, doc)

    def change(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            doc = self.read("draft")
            for c in changes:
                set_path(doc, str(c["path"]), c.get("value"))
            self._write("draft", doc)
            return doc

    def publish(self, who: str) -> str:
        with self._lock:
            live = self.read("live")
            stamp = time.strftime("%Y%m%d-%H%M%S")
            (self.root / "history" / f"{stamp}.json").write_text(
                json.dumps({"by": who, "content": live}, ensure_ascii=False), encoding="utf-8"
            )
            self._write("live", self.read("draft"))
            return stamp

    def discard(self) -> None:
        with self._lock:
            self._write("draft", self.read("live"))

    def history(self) -> list[str]:
        return sorted((p.stem for p in (self.root / "history").glob("*.json")), reverse=True)

    def restore(self, stamp: str) -> None:
        if not re.fullmatch(r"\d{8}-\d{6}", stamp):
            raise ValueError("no such version")
        doc = json.loads((self.root / "history" / f"{stamp}.json").read_text(encoding="utf-8"))
        with self._lock:
            self._write("draft", doc["content"])


def cms_apply(site: Site, params: Any, text: str) -> dict[str, Any]:
    """The AI turns a colleague's instruction into changes of the draft (used by the admin
    page and by the command line `cover-site`)."""
    from coverengine.ai import ask

    draft = site.read("draft")
    ans = ask(params, CMS_SYSTEM, json.dumps({"content": draft, "instruction": text},
                                             ensure_ascii=False))  # fmt: skip
    changes = [c for c in ans.get("changes", []) if isinstance(c, dict) and "path" in c]
    if not changes:
        return {"summary": ans.get("summary") or "nothing to change", "changes": []}
    for c in changes:  # only the content's own keys, no new top-level sections
        if str(c["path"]).split(".")[0] not in CONTENT_DEFAULTS:
            raise ValueError(f"the AI wanted to change {c['path']}, which is not part of the site")
    site.change(changes)
    return {"summary": ans.get("summary", ""), "changes": changes}


def shop_params(auth: Any) -> Any:
    """The engine's parameters with the owner's shop prices on top (when set)."""
    from coverengine.params import Registry

    s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
    trial: dict[str, Any] = {}
    for k, v in s["prices"].items():
        if k != "confirmed" and v not in (None, ""):
            trial[f"quote.{k}"] = float(v)
    if s["prices"].get("confirmed"):
        trial["quote.prices_are_placeholders"] = False
    if s.get("colours"):
        trial["quote.colours"] = s["colours"]
    return Registry.load(None).resolve(trial=trial)


def install(app: FastAPI, auth: Any, data: Path, jobs: Any, store: Any) -> None:
    from coverengine import quote as q
    from coverengine.errors import CoverError

    from coverapi import mailer
    from coverapi.security import _address, require

    site = Site(data / "site")
    quotes = data / "shop_quotes"
    quotes.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(auth.path) as db:
        db.execute(ORDERS_TABLE)
    app.state.site = site
    recent: dict[str, list[float]] = {}

    def limit(request: Request, per_minute: int = 40) -> None:
        a, now = _address(request), time.time()
        times = [t for t in recent.get(a, []) if now - t < 60]  # noqa: PLR2004 - a minute
        if len(times) >= per_minute:
            raise HTTPException(429, "too many requests; try again in a minute")
        recent[a] = [*times, now]

    def settings() -> dict[str, Any]:
        return merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})

    def notify(subject: str, text: str, to: str | None = None) -> None:
        s = settings()
        target = to or s["notify_email"] or "rick@s2dio.industries"
        if mailer.configured(auth):
            try:
                mailer.send(auth, target, subject, text)
            except Exception:  # noqa: BLE001 - a mail must never stop an order
                pass

    # ---- settings (admin) -------------------------------------------------------------------
    @app.get("/api/admin/shop/settings")
    def get_settings(request: Request) -> dict[str, Any]:
        require(request, "admin")
        s = settings()
        key = s["payment"].get("mollie_key") or ""
        s["payment"]["mollie_key"] = (key[:5] + "…" + key[-4:]) if key else ""  # never in full
        missing = [k for k, v in s["company"].items() if not v] + [
            k for k, v in s["prices"].items() if v in (None, "")
        ]  # fmt: skip
        return {"settings": s, "missing": missing, "defaults": SHOP_DEFAULTS}

    @app.put("/api/admin/shop/settings")
    async def put_settings(request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "settings: a JSON object")
        cur = auth.setting(SHOP_SETTING, {}) or {}
        new = merged(cur, {k: v for k, v in body.items() if k in SHOP_DEFAULTS})
        key = (body.get("payment") or {}).get("mollie_key") or ""
        if "…" in key:  # the masked value came back unchanged: keep the stored key
            new["payment"]["mollie_key"] = (cur.get("payment") or {}).get("mollie_key", "")
        auth.set_setting(SHOP_SETTING, new)
        auth.log(admin, "shop settings", {k: "…" for k in body})
        return get_settings(request)

    # ---- the content and the AI CMS (admin) -------------------------------------------------
    @app.get("/api/admin/cms")
    def cms_state(request: Request) -> dict[str, Any]:
        require(request, "edit")
        token = auth.setting(PREVIEW_SETTING, None)
        if not token:
            token = secrets.token_urlsafe(16)
            auth.set_setting(PREVIEW_SETTING, token)
        return {"draft": site.read("draft"), "live": site.read("live"),
                "history": site.history()[:30], "preview": f"/shop/?preview={token}"}  # fmt: skip

    @app.post("/api/admin/cms/command")
    def cms_command(req: CmsCommand, request: Request) -> dict[str, Any]:
        user = require(request, "edit")
        try:
            out = cms_apply(site, shop_params(auth), req.text)
        except (ValueError, CoverError) as exc:
            raise HTTPException(400, str(exc)) from None
        auth.log(user, "site draft", {"instruction": req.text, "summary": out["summary"]})
        return out

    @app.post("/api/admin/cms/publish")
    def cms_publish(request: Request) -> dict[str, Any]:
        user = require(request, "admin")
        stamp = site.publish(user.username)
        auth.log(user, "site published", {"previous": stamp})
        return {"published": True, "previous_version": stamp}

    @app.post("/api/admin/cms/discard")
    def cms_discard(request: Request) -> dict[str, Any]:
        require(request, "edit")
        site.discard()
        return {"draft": site.read("draft")}

    @app.post("/api/admin/cms/restore/{stamp}")
    def cms_restore(stamp: str, request: Request) -> dict[str, Any]:
        require(request, "admin")
        try:
            site.restore(stamp)
        except (ValueError, OSError):
            raise HTTPException(404, "no such version") from None
        return {"draft": site.read("draft")}

    # ---- the shop (public) ------------------------------------------------------------------
    def public_settings() -> dict[str, Any]:
        s = settings()
        p = shop_params(auth)
        return {
            "company": {k: s["company"][k] for k in ("name", "email", "phone", "city", "country")},
            "shipping": [x for x in s["shipping"] if x.get("eur") is not None]
            or [{"country": x["country"], "name": x["name"], "eur": 0} for x in s["shipping"]],
            "payment": bool(s["payment"].get("mollie_key")),
            "film_url": s["film_url"],
            "colours": q.colours(p),
            "products": s["products"],
            "indicative": bool(p["quote.prices_are_placeholders"]),
        }

    @app.get("/api/shop/info")
    def shop_info(request: Request) -> dict[str, Any]:
        token = request.query_params.get("preview")
        draft = token and secrets.compare_digest(token, auth.setting(PREVIEW_SETTING, "") or "x")
        return {"content": site.read("draft" if draft else "live"), "preview": bool(draft),
                "settings": public_settings(), "options": q.options(shop_params(auth))}  # fmt: skip

    def _quote(req: ShopQuote) -> dict[str, Any]:
        p = shop_params(auth)
        given = {**req.sizes, "vents": req.vents, "colour": req.colour}
        try:
            full = q.proposal(req.product, given, p)
            rain = q.rain_check(req.product, given, p)
            glb = q.scene_glb(req.product, given, p, req.support)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        extra = 0.0
        markup = 1 + float(p["quote.markup_pct"]) / 100  # noqa: PLR2004 - percent
        vat = 1 + float(p["quote.vat_pct"]) / 100  # noqa: PLR2004 - percent
        if req.support == "balloons":
            extra = full["balloons"] * float(p["quote.balloon_eur"]) * markup * vat
        elif req.support == "frame":
            extra = float(p["quote.frame_eur"]) * markup * vat
        qid = q.new_id()
        for support, r in rain["options"].items():  # the water in 3D, per support
            water = r.pop("_water_glb", None)
            r["water"] = f"/api/shop/scene/{qid}-{support}.glb" if water else None
            if water:
                (quotes / f"{qid}-{support}.glb").write_bytes(water)
        record = {"time": time.time(), "input": req.model_dump(), "quote": full, "rain": rain,
                  "support_eur": round(extra, 2)}  # fmt: skip
        (quotes / f"{qid}.json").write_text(json.dumps(record), encoding="utf-8")
        (quotes / f"{qid}.glb").write_bytes(glb)
        return {
            "id": qid, "product": full["product"], "pieces": len(full["pieces"]),
            "cover_area_m2": full["cover_area_m2"], "fabric_m2": full["fabric_m2"],
            "vents": full["vents"], "balloons": full["balloons"], "colour": full["colour"],
            "sizes_cm": full["sizes_cm"], "support": req.support,
            "price": {"cover_eur": full["price"]["sale_eur"], "support_eur": round(extra, 2),
                      "total_eur": round(full["price"]["sale_eur"] + extra, 2),
                      "indicative": full["price"]["placeholder_prices"]},
            "rain": rain, "near": q.nearest(req.product, given, store.models)[:1],
            "scene": f"/api/shop/scene/{qid}.glb",
        }  # fmt: skip

    @app.post("/api/shop/quote")
    def shop_quote(req: ShopQuote, request: Request) -> dict[str, Any]:
        limit(request)
        return _quote(req)

    @app.get("/api/shop/scene/{qid}.glb")
    def shop_scene(qid: str) -> Response:
        if (
            not re.fullmatch(r"[0-9a-f]{16}(-(none|balloons|frame))?", qid)
            or not (quotes / f"{qid}.glb").is_file()
        ):
            raise HTTPException(404, "no such scene")
        return Response((quotes / f"{qid}.glb").read_bytes(), media_type="model/gltf-binary")

    def mollie(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        key = settings()["payment"].get("mollie_key") or ""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{MOLLIE_API}{path}", data=data, method=method, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})  # fmt: skip
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - Mollie's https API
            doc: dict[str, Any] = json.loads(r.read())
            return doc

    def base_url(request: Request) -> str:
        s = settings()
        if s["domain"]:
            return "https://" + s["domain"].removeprefix("https://").rstrip("/")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        return f"{scheme}://{host}"

    @app.post("/api/shop/order")
    def shop_order(req: OrderIn, request: Request) -> dict[str, Any]:
        limit(request, per_minute=10)
        if not req.terms:
            raise HTTPException(400, "please accept the terms")
        if not EMAIL.match(req.email.strip()):
            raise HTTPException(400, "please give a valid e-mail address")
        path = quotes / f"{req.quote_id}.json"
        if not path.is_file():
            raise HTTPException(404, "the proposal has expired; please make it again")
        record = json.loads(path.read_text(encoding="utf-8"))
        ship = next(
            (x for x in settings()["shipping"] if x["country"] == req.country.upper()), None
        )
        if ship is None:
            raise HTTPException(400, "we do not deliver to this country yet")
        shipping = float(ship.get("eur") or 0)
        total = round(record["quote"]["price"]["sale_eur"] + record["support_eur"] + shipping, 2)
        token = secrets.token_urlsafe(18)
        data = {"customer": req.model_dump(), "quote": record, "shipping_eur": shipping}
        with sqlite3.connect(auth.path) as db:
            cur = db.execute(
                "INSERT INTO orders (created, token, status, email, data, total_eur, updated) "
                "VALUES (?, ?, 'awaiting_payment', ?, ?, ?, ?)",
                (time.time(), token, req.email.strip(), json.dumps(data), total, time.time()),
            )
            oid = cur.lastrowid
        status_url = f"{base_url(request)}/shop/order/{token}"
        checkout = None
        if settings()["payment"].get("mollie_key"):
            try:
                pay = mollie("POST", "/payments", {
                    "amount": {"currency": "EUR", "value": f"{total:.2f}"},
                    "description": f"Cover order {oid}",
                    "redirectUrl": status_url,
                    "webhookUrl": f"{base_url(request)}/api/shop/mollie",
                    "metadata": {"order": oid},
                })  # fmt: skip
                checkout = pay["_links"]["checkout"]["href"]
                with sqlite3.connect(auth.path) as db:
                    db.execute("UPDATE orders SET mollie_id=? WHERE id=?", (pay["id"], oid))
            except Exception as exc:  # noqa: BLE001 - the order stays; payment can follow
                notify(f"Order {oid}: Mollie refused the payment", str(exc))
        notify(f"New order {oid}: EUR {total}", f"{req.name} <{req.email}>\n{status_url}\n"
               f"{json.dumps(record['quote']['sizes_cm'])}\n(admin page, Orders)")  # fmt: skip
        return {"order": oid, "status_url": status_url, "checkout_url": checkout,
                "total_eur": total, "status": "awaiting_payment"}  # fmt: skip

    @app.get("/api/shop/order/{token}")
    def shop_order_status(token: str) -> dict[str, Any]:
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such order")
        d = json.loads(row["data"])
        return {"order": row["id"], "status": row["status"], "total_eur": row["total_eur"],
                "created": row["created"], "product": d["quote"]["quote"]["product"],
                "colour": d["quote"]["quote"]["colour"]}  # fmt: skip

    @app.post("/api/shop/mollie")
    async def mollie_webhook(request: Request) -> dict[str, Any]:
        form = await request.form()
        pid = str(form.get("id") or "")
        if not re.fullmatch(r"tr_[A-Za-z0-9]{4,40}", pid):
            raise HTTPException(400, "no payment id")
        pay = mollie("GET", f"/payments/{pid}")  # never trust the webhook: ask Mollie
        status = {"paid": "paid", "failed": "failed", "canceled": "cancelled",
                  "expired": "cancelled"}.get(pay.get("status", ""), None)  # fmt: skip
        if status:
            with sqlite3.connect(auth.path) as db:
                db.execute("UPDATE orders SET status=?, updated=? WHERE mollie_id=? "
                           "AND status='awaiting_payment'", (status, time.time(), pid))  # fmt: skip
                row = db.execute("SELECT id FROM orders WHERE mollie_id=?", (pid,)).fetchone()
            if status == "paid" and row:
                produce(int(row[0]))
        return {"ok": True}

    # ---- orders (admin) and the way into production ------------------------------------------
    def produce(oid: int) -> str:
        """The paid order as a cover model, calculated to the end (then the drape follows)."""
        from coverengine import drawn
        from coverengine.catalogue import set_info
        from coverengine.cli import main as cover
        from coverengine.io.kind import confirm

        from coverapi.jobs import JobSpec

        with sqlite3.connect(auth.path) as db:
            row = db.execute("SELECT data, model_id FROM orders WHERE id=?", (oid,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such order")
        if row[1]:
            return str(row[1])
        d = json.loads(row[0])
        qd = d["quote"]["quote"]
        p = shop_params(auth)
        roll = float(p["roll.usable_width_mm"]) - 2 * float(p["stitching.allowance_mm"])
        pieces = drawn.build(qd["shape"], qd["sizes_cm"], roll)
        model_id = f"order-{oid}"
        model = store.models / model_id
        src = store.uploads / model_id / "cover.glb"
        src.parent.mkdir(parents=True, exist_ok=True)
        drawn.scene(pieces).export(src)
        if cover(["import", str(src), "--out", str(model), "--units", "mm", "--up", "z"]):
            raise HTTPException(500, "the order's cover could not be made")
        confirm(model, "cover")
        if qd["product"] in ("dining_set", "round_set"):
            doc = json.loads((model / "cover.json").read_text())
            doc.setdefault("parameters", {}).setdefault("features", {})["middle_cord"] = True
            (model / "cover.json").write_text(json.dumps(doc, indent=2) + "\n")
        c = d["customer"]
        sizes = ", ".join(f"{k} {v}" for k, v in qd["sizes_cm"].items())
        support = d["quote"]["input"]["support"]
        notes = (f"Shop order {oid}: {c['name']} ({c['city']}), {qd['product']} {sizes}, "
                 f"{qd['colour']}, support {support}")  # fmt: skip
        set_info(model, {"status": "draft", "tags": ["order", "shop"], "notes": notes})
        jobs.submit(JobSpec(model_id, ["hull", "cut", "flatten", "export"], {}))
        with sqlite3.connect(auth.path) as db:
            db.execute("UPDATE orders SET model_id=?, status='in_production', updated=? "
                       "WHERE id=?", (model_id, time.time(), oid))  # fmt: skip
        return model_id

    @app.get("/api/admin/orders")
    def orders(request: Request) -> dict[str, Any]:
        require(request, "edit")
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 300")]
        for r in rows:
            r["data"] = json.loads(r["data"])
        return {"orders": rows, "statuses": list(STATUSES)}

    @app.put("/api/admin/orders/{oid}")
    def change_order(oid: int, request: Request, req: dict[str, Any]) -> dict[str, Any]:
        user = require(request, "edit")
        status = str(req.get("status", ""))
        if status not in STATUSES:
            raise HTTPException(400, f"status: one of {', '.join(STATUSES)}")
        with sqlite3.connect(auth.path) as db:
            db.execute(
                "UPDATE orders SET status=?, updated=? WHERE id=?", (status, time.time(), oid)
            )
            row = db.execute("SELECT email, token FROM orders WHERE id=?", (oid,)).fetchone()
        auth.log(user, "order status", {"order": oid, "status": status})
        if row:
            words = {"paid": "is betaald / is paid",
                     "in_production": "wordt gemaakt / is being made",
                     "sewn": "is genaaid / is sewn", "shipped": "is verzonden / has been shipped",
                     "cancelled": "is geannuleerd / is cancelled"}  # fmt: skip
            if status in words:
                notify(f"Je hoes {words[status]}", f"Bestelling / order {oid}: {words[status]}.\n"
                       f"{base_url(request)}/shop/order/{row[1]}\n", to=row[0])  # fmt: skip
        return {"ok": True}

    @app.post("/api/admin/orders/{oid}/produce")
    def order_produce(oid: int, request: Request) -> dict[str, Any]:
        require(request, "edit")
        return {"model_id": produce(oid)}


# ---- the shop's pages for people, search engines and AI assistants (ADR-062) ------------------


def _esc(s: Any) -> str:
    import html

    return html.escape(str(s or ""), quote=True)


def install_pages(app: FastAPI, auth: Any, web_dir: Path) -> None:
    """/shop/... : shop.html with the content already in it (title, description, JSON-LD, the
    text), so search engines and AI assistants read the site without running JavaScript; plus
    robots.txt, sitemap.xml and llms.txt."""
    from coverengine import quote as q
    from fastapi.responses import HTMLResponse, PlainTextResponse

    template = web_dir / "shop.html"

    def site() -> Site:
        s: Site = app.state.site
        return s

    def lang_of(request: Request) -> str:
        want = request.query_params.get("lang") or request.headers.get("accept-language", "")
        return "nl" if want.lower().startswith("nl") else "en"

    def base(request: Request) -> str:
        s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
        if s["domain"]:
            return "https://" + str(s["domain"]).removeprefix("https://").rstrip("/")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        return f"{scheme}://{host}"

    def render(request: Request, page: str) -> HTMLResponse:
        if not template.is_file():
            raise HTTPException(404, "the shop is not built")
        token = request.query_params.get("preview")
        draft = bool(token) and secrets.compare_digest(
            token or "", auth.setting(PREVIEW_SETTING, "") or "x"
        )
        c = site().read("draft" if draft else "live")
        lang = lang_of(request)
        s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
        company = s["company"]
        url = base(request) + "/shop/" + ("" if page == "home" else page)
        title = c["meta"]["title"][lang]
        if page in ("terms", "privacy", "warranty"):
            title = f"{page.capitalize()} · {title}"
        elif page == "configure":
            title = f"{c['hero']['cta'][lang]} · {title}"
        desc = c["meta"]["description"][lang]
        ld: list[dict[str, Any]] = [
            {"@context": "https://schema.org", "@type": "Organization",
             "name": company["name"] or "Covers", "url": base(request) + "/shop/",
             "email": company["email"] or None, "telephone": company["phone"] or None,
             "address": {"@type": "PostalAddress", "streetAddress": company["street"] or None,
                         "postalCode": company["postcode"] or None,
                         "addressLocality": company["city"] or None,
                         "addressCountry": company["country"] or None}},
            {"@context": "https://schema.org", "@type": "Product",
             "name": c["hero"]["title"][lang], "description": desc,
             "brand": company["name"] or "Covers",
             "material": "Sunbrella Coverlast: polyester with an acrylic coating",
             "offers": {"@type": "AggregateOffer", "priceCurrency": "EUR",
                        "availability": "https://schema.org/MadeToOrder"}},
            {"@context": "https://schema.org", "@type": "HowTo", "name": c["hero"]["cta"][lang],
             "step": [{"@type": "HowToStep", "position": i + 1, "name": st["title"][lang],
                       "text": st["text"][lang]} for i, st in enumerate(c["steps"])]},
            {"@context": "https://schema.org", "@type": "FAQPage",
             "mainEntity": [{"@type": "Question", "name": f["q"][lang],
                             "acceptedAnswer": {"@type": "Answer", "text": f["a"][lang]}}
                            for f in c["faq"]]},
        ]  # fmt: skip
        head = (
            f"<title>{_esc(title)}</title>\n"
            f'<meta name="description" content="{_esc(desc)}" />\n'
            f'<link rel="canonical" href="{_esc(url)}" />\n'
            f'<meta property="og:title" content="{_esc(title)}" />\n'
            f'<meta property="og:description" content="{_esc(desc)}" />\n'
            f'<meta property="og:type" content="website" />\n'
            + ('<meta name="robots" content="noindex" />\n' if draft else "")
            + "".join(
                '<script type="application/ld+json">'
                + json.dumps(x, ensure_ascii=False).replace("</", "<\\/")
                + "</script>\n"
                for x in ld
            )
        )
        if page in ("terms", "privacy", "warranty"):
            body_html = f"<h1>{_esc(page.capitalize())}</h1>" + "".join(
                f"<p>{_esc(p)}</p>" for p in str(c["legal"][page][lang]).split("\n\n") if p
            )
        else:
            body_html = (
                f"<h1>{_esc(c['hero']['title'][lang])}</h1><p>{_esc(c['hero']['subtitle'][lang])}</p>"
                + "<h2>How it works</h2><ol>"
                + "".join(
                    f"<li><h3>{_esc(st['title'][lang])}</h3><p>{_esc(st['text'][lang])}</p></li>"
                    for st in c["steps"]
                )  # fmt: skip
                + f"</ol><h2>{_esc(c['green']['title'][lang])}</h2><ul>"
                + "".join(f"<li>{_esc(p[lang])}</li>" for p in c["green"]["points"])
                + "</ul><h2>FAQ</h2>"
                + "".join(
                    f"<h3>{_esc(f['q'][lang])}</h3><p>{_esc(f['a'][lang])}</p>" for f in c["faq"]
                )
                + '<p><a href="/shop/configure">'
                + _esc(c["hero"]["cta"][lang])
                + "</a></p>"
            )
        html = template.read_text(encoding="utf-8")
        html = (
            html.replace("<!--SSR-HEAD-->", head)
            .replace("<!--SSR-BODY-->", f'<main class="ssr">{body_html}</main>')
            .replace('<html lang="nl">', f'<html lang="{lang}">')
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"} if draft else {})

    @app.get("/shop", include_in_schema=False)
    @app.get("/shop/", include_in_schema=False)
    def shop_home(request: Request) -> HTMLResponse:
        return render(request, "home")

    @app.get("/shop/{page:path}", include_in_schema=False)
    def shop_page(page: str, request: Request) -> HTMLResponse:
        page = page.strip("/")
        known = page in ("configure", "terms", "privacy", "warranty") or page.startswith("order/")
        return render(request, page if known else "home")

    @app.get("/api/shop/demo.glb", include_in_schema=False)
    def demo_scene() -> Response:
        """The landing page's 3D: a dining set under its cover with balloons, turning."""
        p = shop_params(auth)
        glb = q.scene_glb(
            "dining_set", {"table_length_cm": 220, "chairs": True}, p, "balloons"
        )  # param-ok
        return Response(
            glb, media_type="model/gltf-binary", headers={"Cache-Control": "max-age=3600"}
        )

    @app.get("/robots.txt", include_in_schema=False)
    def robots(request: Request) -> PlainTextResponse:
        return PlainTextResponse(
            "User-agent: *\nAllow: /shop/\nDisallow: /api/\nDisallow: /#/\n"
            f"Sitemap: {base(request)}/sitemap.xml\n"
        )

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap(request: Request) -> Response:
        b = base(request)
        urls = "".join(f"<url><loc>{b}/shop/{p}</loc></url>"
                       for p in ("", "configure", "terms", "privacy", "warranty"))  # fmt: skip
        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               f'<urlset xmlns="{SITEMAP_NS}">{urls}</urlset>')  # fmt: skip
        return Response(xml, media_type="application/xml")

    @app.get("/llms.txt", include_in_schema=False)
    def llms(request: Request) -> PlainTextResponse:
        """For AI assistants: what this shop is, in plain words, from the live content."""
        c = site().read("live")
        s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
        b = base(request)
        lines = [f"# {s['company']['name'] or 'Covers'}", "",
                 f"> {c['meta']['description']['en']}", "",
                 "## How it works"]  # fmt: skip
        lines += [f"- {st['title']['en']}: {st['text']['en']}" for st in c["steps"]]
        lines += ["", "## Sustainability"] + [f"- {p['en']}" for p in c["green"]["points"]]
        lines += ["", "## Questions"] + [f"- {f['q']['en']} {f['a']['en']}" for f in c["faq"]]
        lines += ["", "## Pages", f"- [Design your cover]({b}/shop/configure)",
                  f"- [Terms]({b}/shop/terms)", f"- [Privacy]({b}/shop/privacy)",
                  f"- [Warranty]({b}/shop/warranty)"]  # fmt: skip
        return PlainTextResponse("\n".join(lines) + "\n")
