"""The cover webshop's back end (ADR-062, docs/plans/cover-webshop.md): its settings, the
site's content with the AI CMS (draft, preview, live, history), the configurator's proposals
with the rain check, orders with Mollie payments, and an order's way into production. Also
(ADR-064): the site in several languages (DeepSeek translates), and the customer's sizes matched
against the covers we already make, with a learning mode (a colleague confirms first) and the
fit question after delivery.

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
    "film_poster": "",
    "notify_email": "",
    "languages": "nl,en,de,fr",
    "matching": {
        "mode": "shadow",
        "threshold_pct": None,
        "choice_pct": None,
        "stock_discount_pct": None,
    },  # fmt: skip
    "fit_mail": {"enabled": False, "days": 14},
}
UI_JSON = Path(__file__).resolve().parents[3] / "config" / "shop_ui.json"
LANG_NAMES = {"nl": "Dutch", "en": "English", "de": "German (informal du)",
              "fr": "French (vous)", "es": "Spanish", "it": "Italian", "da": "Danish",
              "sv": "Swedish", "no": "Norwegian", "pl": "Polish", "pt": "Portuguese"}  # fmt: skip

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
CONTENT_DEFAULTS["ui"] = {
    k: v for k, v in json.loads(UI_JSON.read_text(encoding="utf-8")).items() if k[0] != "_"
}


def tr(t: Any, lang: str) -> str:
    """A text in the asked language, else English, else Dutch."""
    if not isinstance(t, dict):
        return str(t or "")
    return str(t.get(lang) or t.get("en") or t.get("nl") or "")


def site_languages(auth: Any) -> list[str]:
    s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
    langs = [x.strip().lower() for x in str(s["languages"]).split(",")]
    out = [x for x in langs if re.fullmatch(r"[a-z]{2}", x)]
    return out or ["nl", "en"]


CMS_SYSTEM = """You edit the content of a webshop for made-to-measure outdoor furniture covers.
You get the current content (JSON; every text has one entry per language code: LANGS) and a
colleague's instruction. Change only what the instruction asks; keep every language in step
(translate the change into each of them; a new text gets all of them);
keep the tone: clear, warm, short sentences, no hype. Never invent facts (prices, guarantees,
certificates, numbers) that are not in the content or the instruction. Answer with JSON only:
{"changes": [{"path": "hero.title.nl", "value": "..."}, ...], "summary": "one sentence"}
Paths use dots and list indexes (faq.0.q.en); "ui" holds the buttons and labels, whose
{placeholders} stay as they are. To add a list item give the next index; to remove
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
    stock_model: str | None = Field(default=None, pattern=r"^suns-[a-z0-9-]{1,120}$")
    match_token: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{10,40}$")


class MatchIn(BaseModel):
    product: str = Field(max_length=40)
    sizes: dict[str, Any] = Field(default_factory=dict)
    email: str | None = Field(default=None, max_length=254)
    name: str | None = Field(default=None, max_length=120)
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")


class MatchAnswer(BaseModel):
    chosen: str = Field(pattern=r"^(custom|suns-[a-z0-9-]{1,120})$")
    note: str | None = Field(default=None, max_length=2000)


class FitIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


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
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")


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
STATUSES = ("awaiting_payment", "paid", "in_production", "sewn", "shipped", "cancelled", "failed",
            "returned")  # fmt: skip
MATCH_TABLE = """
CREATE TABLE IF NOT EXISTS match_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL NOT NULL,
  token TEXT NOT NULL UNIQUE,
  email TEXT,
  name TEXT,
  lang TEXT,
  product TEXT NOT NULL,
  given TEXT NOT NULL,
  result TEXT NOT NULL,
  best_model TEXT,
  best_pct REAL,
  decision TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  chosen TEXT,
  chosen_by TEXT,
  changed INTEGER,
  note TEXT,
  answered REAL
)"""
FEEDBACK_TABLE = """
CREATE TABLE IF NOT EXISTS fit_feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL NOT NULL,
  order_id INTEGER NOT NULL,
  score INTEGER NOT NULL,
  comment TEXT,
  photo TEXT
)"""
BANDS = ((95, 101), (90, 95), (85, 90), (80, 85), (0, 80))
DAY_S = 86400.0
PHOTO_MAX = 6_000_000
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


def cms_apply(site: Site, params: Any, text: str, langs: list[str] | None = None) -> dict[str, Any]:
    """The AI turns a colleague's instruction into changes of the draft (used by the admin
    page and by the command line `cover-site`); any language it left out is then translated."""
    from coverengine.ai import ask

    langs = langs or ["nl", "en"]
    draft = site.read("draft")
    system = CMS_SYSTEM.replace("LANGS", ", ".join(langs))
    ans = ask(params, system, json.dumps({"content": draft, "instruction": text},
                                         ensure_ascii=False))  # fmt: skip
    changes = [c for c in ans.get("changes", []) if isinstance(c, dict) and "path" in c]
    if not changes:
        return {"summary": ans.get("summary") or "nothing to change", "changes": []}
    for c in changes:  # only the content's own keys, no new top-level sections
        if str(c["path"]).split(".")[0] not in CONTENT_DEFAULTS:
            raise ValueError(f"the AI wanted to change {c['path']}, which is not part of the site")
    site.change(changes)
    if len(langs) > 2:  # noqa: PLR2004 - beyond Dutch and English
        translate(site, params, langs)
    return {"summary": ans.get("summary", ""), "changes": changes}


TRANSLATE_SYSTEM = """You translate the texts of a webshop for made-to-measure outdoor furniture
covers (Sunbrella Coverlast fabric, cut by our own software, sewn in our workshop). You get JSON
{"languages": {"de": "German (informal du)", ...}, "texts": {"<path>": {"nl": "...", "en": "..."}}}.
Translate every text into every asked language, from the Dutch and English given (they say the
same). Natural, short and warm, as a native copywriter would write it, not word for word. Keep
{placeholders}, product names, units, numbers and punctuation like "→" unchanged. A legal text
stays precise. One word for one thing, in every text (they are sent in batches): the cover
(hoes) is "Schutzhülle" in German, "housse" in French, "funda" in Spanish, "telo di copertura" in
Italian; the frame "Gestell"/"armature", the balloon "Ballon"/"ballon".
Answer with JSON only: {"texts": {"<path>": {"de": "...", ...}, ...}}"""
TRANSLATE_BATCH = 40


def _texts(doc: Any, path: str = "") -> list[tuple[str, dict[str, Any]]]:
    """Every translatable text in the content: a dict of language codes to strings."""
    if isinstance(doc, dict):
        if (
            doc
            and all(re.fullmatch(r"[a-z]{2}", str(k)) for k in doc)
            and ("nl" in doc or "en" in doc)
        ):
            return [(path, doc)]
        return [x for k, v in doc.items() for x in _texts(v, f"{path}.{k}" if path else k)]
    if isinstance(doc, list):
        return [x for i, v in enumerate(doc) for x in _texts(v, f"{path}.{i}")]
    return []


def translate(site: Site, params: Any, langs: list[str], only: str | None = None) -> dict[str, Any]:
    """Fill in the languages the draft is missing (DeepSeek), in batches; `only` limits it to
    paths starting with that prefix. The draft only: a person publishes."""
    from coverengine.ai import ask

    todo = []
    for path, t in _texts(site.read("draft")):
        if only and not path.startswith(only):
            continue
        source = {k: t[k] for k in ("nl", "en") if t.get(k)}
        missing = [x for x in langs if not t.get(x) and x not in source]
        if source and missing:
            todo.append((path, source, missing))
    done = 0
    for i in range(0, len(todo), TRANSLATE_BATCH):
        batch = todo[i : i + TRANSLATE_BATCH]
        want = sorted({x for _, _, m in batch for x in m})
        ans = ask(params, TRANSLATE_SYSTEM, json.dumps({
            "languages": {x: LANG_NAMES.get(x, x) for x in want},
            "texts": {path: src for path, src, _ in batch}}, ensure_ascii=False))  # fmt: skip
        got = ans.get("texts") or {}
        changes = []
        for path, _, missing in batch:
            out = got.get(path) or {}
            for x in missing:
                if isinstance(out.get(x), str) and out[x].strip():
                    changes.append({"path": f"{path}.{x}", "value": out[x].strip()})
        if changes:
            site.change(changes)
            done += len(changes)
    return {"translated": done, "texts": len(todo), "languages": langs}


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
    m = s["matching"]
    if m.get("mode") in ("shadow", "auto"):
        trial["match.mode"] = m["mode"]
    for k in ("threshold_pct", "choice_pct"):
        if m.get(k) not in (None, ""):
            trial[f"match.{k}"] = float(m[k])
    return Registry.load(None).resolve(trial=trial)


def install(app: FastAPI, auth: Any, data: Path, jobs: Any, store: Any) -> None:
    from coverengine import quote as q
    from coverengine.errors import CoverError

    from coverapi import mailer
    from coverapi.security import _address, require

    site = Site(data / "site")
    quotes = data / "shop_quotes"
    quotes.mkdir(parents=True, exist_ok=True)
    photos = data / "fit_photos"
    photos.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(auth.path) as db:
        db.execute(ORDERS_TABLE)
        db.execute(MATCH_TABLE)
        db.execute(FEEDBACK_TABLE)
        have = {r[1] for r in db.execute("PRAGMA table_info(orders)")}
        for col in ("feedback_token TEXT", "feedback_sent REAL"):
            if col.split()[0] not in have:
                db.execute(f"ALTER TABLE orders ADD COLUMN {col}")
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
            out = cms_apply(site, shop_params(auth), req.text, site_languages(auth))
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

    @app.post("/api/admin/cms/translate")
    def cms_translate(request: Request) -> dict[str, Any]:
        """Every language of the shop filled in (the draft; check the preview, then publish)."""
        user = require(request, "edit")
        try:
            out = translate(site, shop_params(auth), site_languages(auth))
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        auth.log(user, "site translated", out)
        return out

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
            "film_poster": s["film_poster"],
            "colours": q.colours(p),
            "products": s["products"],
            "indicative": bool(p["quote.prices_are_placeholders"]),
            "languages": site_languages(auth),
            "matching": str(p["match.mode"]),
        }

    @app.get("/api/shop/info")
    def shop_info(request: Request) -> dict[str, Any]:
        token = request.query_params.get("preview")
        draft = token and secrets.compare_digest(token, auth.setting(PREVIEW_SETTING, "") or "x")
        return {"content": site.read("draft" if draft else "live"), "preview": bool(draft),
                "settings": public_settings(), "options": q.options(shop_params(auth))}  # fmt: skip

    def _stock(model_id: str, product: str) -> dict[str, Any]:
        from coverengine import match as mt

        c = mt.card(store.models / model_id)
        if c is None or c["kind"] != product:
            raise HTTPException(400, "this cover is not in our range for this furniture")
        return c

    def _quote(req: ShopQuote) -> dict[str, Any]:
        from coverengine import match as mt

        p = shop_params(auth)
        stock = _stock(req.stock_model, req.product) if req.stock_model else None
        sizes = (
            {**req.sizes, **mt.fields_for(req.product, stock["size_cm"])} if stock else req.sizes
        )
        given = {**sizes, "vents": req.vents, "colour": req.colour}
        try:
            full = q.proposal(req.product, given, p)
            rain = q.rain_check(req.product, given, p)
            glb = q.scene_glb(req.product, given, p, req.support)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        if stock:  # an existing cover: its own sizes, and the stock discount (when set)
            off = settings()["matching"].get("stock_discount_pct") or 0
            full["price"]["sale_eur"] = round(full["price"]["sale_eur"] * (1 - float(off) / 100), 2)  # noqa: PLR2004 - percent
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
                  "support_eur": round(extra, 2),
                  "stock": ({"model_id": stock["model_id"], "name": stock["name"]}
                            if stock else None),
                  "match_token": req.match_token}  # fmt: skip
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
            "scene": f"/api/shop/scene/{qid}.glb", "stock": record["stock"],
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
        data = {"customer": req.model_dump(), "quote": record, "shipping_eur": shipping,
                "lang": req.lang}  # fmt: skip
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

    # ---- the customer's sizes against our range, and the learning mode (ADR-064) -------------
    def _match_row(token: str) -> dict[str, Any] | None:
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM match_requests WHERE token=?", (token,)).fetchone()
        return dict(row) if row else None

    def _lang_prefix(lang: str) -> str:
        langs = site_languages(auth)
        return "" if not langs or lang == langs[0] else f"{lang}/"

    @app.post("/api/shop/match")
    def shop_match(req: MatchIn, request: Request) -> dict[str, Any]:
        """Which existing cover fits these sizes. Learning mode (shadow): the customer leaves an
        e-mail address and a colleague confirms the proposal first; auto: the answer at once."""
        from coverengine import match as mt

        limit(request)
        p = shop_params(auth)
        mode = str(p["match.mode"])
        email = (req.email or "").strip()
        if mode == "shadow" and not EMAIL.match(email):
            raise HTTPException(400, "please give your e-mail address: we answer within a day")
        try:
            r = mt.match(req.product, req.sizes, store.models, p, top=8)  # param-ok: candidates
        except (ValueError, CoverError) as exc:
            raise HTTPException(400, str(exc)) from None
        best = r["matches"][0] if r["matches"] else None
        token = secrets.token_urlsafe(18)
        auto = mode == "auto"
        chosen = (
            (best["model_id"] if best and r["decision"] != "custom" else "custom") if auto else None
        )
        with sqlite3.connect(auth.path) as db:
            cur = db.execute(
                "INSERT INTO match_requests (created, token, email, name, lang, product, given, "
                "result, best_model, best_pct, decision, mode, status, chosen, chosen_by, "
                "answered) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), token, email or None, req.name, req.lang, req.product,
                 json.dumps(req.sizes), json.dumps(r), best["model_id"] if best else None,
                 best["score_pct"] if best else 0.0, r["decision"], mode,
                 "answered" if auto else "open", chosen, "auto" if auto else None,
                 time.time() if auto else None),
            )  # fmt: skip
            mid = cur.lastrowid
        if auto:
            return {"mode": mode, "token": token, "decision": r["decision"],
                    "match": best, "threshold_pct": r["threshold_pct"]}  # fmt: skip
        pct = f"{best['score_pct']} % {best['model_id']}" if best else "no cover of this kind"
        notify(f"Match request {mid}: {req.product}, best {pct}",
               f"{req.name or ''} <{email}> asks which cover fits:\n{json.dumps(req.sizes)}\n"
               f"Best: {pct}. Confirm or change it on the admin page, Matches.")  # fmt: skip
        return {"mode": mode, "token": token, "status": "open"}

    @app.get("/api/shop/match/{token}")
    def shop_match_answer(token: str) -> dict[str, Any]:
        row = _match_row(token)
        if row is None:
            raise HTTPException(404, "no such request")
        if row["status"] != "answered":
            return {"status": "open"}
        r = json.loads(row["result"])
        chosen = row["chosen"]
        match = None
        if chosen and chosen != "custom":
            match = next((m for m in r["matches"] if m["model_id"] == chosen), None) or r.get(
                "chosen_entry"
            )
        return {"status": "answered", "product": row["product"], "sizes": json.loads(row["given"]),
                "decision": "custom" if chosen == "custom" else r["decision"] if match is None
                else ("existing" if match["score_pct"] >= r["threshold_pct"] else "choice"),
                "match": match, "note": row["note"]}  # fmt: skip

    @app.get("/api/admin/matches")
    def matches(request: Request) -> dict[str, Any]:
        require(request, "edit")
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(x) for x in db.execute(
                "SELECT * FROM match_requests ORDER BY id DESC LIMIT 300")]  # fmt: skip
        for x in rows:
            x["result"], x["given"] = json.loads(x["result"]), json.loads(x["given"])
        return {"requests": rows, "mode": str(shop_params(auth)["match.mode"])}

    @app.put("/api/admin/matches/{mid}")
    def answer_match(mid: int, req: MatchAnswer, request: Request) -> dict[str, Any]:
        """A colleague's answer: the proposed cover, another one, or custom. Every change of the
        proposal is stored: that is what the learning page counts."""
        from coverengine import match as mt

        user = require(request, "edit")
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM match_requests WHERE id=?", (mid,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such request")
        r = json.loads(row["result"])
        proposed = (
            row["best_model"] if row["decision"] != "custom" and row["best_model"] else "custom"
        )
        if req.chosen != "custom" and not any(m["model_id"] == req.chosen for m in r["matches"]):
            e = mt.entry(store.models, req.chosen, row["product"], json.loads(row["given"]),
                         shop_params(auth))  # fmt: skip
            if e is None:
                raise HTTPException(400, f"no cover {req.chosen}")
            r["chosen_entry"] = e
        with sqlite3.connect(auth.path) as db:
            db.execute("UPDATE match_requests SET status='answered', chosen=?, chosen_by=?, "
                       "changed=?, note=?, answered=?, result=? WHERE id=?",
                       (req.chosen, user.username, int(req.chosen != proposed), req.note,
                        time.time(), json.dumps(r), mid))  # fmt: skip
        auth.log(user, "match answered", {"request": mid, "chosen": req.chosen,
                                          "changed": req.chosen != proposed})  # fmt: skip
        if row["email"]:
            c = site.read("live")["ui"]["words"]
            lang = row["lang"] or "nl"
            link = f"{base_url(request)}/shop/{_lang_prefix(lang)}match/{row['token']}"
            notify(tr(c["proposal"], lang), f"{tr(c['proposal'], lang)}:\n{link}\n",
                   to=row["email"])  # fmt: skip
        return {"ok": True, "changed": req.chosen != proposed}

    @app.get("/api/admin/learning")
    def learning(request: Request) -> dict[str, Any]:
        """Per match band: how many requests, how often a colleague changed the proposal, and
        how the delivered covers fit (the customers' answers, returns)."""
        require(request, "edit")
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            reqs = [dict(x) for x in db.execute("SELECT * FROM match_requests")]
            orders_ = [dict(x) for x in db.execute("SELECT id, status, data FROM orders")]
            fb = {x["order_id"]: x["score"] for x in db.execute("SELECT * FROM fit_feedback")}
        pct_of = {x["token"]: float(x["best_pct"] or 0) for x in reqs}
        out = []
        for lo, hi in BANDS:
            rs = [x for x in reqs if lo <= float(x["best_pct"] or 0) < hi]
            staff = [x for x in rs if x["chosen_by"] not in (None, "auto")]
            os_ = []
            for o in orders_:
                tok = json.loads(o["data"]).get("quote", {}).get("match_token")
                if tok in pct_of and lo <= pct_of[tok] < hi:
                    os_.append(o)
            scores = [fb[o["id"]] for o in os_ if o["id"] in fb]
            out.append({
                "band": f"{lo}–{min(hi, 100)} %", "requests": len(rs),
                "answered_by_staff": len(staff),
                "changed": sum(1 for x in staff if x["changed"]),
                "custom_chosen": sum(1 for x in rs if x["chosen"] == "custom"),
                "orders": len(os_), "fit_answers": len(scores),
                "fit_avg": round(sum(scores) / len(scores), 2) if scores else None,
                "returns": sum(1 for o in os_ if o["status"] == "returned"),
            })  # fmt: skip
        p = shop_params(auth)
        return {"bands": out, "threshold_pct": float(p["match.threshold_pct"]),
                "choice_pct": float(p["match.choice_pct"]),
                "mode": str(p["match.mode"])}  # fmt: skip

    # ---- the fit question after delivery -----------------------------------------------------
    def fit_mails() -> int:
        """Shipped orders older than fit_mail.days get one question: how does it fit?"""
        s = settings()
        if not s["fit_mail"].get("enabled") or not s["domain"] or not mailer.configured(auth):
            return 0
        days = float(s["fit_mail"].get("days") or 14)  # noqa: PLR2004 - two weeks
        base = "https://" + str(s["domain"]).removeprefix("https://").rstrip("/")
        sent = 0
        with sqlite3.connect(auth.path) as db:
            rows = db.execute(
                "SELECT id, email, data FROM orders WHERE status='shipped' AND feedback_sent IS "
                "NULL AND updated < ?", (time.time() - days * DAY_S,)).fetchall()  # fmt: skip
        words = site.read("live")["ui"]["words"]
        for oid, email, d in rows:
            lang = json.loads(d).get("lang") or "nl"
            token = secrets.token_urlsafe(18)
            link = f"{base}/shop/{_lang_prefix(lang)}fit/{token}"
            notify(tr(words["fit_title"], lang), f"{tr(words['fit_title'], lang)}\n{link}\n",
                   to=email)  # fmt: skip
            with sqlite3.connect(auth.path) as db:
                db.execute("UPDATE orders SET feedback_token=?, feedback_sent=? WHERE id=?",
                           (token, time.time(), oid))  # fmt: skip
            sent += 1
        return sent

    def fit_loop() -> None:
        while True:
            try:
                fit_mails()
            except Exception:  # noqa: BLE001 - try again in an hour
                pass
            time.sleep(3600)  # noqa: PLR2004 - hourly

    threading.Thread(target=fit_loop, daemon=True, name="fit-mails").start()
    app.state.fit_mails = fit_mails

    def _order_by_fit(token: str) -> tuple[int, str]:
        with sqlite3.connect(auth.path) as db:
            row = db.execute("SELECT id, data FROM orders WHERE feedback_token=?",
                             (token,)).fetchone()  # fmt: skip
        if row is None or not re.fullmatch(r"[A-Za-z0-9_-]{10,40}", token):
            raise HTTPException(404, "no such order")
        return int(row[0]), str(json.loads(row[1])["quote"]["quote"]["product"])

    @app.get("/api/shop/fit/{token}")
    def fit_get(token: str) -> dict[str, Any]:
        oid, product = _order_by_fit(token)
        with sqlite3.connect(auth.path) as db:
            done = db.execute("SELECT 1 FROM fit_feedback WHERE order_id=?", (oid,)).fetchone()
        return {"order": oid, "product": product, "answered": bool(done)}

    @app.post("/api/shop/fit/{token}")
    def fit_post(token: str, req: FitIn, request: Request) -> dict[str, Any]:
        limit(request, per_minute=10)
        oid, _ = _order_by_fit(token)
        with sqlite3.connect(auth.path) as db:
            db.execute("DELETE FROM fit_feedback WHERE order_id=?", (oid,))
            db.execute("INSERT INTO fit_feedback (created, order_id, score, comment) "
                       "VALUES (?, ?, ?, ?)",
                       (time.time(), oid, req.score, req.comment))  # fmt: skip
        notify(f"Fit answer, order {oid}: {req.score}/5", req.comment or "")
        return {"ok": True}

    @app.post("/api/shop/fit/{token}/photo")
    async def fit_photo(token: str, request: Request) -> dict[str, Any]:
        limit(request, per_minute=10)
        oid, _ = _order_by_fit(token)
        body = await request.body()
        kind = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}
        ext = next((v for k, v in kind.items() if body.startswith(k)), None)
        if ext is None or len(body) > PHOTO_MAX:
            raise HTTPException(400, "a JPEG, PNG or WebP photo up to 6 MB")
        name = f"order-{oid}.{ext}"
        (photos / name).write_bytes(body)
        with sqlite3.connect(auth.path) as db:
            db.execute("UPDATE fit_feedback SET photo=? WHERE order_id=?", (name, oid))
        return {"ok": True}

    @app.get("/api/admin/feedback")
    def feedback(request: Request) -> dict[str, Any]:
        require(request, "edit")
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(x) for x in db.execute("SELECT * FROM fit_feedback ORDER BY id DESC")]
        return {"feedback": rows}

    @app.get("/api/admin/feedback/photo/{name}")
    def feedback_photo(name: str, request: Request) -> Response:
        require(request, "edit")
        if not re.fullmatch(r"order-\d+\.(jpg|png|webp)", name) or not (photos / name).is_file():
            raise HTTPException(404, "no such photo")
        media = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[
            name.rsplit(".", 1)[1]
        ]
        return Response((photos / name).read_bytes(), media_type=media)

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
        if d["quote"].get("stock"):  # an existing cover: cut from its own, tested pattern
            model_id = str(d["quote"]["stock"]["model_id"])
            with sqlite3.connect(auth.path) as db:
                db.execute("UPDATE orders SET model_id=?, status='in_production', updated=? "
                           "WHERE id=?", (model_id, time.time(), oid))  # fmt: skip
            notify(f"Order {oid}: cut the existing cover {model_id}",
                   f"Order {oid} is an existing cover from the range: {model_id} "
                   f"(cut.dxf of that model).")  # fmt: skip
            return model_id
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

    def lang_of(request: Request, prefix: str | None) -> str:
        langs = site_languages(auth)
        if prefix in langs:
            return str(prefix)
        want = request.query_params.get("lang", "")
        return want if want in langs else langs[0]

    def base(request: Request) -> str:
        s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
        if s["domain"]:
            return "https://" + str(s["domain"]).removeprefix("https://").rstrip("/")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        return f"{scheme}://{host}"

    def render(request: Request, page: str, prefix: str | None = None) -> HTMLResponse:
        if not template.is_file():
            raise HTTPException(404, "the shop is not built")
        token = request.query_params.get("preview")
        draft = bool(token) and secrets.compare_digest(
            token or "", auth.setting(PREVIEW_SETTING, "") or "x"
        )
        c = site().read("draft" if draft else "live")
        langs = site_languages(auth)
        lang = lang_of(request, prefix)
        s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
        company = s["company"]
        tail = "" if page == "home" else page

        def url_in(x: str) -> str:
            return base(request) + "/shop/" + ("" if x == langs[0] else f"{x}/") + tail

        url = url_in(lang)
        w = c["ui"]["words"]
        title = tr(c["meta"]["title"], lang)
        if page in ("terms", "privacy", "warranty"):
            name = tr(w["terms_page" if page == "terms" else page], lang)
            title = f"{name} · {title}"
        elif page == "configure":
            title = f"{tr(c['hero']['cta'], lang)} · {title}"
        desc = tr(c["meta"]["description"], lang)
        ld: list[dict[str, Any]] = [
            {"@context": "https://schema.org", "@type": "Organization",
             "name": company["name"] or "Covers", "url": base(request) + "/shop/",
             "email": company["email"] or None, "telephone": company["phone"] or None,
             "address": {"@type": "PostalAddress", "streetAddress": company["street"] or None,
                         "postalCode": company["postcode"] or None,
                         "addressLocality": company["city"] or None,
                         "addressCountry": company["country"] or None}},
            {"@context": "https://schema.org", "@type": "Product",
             "name": tr(c["hero"]["title"], lang), "description": desc,
             "brand": company["name"] or "Covers",
             "material": "Sunbrella Coverlast: polyester with an acrylic coating",
             "offers": {"@type": "AggregateOffer", "priceCurrency": "EUR",
                        "availability": "https://schema.org/MadeToOrder"}},
            {"@context": "https://schema.org", "@type": "HowTo",
             "name": tr(c["hero"]["cta"], lang), "inLanguage": lang,
             "step": [{"@type": "HowToStep", "position": i + 1, "name": tr(st["title"], lang),
                       "text": tr(st["text"], lang)} for i, st in enumerate(c["steps"])]},
            {"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": lang,
             "mainEntity": [{"@type": "Question", "name": tr(f["q"], lang),
                             "acceptedAnswer": {"@type": "Answer", "text": tr(f["a"], lang)}}
                            for f in c["faq"]]},
        ]  # fmt: skip
        alternates = (
            "".join(
                f'<link rel="alternate" hreflang="{x}" href="{_esc(url_in(x))}" />\n' for x in langs
            )
            + f'<link rel="alternate" hreflang="x-default" href="{_esc(url_in(langs[0]))}" />\n'
        )
        head = (
            f"<title>{_esc(title)}</title>\n"
            f'<meta name="description" content="{_esc(desc)}" />\n'
            f'<link rel="canonical" href="{_esc(url)}" />\n'
            + alternates
            + f'<meta property="og:title" content="{_esc(title)}" />\n'
            f'<meta property="og:description" content="{_esc(desc)}" />\n'
            f'<meta property="og:locale" content="{_esc(lang)}" />\n'
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
            body_html = f"<h1>{_esc(title.split(' · ')[0])}</h1>" + "".join(
                f"<p>{_esc(x)}</p>" for x in tr(c["legal"][page], lang).split("\n\n") if x
            )
        else:
            body_html = (
                f"<h1>{_esc(tr(c['hero']['title'], lang))}</h1>"
                f"<p>{_esc(tr(c['hero']['subtitle'], lang))}</p>"
                f"<h2>{_esc(tr(w['how'], lang))}</h2><ol>"
                + "".join(
                    f"<li><h3>{_esc(tr(st['title'], lang))}</h3>"
                    f"<p>{_esc(tr(st['text'], lang))}</p></li>"
                    for st in c["steps"]
                )
                + f"</ol><h2>{_esc(tr(c['green']['title'], lang))}</h2><ul>"
                + "".join(f"<li>{_esc(tr(x, lang))}</li>" for x in c["green"]["points"])
                + f"</ul><h2>{_esc(tr(w['faq'], lang))}</h2>"
                + "".join(
                    f"<h3>{_esc(tr(f['q'], lang))}</h3><p>{_esc(tr(f['a'], lang))}</p>"
                    for f in c["faq"]
                )
                + f'<p><a href="{_esc(url_in(lang).removesuffix(tail))}configure">'
                + _esc(tr(c["hero"]["cta"], lang))
                + "</a></p>"
                + "<nav>"
                + "".join(
                    f'<a href="{_esc(url_in(x))}" hreflang="{x}">{x.upper()}</a> ' for x in langs
                )  # fmt: skip
                + "</nav>"
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
        parts = page.strip("/").split("/", 1)
        prefix = None
        if parts[0] in site_languages(auth):
            prefix = parts[0]
            page = parts[1] if len(parts) > 1 else ""
        page = page.strip("/")
        known = page in ("configure", "terms", "privacy", "warranty") or page.startswith(
            ("order/", "match/", "fit/")
        )
        return render(request, page if known else "home", prefix)

    media = Path(app.state.store.root) / "media"

    @app.get("/media/{name}", include_in_schema=False)
    def media_file(name: str) -> Response:
        """The shop's films and pictures (data/media; ADR-065), with byte ranges for video."""
        from fastapi.responses import FileResponse

        if not re.fullmatch(r"[a-z0-9_-]{1,80}\.(mp4|webm|jpg|png|webp)", name):
            raise HTTPException(404, "no such file")
        path = media / name
        if not path.is_file():
            raise HTTPException(404, "no such file")
        return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

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
        langs = site_languages(auth)
        urls = "".join(
            f"<url><loc>{b}/shop/{'' if x == langs[0] else x + '/'}{p}</loc></url>"
            for x in langs
            for p in ("", "configure", "terms", "privacy", "warranty")
        )
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
                 f"> {tr(c['meta']['description'], 'en')}", "",
                 "## How it works"]  # fmt: skip
        lines += [f"- {tr(st['title'], 'en')}: {tr(st['text'], 'en')}" for st in c["steps"]]
        lines += ["", "## Sustainability"] + [f"- {tr(p, 'en')}" for p in c["green"]["points"]]
        lines += ["", "## Questions"] + [
            f"- {tr(f['q'], 'en')} {tr(f['a'], 'en')}" for f in c["faq"]
        ]
        lines += ["", "## Pages", f"- [Design your cover]({b}/shop/configure)",
                  f"- [Terms]({b}/shop/terms)", f"- [Privacy]({b}/shop/privacy)",
                  f"- [Warranty]({b}/shop/warranty)", "",
                  "## Languages",
                  "The shop is in " + ", ".join(site_languages(auth)) + "."]  # fmt: skip
        return PlainTextResponse("\n".join(lines) + "\n")
