"""Start from a photo or a link (ADR-086): the configurator's sizes suggested from the
customer's own photo of their furniture, or from the page of a webshop that sells it.

- A link is fetched here, safely: http(s) only; every host is resolved and must be a public
  address (no private, loopback, link-local or metadata address: SSRF), each redirect (at most
  MAX_REDIRECTS) is checked again, and the connection goes to the address that was checked (no
  second DNS lookup); a time and a size limit; a page must be HTML, an image an image.
- From the page the program takes what is written: the title, the og/meta tags, a JSON-LD
  Product (name, image, sizes) and the text around "afmetingen / dimensions / Maße / cm". The
  product's main image (og:image) is fetched with the same rules.
- The AI (ai.vision_*, the cheap Flash model; guarded by the month's budget, ADR-078) gets the
  photos and/or those facts and says which configurator product it is and its sizes, each with
  where it came from. A number written on the page beats an estimate from a picture.
- A photo alone (ADR-087, ADR-092) is first identified (type, brand and model when it can,
  features, materials, estimated sizes, search queries); Google Search runs for the recognised
  brand and model and, beside it, for the look alone; each result's own picture is held against
  the photo. The very product is "recognised" (shown by name), a similar enough one is a
  "comparable" start, anything less is dropped and the photo's estimates are asked to measure.
  A real search by image (Cloud Vision web detection, ADR-112) runs first: its pages that show
  the photo become candidates and the names of its matching pictures help the identification.
- The admin's photo test (Admin, Shop settings) runs the same flow and shows every step.
- The sizes are checked against config/quote_products.json (clipped to the range, flagged), and
  the proposal carries the existing cover that fits (coverengine.match), if any.
- Per visitor (the Worker's x-client-ip) at most `suggest.per_hour` suggestions an hour. Nothing
  is stored: a photo lives only for the request. When the customer orders, the browser sends
  the link and the summary with the order, and the photos to /api/shop/order/{token}/source.
"""

from __future__ import annotations

import contextvars
import http.client
import io
import ipaddress
import json
import logging
import re
import socket
import sqlite3
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)
DAY_S = 86400.0


def _carry(fn: Any) -> Any:
    """fn for another thread, run in a copy of this thread's context: the visitor whose paid
    calls these are (spend.for_visitor, ADR-103) goes along."""
    ctx = contextvars.copy_context()
    return lambda *a: ctx.copy().run(fn, *a)


MAX_REDIRECTS = 3
MAX_PHOTOS = 3
MAX_SOURCE_UPLOADS = 10  # an order's photos: uploads per visitor per hour
HOUR_S = 3600.0
PAGE_TYPES = ("text/html", "application/xhtml+xml")
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/avif")  # many shops send AVIF
PHOTO_EDGE_PX = 1600  # photos are made this small before the AI sees them (fewer tokens)
SNIPPET_CHARS = 220
SNIPPETS_MAX = 10
FACTS_MAX_CHARS = 4000
CHECK_BELOW = 0.6  # a size the AI is less sure of than this must be checked
NAMES_MAX = 15  # names of matching web pictures and pages given to the identification (ADR-112)
TRACE_THUMB_PX = 160  # the photo test shows each compared web picture this small
PICTURE_URL = re.compile(r"\.(jpe?g|png|webp|avif|gif)$", re.I)
DIMENSION_WORDS = re.compile(
    r"afmeting|dimension|maße|masse|abmessung|größe|grootte|taille|lengte|breedte|hoogte|"
    r"length|width|height|depth|diepte|länge|breite|höhe|tiefe|longueur|largeur|hauteur|\bcm\b",
    re.I,
)
UA = "Mozilla/5.0 (compatible; S2DIO-cover-sizes/1.0; +https://shop.s2dio.living)"


class SuggestError(Exception):
    """Shown to the customer as it is (plain words)."""


# ---- fetching a page or an image, safely --------------------------------------------------------


def _public(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped is not None:
        a = a.ipv4_mapped
    return bool(a.is_global) and not (a.is_multicast or a.is_reserved or a.is_link_local)


def resolve(host: str, port: int) -> str:
    """The host's address, when every address it has is public (else refused)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise SuggestError("that address cannot be found") from None
    ips = sorted({str(i[4][0]) for i in infos})
    if not ips or not all(_public(ip) for ip in ips):
        raise SuggestError("that address is not a public web page")
    return ips[0]


def _request(
    scheme: str, host: str, port: int, path: str, ip: str, timeout: float
) -> http.client.HTTPResponse:
    """One GET to the checked address (the name only for TLS and the Host header)."""
    cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
    conn = cls(host, port, timeout=timeout)

    def pinned(addr: Any, t: Any = None, src: Any = None) -> socket.socket:
        return socket.create_connection((ip, addr[1]), timeout, src)

    conn._create_connection = pinned  # type: ignore[attr-defined]  # no second DNS lookup
    headers = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "nl,en;q=0.8,de;q=0.6"}
    conn.request("GET", path or "/", headers=headers)
    return conn.getresponse()


def fetch(url: str, kinds: tuple[str, ...], timeout: float, max_bytes: int) -> tuple[str, bytes]:
    """The body at `url` (following up to MAX_REDIRECTS redirects, each checked again), when it
    is one of `kinds` and at most `max_bytes`. Returns (final url, body)."""
    deadline = time.monotonic() + timeout
    for _ in range(MAX_REDIRECTS + 1):
        u = urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise SuggestError("only http and https links")
        port = u.port or (443 if u.scheme == "https" else 80)
        ip = resolve(u.hostname, port)
        left = deadline - time.monotonic()
        if left <= 0:
            raise SuggestError("the page took too long")
        path = u.path + (f"?{u.query}" if u.query else "")
        try:
            r = _request(u.scheme, u.hostname, port, path, ip, left)
        except (OSError, http.client.HTTPException):
            raise SuggestError("the page could not be opened") from None
        if r.status in (301, 302, 303, 307, 308):
            loc = r.getheader("Location")
            r.close()
            if not loc:
                raise SuggestError("the page sent us nowhere")
            url = urljoin(url, loc)
            continue
        if r.status != 200:
            r.close()
            raise SuggestError(f"the page answered {r.status}")
        ctype = (r.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in kinds:
            r.close()
            raise SuggestError("that link is not a web page" if kinds == PAGE_TYPES
                               else "that is not a photo")  # fmt: skip
        body = r.read(max_bytes + 1)
        r.close()
        if len(body) > max_bytes:
            raise SuggestError("the page is too large")
        return url, body
    raise SuggestError("too many redirects")


# ---- what a page says ---------------------------------------------------------------------------


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.ld: list[str] = []
        self.text: list[str] = []
        self._in: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"])
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in.append("ld")
        elif tag in ("script", "style", "noscript", "svg"):
            self._in.append("skip")
        elif tag == "title":
            self._in.append("title")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg", "title") and self._in:
            self._in.pop()

    def handle_data(self, data: str) -> None:
        where = self._in[-1] if self._in else ""
        if where == "ld":
            self.ld.append(data)
        elif where == "title":
            self.title += data
        elif where != "skip" and data.strip():
            self.text.append(" ".join(data.split()))


def _products(node: Any) -> list[dict[str, Any]]:
    """Every JSON-LD object of type Product (also inside @graph or lists)."""
    out: list[dict[str, Any]] = []
    if isinstance(node, list):
        for x in node:
            out += _products(x)
    elif isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(str(x).lower() in ("product", "productgroup") for x in types):
            out.append(node)
        for key in ("@graph", "itemListElement", "hasVariant"):
            if key in node:
                out += _products(node[key])
    return out


def _quantity(v: Any) -> str | None:
    if isinstance(v, dict):
        val, unit = v.get("value"), v.get("unitText") or v.get("unitCode") or ""
        return f"{val} {unit}".strip() if val is not None else None
    return str(v) if v not in (None, "") else None


def page_facts(html: bytes, url: str) -> dict[str, Any]:
    """Title, description, main image and every size written on the page."""
    p = _Page()
    try:
        p.feed(html.decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 - a broken page still has what was read so far
        pass
    facts: dict[str, Any] = {
        "url": url,
        "title": " ".join(p.title.split())[:200],
        "description": (p.meta.get("og:description") or p.meta.get("description") or "")[:500],
        "image": p.meta.get("og:image") or p.meta.get("twitter:image") or "",
        "product": {},
    }
    for block in p.ld:
        try:
            doc = json.loads(block)
        except ValueError:
            continue
        for prod in _products(doc):
            d = facts["product"]
            d.setdefault("name", prod.get("name"))
            img = prod.get("image")
            if not facts["image"] and img:
                facts["image"] = img[0] if isinstance(img, list) else (
                    img.get("url") if isinstance(img, dict) else str(img))  # fmt: skip
            for key in ("width", "height", "depth", "length", "size"):
                q = _quantity(prod.get(key))
                if q:
                    d.setdefault("sizes", {})[key] = q
            for prop in prod.get("additionalProperty") or []:
                if isinstance(prop, dict) and DIMENSION_WORDS.search(str(prop.get("name", ""))):
                    q = _quantity(prop.get("value")) or _quantity(prop)
                    if q:
                        d.setdefault("sizes", {})[str(prop.get("name"))[:60]] = q
    text = " ".join(p.text)
    snippets: list[str] = []
    for m in DIMENSION_WORDS.finditer(text):
        a = max(0, m.start() - SNIPPET_CHARS // 2)
        piece = text[a : a + SNIPPET_CHARS]
        if re.search(r"\d", piece) and not any(piece[:40] in s for s in snippets):
            snippets.append(piece)
        if len(snippets) >= SNIPPETS_MAX:
            break
    facts["sizes_text"] = snippets
    if facts["image"]:
        facts["image"] = urljoin(url, str(facts["image"]))
    return facts


# ---- photos -------------------------------------------------------------------------------------


def photo_png(data: bytes) -> bytes:
    """A customer's photo as a PNG at most PHOTO_EDGE_PX on its long side (JPEG, PNG, WebP; an
    iPhone's HEIC is refused with a clear way out)."""
    from PIL import Image, UnidentifiedImageError

    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        raise SuggestError("HEIC photos are not supported: please send a JPG or PNG (on an "
                           "iPhone: Settings, Camera, Formats, Most Compatible)")  # fmt: skip
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError):
        raise SuggestError("that file is not a photo (JPG, PNG, WebP or AVIF please)") from None
    # a webshop's cut-out picture: its see-through background white, not black (which made the
    # furniture hard to recognise and found nothing in the image search)
    rgba = im.convert("RGBA")
    rgb = Image.new("RGB", rgba.size, "white")
    rgb.paste(rgba, mask=rgba.getchannel("A"))
    rgb.thumbnail((PHOTO_EDGE_PX, PHOTO_EDGE_PX))
    out = io.BytesIO()
    rgb.save(out, "PNG", optimize=True)
    return out.getvalue()


# ---- the AI and the proposal --------------------------------------------------------------------

SYSTEM = """You help a webshop that sews made-to-measure covers for outdoor furniture. A customer
gave a photo of their furniture and/or the facts of a webshop page selling it. Say which of the
configurator's products it is and its sizes, in cm, using ONLY these products and fields:
__PRODUCTS__
Rules:
- A size WRITTEN on the page (JSON-LD, the text) is "page". Convert inches (1 in = 2.54 cm) and mm.
  The page's width/depth/length may be named differently: map them onto the fields sensibly
  (e.g. a lounger's length is its long side, a table's width its short side).
- A size you can only judge from a picture is "photo": give your best estimate, with an honest
  confidence (0-1); a photo alone rarely deserves more than 0.5.
- Leave out a field you cannot justify at all. A yes/no field is true/false.
- A sun lounger: say in "notes" whether the back is raised (a headrest) and, if fields for it are
  listed, fill them.
- The page's "relation" says what it is to the customer's furniture. "The same product": its
  written sizes are the furniture's own. "A SIMILAR product": its sizes are only a start; check
  them against the photo, never call it the customer's product and never name its brand as
  theirs (say the sizes come from a similar product).
- "A first look at the photo" (when given) is an earlier reading: a help, not a fact.
Answer JSON only:
{"product": "<key>", "fields": {"<field>": {"value": <number or true/false>, "source": "page" or
"photo", "confidence": <0-1>}}, "summary": "one or two plain sentences for the customer, in
LANGUAGE", "notes": "anything the workshop should know"}"""


def _products_text(products: dict[str, Any]) -> str:
    lines = []
    for k, v in products.items():
        fs = []
        for f, (_d, lo, hi) in v["fields"].items():
            fs.append(f"{f} (yes/no)" if lo is None else f"{f} ({lo}-{hi})")
        lines.append(f"- {k}: {v['label']}: " + ", ".join(fs))
    return "\n".join(lines)


def ask(
    params: Any,
    photos: list[bytes],
    facts: dict[str, Any] | None,
    lang: str,
    hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import base64

    from coverengine.ai import ask_parts
    from coverengine.params import Registry
    from coverengine.quote import PRODUCTS

    vision = Registry.load(None).resolve(trial={
        "ai.provider": str(params["ai.vision_provider"]),
        "ai.model": str(params["ai.vision_model"]),
        "ai.base_url": str(params["ai.vision_base_url"]),
        "ai.timeout_s": int(params["suggest.ai_timeout_s"])})  # fmt: skip
    system = SYSTEM.replace("__PRODUCTS__", _products_text(PRODUCTS)).replace(
        "LANGUAGE", {"nl": "Dutch", "de": "German", "fr": "French"}.get(lang, "English")
    )
    parts: list[dict[str, Any]] = []
    if facts:
        page = "The webshop page: " + json.dumps(facts)[:FACTS_MAX_CHARS]
        parts.append({"type": "text", "text": page})
    if hint:
        look = {k: hint[k] for k in ("kind", "type", "features", "est_cm") if hint.get(k)}
        parts.append({"type": "text", "text": "A first look at the photo: " + json.dumps(look)})
    for png in photos:
        b = base64.b64encode(png).decode()
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}})
    if not parts:
        raise SuggestError("give a photo or a link")
    ans = ask_parts(vision, system, parts)
    ans.pop("_usage", None)
    return ans


def _png_part(png: bytes) -> dict[str, Any]:
    import base64

    return {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}}


def _json_in(text: str) -> dict[str, Any]:
    """The one JSON object in an answer (a grounded answer may wrap it in prose or markdown)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        doc = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return doc if isinstance(doc, dict) else {}


def gemini(
    params: Any, parts: list[dict[str, Any]], what: str, timeout: float, search: bool = False
) -> dict[str, Any]:
    """One call to Gemini's own API (the vision model; ADR-092): pictures and text in, the text
    out, with Google Search when `search` (the grounding's real links and the queries it ran
    come back too). Tokens and the search fee go into the month's ledger (ADR-078); the budget
    guards every call. A failure is a CoverError with the reason (never the key)."""
    import urllib.error
    import urllib.request

    from coverengine import spend
    from coverengine.ai import _key
    from coverengine.errors import CoverError

    spend.guard(params)
    model = str(params["ai.vision_model"])
    config: dict[str, Any] = {"thinkingConfig": {"thinkingLevel": str(params["suggest.thinking"])}}
    if not search:  # a grounded answer cannot be forced to JSON; the others can
        config["responseMimeType"] = "application/json"
    body: dict[str, Any] = {"contents": [{"parts": parts}], "generationConfig": config}
    if search:
        body["tools"] = [{"google_search": {}}]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "x-goog-api-key": _key("gemini")})  # fmt: skip
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - Google's API
            reply = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise CoverError(f"the AI did not answer: HTTP {exc.code} ({what})") from None
    except (OSError, ValueError) as exc:
        raise CoverError(f"the AI did not answer: {type(exc).__name__} ({what})") from None
    u = reply.get("usageMetadata") or {}
    out_tokens = int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
    usage = {"prompt_tokens": u.get("promptTokenCount"), "completion_tokens": out_tokens}
    spend.record(params, model, usage, what)
    cand = (reply.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    grounding = cand.get("groundingMetadata") or {}
    queries = [str(q) for q in grounding.get("webSearchQueries") or []]
    if search:  # Google bills each search query the model runs (to confirm on the bill)
        fee = float(params["suggest.search_query_eur"]) * max(1, len(queries))  # type: ignore[arg-type]
        spend.record_eur(model + " search", fee, what)
    links = []
    for ch in grounding.get("groundingChunks") or []:
        web = ch.get("web") or {}
        if str(web.get("uri", "")).startswith("http"):
            links.append({"url": str(web["uri"]), "title": str(web.get("title") or "")})
    return {"text": text, "links": links, "queries": queries}


IDENTIFY = """You help a webshop that sews made-to-measure covers for outdoor furniture. Look at
the customer's photo and describe the furniture so that its own product page can be found on the
web. Recognise the brand and the model (collection) name when you can: a logo, a label, or a
design you really know. Be honest: brand_confidence above 0.7 only when you truly recognise this
exact product, not because it resembles a famous design.
The webshop's products: __PRODUCTS__
Answer JSON only:
{"kind": "<one of the product keys above>", "type": "<what it is, e.g. 3-seater lounge sofa,
rectangular dining table, sun lounger with raised back>", "brand": "<brand or null>", "model":
"<model or collection name or null>", "brand_confidence": <0-1>, "materials": ["..."],
"colours": ["..."], "features": ["distinctive visible details: arms, legs, back, weaving,
cushions, number of seats, table top shape ..."], "est_cm": {"length": <n>, "depth": <n>,
"height": <n>, "seat_height": <n>}, "queries": ["up to __N__ web search queries WITHOUT a brand
name that would find this product's page or its closest equivalents for sale, by its type,
shape, distinctive features and materials (e.g. 'outdoor lounge sofa teak frame rope back'),
the most specific first, one in Dutch and one in German"]}"""


HINTS = """
A search by image found web pictures and pages that show this very photo (or part of it). Their
file names and titles (shops name product pictures after the product; a name that recurs is very
likely this product's brand and model, a single odd one may be a mismatch):
__NAMES__
Use them for brand and model when they fit what you see (then brand_confidence may be high)."""


def identify(params: Any, png: bytes, names: list[str] | None = None) -> dict[str, Any]:
    """What the photo shows (ADR-092): product type, brand and model when recognisable,
    materials, distinctive features, estimated sizes and the queries to search with. `names`:
    what the search by image's matching pictures and pages are called (ADR-112)."""
    from coverengine.quote import PRODUCTS

    n = int(params["suggest.queries"])  # type: ignore[arg-type]
    keys = "; ".join(f"{k} ({v['label']})" for k, v in PRODUCTS.items())
    prompt = IDENTIFY.replace("__PRODUCTS__", keys).replace("__N__", str(n))
    if names:
        prompt += HINTS.replace("__NAMES__", "\n".join(f"- {x}" for x in names[:NAMES_MAX]))
    timeout = float(params["suggest.ai_timeout_s"])  # type: ignore[arg-type]
    doc = _json_in(gemini(params, [_png_part(png), {"text": prompt}], "suggest identify",
                          timeout)["text"])  # fmt: skip
    queries = [str(q).strip() for q in doc.get("queries") or [] if str(q).strip()][:n]
    try:
        conf = float(doc.get("brand_confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    brand = str(doc.get("brand") or "").strip()
    model = str(doc.get("model") or "").strip()
    if brand.lower() in ("null", "none", "unknown"):
        brand = ""
    if model.lower() in ("null", "none", "unknown"):
        model = ""
    return {**doc, "brand": brand, "model": model, "brand_confidence": conf, "queries": queries}


SEARCH = """Find this outdoor furniture on the web. What was seen in the photo:
__IDENT__
__FIRST__Search with these queries (and better ones if they find nothing):
__QUERIES__
Look for its own product page (best: the manufacturer's page that states the dimensions), and
else the pages of the most similar products for sale (same type, shape and number of seats).
Read the sizes from those pages (in cm; convert inches and mm). Answer JSON only (no markdown):
{"pages": [{"url": "<the product page URL>", "title": "<product name>", "brand": "<brand>",
"image": "<the URL of the product's main photo, if you saw it>", "same": <true when you believe
it is exactly the product in the photo>, "sizes_cm": {"length": <n>, "width": <n>, "depth": <n>,
"height": <n>, "seat_height": <n>}}]}
with at most __PAGES__ pages, the best match first; leave out sizes a page does not state."""


def search_comparable(
    params: Any, png: bytes, ident: dict[str, Any] | None = None, brand: bool = False
) -> list[dict[str, Any]]:
    """Product pages on the web for a photo (owner, 7 Oct 2026; ADR-087, ADR-092): Gemini with
    Google Search, given what `identify` saw. `brand`: search the recognised brand and model
    (the manufacturer's page first); else search by the look alone, without any brand, so that a
    wrong guess of the brand cannot steer it. The pages it names (with the sizes it read) come
    first, then the search's own links (real results, without sizes)."""
    ident = ident or {}
    keys = ("type", "materials", "colours", "features", "est_cm")
    seen_ = {k: ident.get(k) for k in keys if ident.get(k)}
    first, queries = "", "\n".join(f"- {q}" for q in ident.get("queries") or []) or "- (your own)"
    if brand:
        name = f"{ident.get('brand', '')} {ident.get('model', '')}".strip()
        first = (f"It may be the {name}: search for that exact product (the manufacturer's own "
                 "page first) and check that it really looks like the photo.\n")  # fmt: skip
        queries = f"- {name}\n- {name} dimensions\n- {name} afmetingen"
    prompt = (SEARCH.replace("__IDENT__", json.dumps(seen_) if seen_ else "(see the photo)")
              .replace("__FIRST__", first).replace("__QUERIES__", queries)
              .replace("__PAGES__", str(params["suggest.search_pages"])))  # fmt: skip
    timeout = float(params["suggest.search_timeout_s"])  # type: ignore[arg-type]
    got = gemini(params, [_png_part(png), {"text": prompt}], "suggest search", timeout, True)
    pages: list[dict[str, Any]] = []
    for pg in _json_in(got["text"]).get("pages") or []:
        # a picture's address is no product page (it became the customer's "recognised" link)
        if (isinstance(pg, dict) and str(pg.get("url", "")).startswith("http")
                and not PICTURE_URL.search(urlsplit(str(pg["url"])).path)):  # fmt: skip
            raw = pg.get("sizes_cm")
            sizes: dict[str, Any] = raw if isinstance(raw, dict) else {}
            kept = {k: v for k, v in sizes.items() if isinstance(v, int | float) and v > 0}
            img = str(pg.get("image") or "")
            pages.append({"url": str(pg["url"]), "title": str(pg.get("title") or ""),
                          "brand": str(pg.get("brand") or ""), "same": pg.get("same") is True,
                          "image": img if img.startswith("http") else "",
                          "sizes_cm": kept})  # fmt: skip
    pages += got["links"]
    seen, out = set(), []
    for pg in pages:
        if pg["url"] not in seen:
            seen.add(pg["url"])
            out.append(pg)
    return out


_NAME_NOISE = re.compile(r"^(\d+|\d+x\d*|x\d+|[0-9a-f]{8,}|[a-z]?\d{5,}[a-z\d]*|cdn|shop|files|"
                         r"products?|images?|uploads?|media|catalog|cache|large|thumb|img|"
                         r"jpe?g|png|webp|avif|v)$", re.I)  # fmt: skip


def image_name(url: str) -> str:
    """The words in a web picture's file name ("Marolo-SUNS-Daybed-BZ-Free-26-2500_1.jpg" ->
    "Marolo SUNS Daybed BZ Free"): shops name their product pictures after the product, so a
    picture that matches the photo often says what it is (ADR-112). Empty when it says nothing
    (a hash, numbers)."""
    from urllib.parse import unquote

    last = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    last = re.sub(r"\.[a-z0-9]{2,5}$", "", last, flags=re.I)
    words = [w for w in re.split(r"[-_+.,~\s()]+", last) if w and not _NAME_NOISE.match(w)]
    letters = [w for w in words if re.search(r"[a-z]{3}", w, re.I)]
    return " ".join(words)[:100] if len(letters) >= 2 else ""


def read_web_detection(web: dict[str, Any]) -> dict[str, Any]:
    """Cloud Vision's web detection made useful (ADR-112). Measured on 15 photos: Google lists
    first the pages about its best-guess label ("studio couch", "swimming pool": no matching
    picture at all) and only then the pages that really show the photo; the pictures that match
    usually carry the product's name in their file name. So:
    - "pages": only the pages with a matching picture, full matches first;
    - "names": what those pictures and pages are called (the hints for the identification);
    - "entities", "labels", "images" and "similar" as Google gives them (for the diagnostics;
      the label and the similar pictures are too generic to search with)."""
    pages: list[dict[str, Any]] = []
    other = 0
    for pg in web.get("pagesWithMatchingImages") or []:
        url = str(pg.get("url") or "")
        full, part = pg.get("fullMatchingImages") or [], pg.get("partialMatchingImages") or []
        if not url.startswith("http"):
            continue
        if not (full or part):
            other += 1  # a page about the label, not about this picture
            continue
        title = re.sub(r"<[^>]+>", "", str(pg.get("pageTitle") or ""))  # it marks the match
        img = str((full or part)[0].get("url") or "")
        pages.append({"url": url, "title": " ".join(title.split()), "image": img,
                      "same": bool(full), "match": "full" if full else "partial",
                      "from": "image search"})  # fmt: skip
    pages.sort(key=lambda p: not p["same"])  # full matches first, Google's order kept within
    imgs = {k: [str(x.get("url")) for x in web.get(f"{k}MatchingImages") or [] if x.get("url")]
            for k in ("full", "partial")}  # fmt: skip
    names: list[str] = []
    for u in [*imgs["full"], *(p["image"] for p in pages if p["same"]), *imgs["partial"],
              *(p["image"] for p in pages if not p["same"])]:  # fmt: skip
        names.append(image_name(str(u)))
    names += [str(p["title"])[:100] for p in pages]
    names = list(dict.fromkeys(n for n in names if n))
    ents = [{"name": str(e.get("description")), "score": round(float(e.get("score") or 0), 2)}
            for e in web.get("webEntities") or [] if e.get("description")]  # fmt: skip
    return {
        "pages": pages, "labels": [str(x.get("label")) for x in web.get("bestGuessLabels") or []
                                   if x.get("label")],
        "names": names[:NAMES_MAX], "entities": ents, "images": imgs,
        "similar": [str(x.get("url")) for x in web.get("visuallySimilarImages") or []
                    if x.get("url")],
        "other_pages": other,
    }  # fmt: skip


def _jpeg(png: bytes) -> bytes:
    """The photo as a JPEG for the image search: the same picture, a fraction of the bytes."""
    from PIL import Image

    out = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


def reverse_search(params: Any, png: bytes) -> dict[str, Any]:
    """A real search by image (ADR-092, ADR-112): Google Cloud Vision's web detection, the web
    index behind Google Lens's exact matches (not Lens's product index). Asks for
    `suggest.reverse_max` results of each kind (with 5, only the label's pages came back) and
    returns read_web_detection's reading. Its fee goes into the month's ledger."""
    import base64
    import urllib.error
    import urllib.request

    from coverengine import spend
    from coverengine.ai import _key
    from coverengine.errors import CoverError

    spend.guard(params)
    n = int(params["suggest.reverse_max"])  # type: ignore[arg-type]
    body = {"requests": [{"image": {"content": base64.b64encode(_jpeg(png)).decode()},
                          "features": [{"type": "WEB_DETECTION", "maxResults": n}]}]}  # fmt: skip
    req = urllib.request.Request(
        "https://vision.googleapis.com/v1/images:annotate", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": _key("google_vision")})  # fmt: skip
    timeout = float(params["suggest.ai_timeout_s"])  # type: ignore[arg-type]
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - Google's API
            reply = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise CoverError(f"the image search did not answer: HTTP {exc.code}") from None
    except (OSError, ValueError) as exc:
        raise CoverError(f"the image search did not answer: {type(exc).__name__}") from None
    spend.record_eur("google vision web", float(params["suggest.reverse_eur"]),  # type: ignore[arg-type]
                     "suggest reverse")  # fmt: skip
    return read_web_detection(((reply.get("responses") or [{}])[0]).get("webDetection") or {})


COMPARE = """Picture 0 is a customer's photo of their outdoor furniture. The other pictures are
products found on the web (each introduced by its number and name). For each, judge:
- "same": true only if it is the very same product model AND the same size variant (same number
  of seats or modules, same table shape) as in picture 0; colour, cushion fabric, the photo's
  angle and the setting may differ.
- "similarity": 0-1, how alike the shape is for a tight-fitting cover: outline, proportions,
  arms, back height, legs, number of seats (1 = identical shape, 0.5 = same type but clearly
  different shape, 0 = a different kind of furniture).
Answer JSON only: {"candidates": [{"n": <number>, "same": <true/false>, "similarity": <0-1>,
"why": "<a few words>"}]}"""


def compare(params: Any, png: bytes, cands: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """The candidates' own pictures held against the customer's photo by the vision model
    (ADR-092): {index in cands: {"same", "similarity", "why"}} for those with a picture."""
    parts: list[dict[str, Any]] = [{"text": "Picture 0: the customer's photo"}, _png_part(png)]
    shown = []
    for i, c in enumerate(cands):
        if c.get("png"):
            parts += [{"text": f"Picture {i + 1}: {c.get('title') or c['url']}"},
                      _png_part(c["png"])]  # fmt: skip
            shown.append(i)
    if not shown:
        return {}
    parts.append({"text": COMPARE})
    timeout = float(params["suggest.ai_timeout_s"])  # type: ignore[arg-type]
    doc = _json_in(gemini(params, parts, "suggest compare", timeout)["text"])
    out: dict[int, dict[str, Any]] = {}
    for row in doc.get("candidates") or []:
        try:
            i = int(row.get("n")) - 1
            sim = max(0.0, min(1.0, float(row.get("similarity") or 0)))
        except (TypeError, ValueError, AttributeError):
            continue
        if i in shown:
            out[i] = {"same": row.get("same") is True, "similarity": sim,
                      "why": str(row.get("why") or "")[:120]}  # fmt: skip
    return out


def _small_png(data: bytes, edge: int) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(photo_png(data))).convert("RGB")
    im.thumbnail((edge, edge))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue()


def _candidate(pg: dict[str, Any], timeout: float, page_max: int, img_max: int,
               edge: int) -> dict[str, Any]:  # fmt: skip
    """One search result made ready: its page's facts (or the sizes the search read, when the
    shop refuses robots) and its main picture, small, for the comparison."""
    c: dict[str, Any] = {"url": pg["url"], "title": pg.get("title") or "", "facts": None}
    f: dict[str, Any] = {}
    try:
        final, html = fetch(pg["url"], PAGE_TYPES, timeout, page_max)
        f = page_facts(html, final)
        c["url"], c["title"] = final, f.get("title") or c["title"]
    except SuggestError:  # many shops refuse robots: the search read it
        pass
    if (f.get("product") or {}).get("sizes") or f.get("sizes_text"):
        c["facts"] = f
    elif pg.get("sizes_cm"):
        c["facts"] = {"url": c["url"], "title": c["title"], "image": "",
                      "product": {"name": c["title"], "sizes": pg["sizes_cm"]},
                      "sizes_text": [], "read_by": "the web search"}  # fmt: skip
    for img in dict.fromkeys(x for x in (f.get("image"), pg.get("image")) if x):
        try:
            _, raw = fetch(str(img), IMAGE_TYPES, timeout, img_max)
            c["png"] = _small_png(raw, edge)
            # the page's own picture, or the one the search by image matched to the photo (which
            # says nothing about what the page sells: a category page shows it too)
            c["pic"] = "page" if img == f.get("image") else (
                "match" if pg.get("from") == "image search" else "search")  # fmt: skip
            break
        except (SuggestError, OSError, ValueError):
            continue
    return c


def _search(params: Any, png: bytes, ident: dict[str, Any], brand: bool) -> list[dict[str, Any]]:
    """One search; a failed one finds nothing (the other may still find something)."""
    from coverengine.errors import CoverError

    try:
        return search_comparable(params, png, ident, brand)
    except (CoverError, OSError, ValueError) as exc:
        log.warning("suggest search: %s", exc)
        return []


NOTHING_BY_IMAGE: dict[str, Any] = {"pages": [], "labels": [], "names": [], "entities": [],
                                    "images": {"full": [], "partial": []}, "similar": [],
                                    "other_pages": 0}  # fmt: skip


def _reverse(params: Any, png: bytes) -> dict[str, Any]:
    """The search by image when it is on; off, or failing, it finds nothing."""
    from coverengine.errors import CoverError

    if not bool(params["suggest.reverse_search"]):
        return {**NOTHING_BY_IMAGE, "off": True}
    try:
        return {**NOTHING_BY_IMAGE, **reverse_search(params, png)}
    except (CoverError, OSError, ValueError) as exc:
        log.warning("suggest reverse search: %s", exc)
        return {**NOTHING_BY_IMAGE, "error": str(exc)[:200]}


def _named(ident: dict[str, Any], title: str) -> bool:
    """The page's name carries the recognised brand and model."""
    b = str(ident.get("brand") or "")
    return bool(b) and b.casefold() in title.casefold() and _says_model(ident, title)


def _says_model(ident: dict[str, Any], *texts: str) -> bool:
    """One of the texts (a page's title, its address) names the recognised model (or one of
    them: "Dolce / Nova" is a chair at a table)."""

    def words(t: str) -> str:
        return " " + re.sub(r"[^a-z0-9]+", " ", t.casefold()).strip() + " "

    models = [words(m) for m in re.split(r"[/,&+]", str(ident.get("model") or ""))]
    models = [m for m in models if m.strip()]
    return any(m in words(t) for m in models for t in texts)


def _short_name(title: str, ident: dict[str, Any]) -> str:
    """A page's title without the shop's name: "Marolo daybed - SUNS Outdoor Lifestyle" ->
    "Marolo daybed" (the part that names the model, else the first)."""
    parts = [p.strip() for p in re.split(r"\s+[|–—-]\s+", title) if p.strip()] or [title]
    return next((p for p in parts if _says_model(ident, p)), parts[0])


def _by_image_first(pages: list[dict[str, Any]], ident: dict[str, Any]) -> list[dict[str, Any]]:
    """The search by image's pages: those naming the recognised model first, then the full
    matches (a page showing the very picture), else in Google's order (ADR-112)."""

    def key(i: int) -> tuple[bool, bool, int]:
        return (not _says_model(ident, pages[i]["title"], pages[i]["url"]),
                not pages[i]["same"], i)  # fmt: skip

    return [pages[i] for i in sorted(range(len(pages)), key=key)]


def find_comparable(
    params: Any, png: bytes, timeout: float, page_max: int, img_max: int,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:  # fmt: skip
    """A photo alone (ADR-087, ADR-092, ADR-112): search by image, identify the furniture (brand
    and model when it can, helped by the names of the pictures that match), search the web with
    targeted queries, hold each result's picture against the photo, and keep
    - "recognised": the very same product (the comparison says so, or its page carries the
      brand and model the photo was recognised as with high confidence);
    - else "comparable": the most similar product with written sizes, when similar enough;
    - else nothing (the photo's own estimates; better than a product that makes no sense).
    Returns {"ident", "facts", "recognised", "comparable", "candidates"}; `trace` (the admin's
    photo test) gets each step's own result."""
    from concurrent.futures import ThreadPoolExecutor

    from coverengine.errors import CoverError

    trace = trace if trace is not None else {}
    out: dict[str, Any] = {"ident": {}, "facts": None, "recognised": None, "comparable": None,
                           "candidates": []}  # fmt: skip
    # the search by image first (a second or two): the names of the pictures that match the
    # photo are the best hint of its brand and model there is (ADR-112)
    reverse = {**NOTHING_BY_IMAGE, **_reverse(params, png)}
    trace["image_search"] = reverse
    try:
        ident = identify(params, png, reverse["names"])
    except CoverError as exc:
        ident = {}  # the search still sees the photo
        trace["identify_error"] = str(exc)
    # Google's best-guess label ("studio couch", "swimming pool") is no query any more: on 15
    # photos it never named the product and steered the search away (ADR-112)
    out["ident"] = trace["identify"] = ident
    # two searches side by side: the recognised brand and model (when there is a guess) and the
    # look alone; their results taken in turns, after the pages showing the very picture. When
    # the search by image already shows a page of the recognised model, the search by look
    # (for a similar product) is not needed: one search fee less (ADR-112)
    sure = ident.get("brand_confidence", 0) >= float(params["suggest.brand_min"]) and any(  # type: ignore[arg-type]
        _says_model(ident, p["title"], p["url"]) for p in reverse["pages"]
    )
    focus = (
        [True] if sure and ident.get("brand") else [True, False] if ident.get("brand") else [False]
    )
    with ThreadPoolExecutor(max_workers=len(focus)) as pool:
        search = _carry(_search)
        found = list(pool.map(lambda b: search(params, png, ident, b), focus))
    trace["searches"] = {("brand and model" if b else "look"): r
                         for b, r in zip(focus, found, strict=True)}  # fmt: skip
    runs = [_by_image_first(reverse["pages"], ident), *found]
    pages, seen = [], set()
    for i in range(max(len(r) for r in runs)):
        for r in runs:
            if i < len(r) and r[i]["url"] not in seen:
                seen.add(r[i]["url"])
                pages.append(r[i])
    pages = pages[: int(params["suggest.search_pages"])]  # type: ignore[arg-type]
    if not pages:
        return out
    edge = int(params["suggest.compare_px"])  # type: ignore[arg-type]
    with ThreadPoolExecutor(max_workers=len(pages)) as pool:
        cands = list(pool.map(lambda pg: _candidate(pg, timeout, page_max, img_max, edge), pages))
    try:
        scores = compare(params, png, cands)
    except CoverError:
        scores = {}
    same_min = float(params["suggest.same_min"])  # type: ignore[arg-type]
    similar_min = float(params["suggest.similar_min"])  # type: ignore[arg-type]
    brand_min = float(params["suggest.brand_min"])  # type: ignore[arg-type]
    for i, (c, pg) in enumerate(zip(cands, pages, strict=True)):
        s = scores.get(i)
        c["similarity"] = s["similarity"] if s else None
        c["why"] = s["why"] if s else ""
        if s and c.get("pic") == "match":  # the picture the search by image matched, not the
            # page's own: it is the photo itself, so the page counts only when it names the model
            c["same"] = (
                s["same"]
                and s["similarity"] >= same_min
                and _says_model(ident, c["title"], c["url"])
            )
        elif s:  # seen side by side: the comparison decides
            c["same"] = s["same"] and s["similarity"] >= same_min
        else:  # no picture to compare: only the recognised name on the page counts
            c["same"] = (bool(pg.get("same")) and ident.get("brand_confidence", 0) >= brand_min
                         and _named(ident, c["title"]))  # fmt: skip
    out["candidates"] = [{k: v for k, v in c.items() if k not in ("png", "facts")} | {
        "sizes": bool(c["facts"])} for c in cands]  # fmt: skip
    trace["candidates"] = [_traced(c, pg) for c, pg in zip(cands, pages, strict=True)]
    rank = sorted(range(len(cands)), key=lambda i: -(cands[i]["similarity"] or 0))
    # the very product: the one with written sizes first, then the most alike
    same = sorted((i for i in rank if cands[i]["same"]), key=lambda i: not cands[i]["facts"])
    alike = [i for i in rank if cands[i]["facts"] and (cands[i]["similarity"] or 0) >= similar_min]
    if same:
        c, pg = cands[same[0]], pages[same[0]]
        # the name as the page gives it (the photo's own guess may have been another brand)
        brand = str(pg.get("brand") or "") or (ident.get("brand") if _named(ident, c["title"])
                                               else "")  # fmt: skip
        name = _short_name(str(pg.get("title") or c["title"]), ident)
        if brand and brand.casefold() not in name.casefold():
            name = f"{brand} {name}"
        out["recognised"] = {"url": c["url"], "title": c["title"], "name": name,
                             "brand": brand or "", "similarity": c["similarity"]}  # fmt: skip
        if c["facts"]:
            out["facts"] = {**c["facts"], "relation": "the same product as in the photo"}
    if out["facts"] is None and alike:
        c = cands[alike[0]]
        out["comparable"] = {"url": c["url"], "title": c["title"], "similarity": c["similarity"]}
        out["facts"] = {**c["facts"], "relation": "a SIMILAR product, not the customer's own"}
    return out


def _traced(c: dict[str, Any], pg: dict[str, Any]) -> dict[str, Any]:
    """One candidate as the photo test shows it: where it came from, the picture compared (a
    small JPEG of the web's picture, never the customer's photo), the score and the sizes read."""
    import base64

    from PIL import Image

    thumb = ""
    if c.get("png"):
        im = Image.open(io.BytesIO(c["png"])).convert("RGB")
        im.thumbnail((TRACE_THUMB_PX, TRACE_THUMB_PX))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=80)
        thumb = "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    f = c.get("facts") or {}
    return {"url": c["url"], "title": c["title"], "from": pg.get("from") or "web search",
            "match": pg.get("match") or "", "picture": c.get("pic") or "", "thumb": thumb,
            "similarity": c.get("similarity"), "same": c.get("same"), "why": c.get("why", ""),
            "sizes": (f.get("product") or {}).get("sizes") or {},
            "sizes_text": (f.get("sizes_text") or [])[:3]}  # fmt: skip


def proposal(ans: dict[str, Any]) -> dict[str, Any]:
    """The AI's answer checked against the configurator: a known product, every size within its
    range (clipped and flagged), and which sizes the customer must check."""
    from coverengine.quote import PRODUCTS

    product = str(ans.get("product") or "")
    if product not in PRODUCTS:
        raise SuggestError("we could not tell which furniture this is: please choose it below")
    got = ans.get("fields") if isinstance(ans.get("fields"), dict) else {}
    sizes: dict[str, Any] = {}
    flags: dict[str, list[str]] = {}
    for f, (d, lo, hi) in PRODUCTS[product]["fields"].items():
        item = got.get(f) if isinstance(got, dict) else None
        if not isinstance(item, dict) or "value" not in item:
            sizes[f] = d
            # a yes/no the AI did not mention keeps its default unflagged (a lounger without a
            # word about a headrest is a flat one); every size it did not give must be checked
            flags[f] = [] if lo is None else ["default"]
            continue
        src = str(item.get("source") or "photo")
        try:
            conf = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if lo is None:
            sizes[f] = bool(item["value"])
            flags[f] = [] if src == "page" else ["estimate"]
            continue
        try:
            v = float(item["value"])
        except (TypeError, ValueError):
            sizes[f] = d
            flags[f] = ["default"]
            continue
        mark = [] if src == "page" and conf >= CHECK_BELOW else ["estimate"]
        if v < lo or v > hi:
            mark.append("clipped")
            v = min(max(v, lo), hi)
        sizes[f] = round(v)
        flags[f] = mark
    # a size that belongs to an unticked yes/no (the headrest of a flat lounger) is not asked
    requires = PRODUCTS[product].get("requires", {})
    for f, need in requires.items():
        if not sizes.get(need):
            flags[f] = []
    check = [f for f, m in flags.items() if m]
    return {"product": product, "label": PRODUCTS[product]["label"], "sizes": sizes,
            "flags": flags, "check": check, "summary": str(ans.get("summary") or "")[:400],
            "notes": str(ans.get("notes") or "")[:600]}  # fmt: skip


def read(
    p: Any, pngs: list[bytes], url: str, lang: str, trace: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The suggestion for these photos and/or this link: (the proposal, the page's facts).
    `trace` (the admin's photo test, ADR-112) gets each step's own result."""
    from coverengine.errors import CoverError

    limit_bytes = int(p["suggest.photo_max_bytes"])  # type: ignore[arg-type]
    timeout = float(p["suggest.fetch_timeout_s"])  # type: ignore[arg-type]
    page_max = int(p["suggest.fetch_max_bytes"])  # type: ignore[arg-type]
    facts = None
    url = (url or "").strip()
    if url:
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        final, html = fetch(url, PAGE_TYPES, timeout, page_max)
        facts = page_facts(html, final)
        if trace is not None:
            trace["page"] = facts
        if facts["image"] and len(pngs) < MAX_PHOTOS:
            try:
                _, img = fetch(facts["image"], IMAGE_TYPES, timeout, limit_bytes)
                pngs = [*pngs, photo_png(img)]
            except SuggestError:
                pass  # the page's facts alone
    found: dict[str, Any] = {}
    if not facts and pngs and bool(p["suggest.search"]):
        # a photo alone: recognise it, or start from a similar product's written sizes
        # (ADR-087, ADR-092)
        try:
            found = find_comparable(p, pngs[0], timeout, page_max, limit_bytes, trace)
            facts = found["facts"]
        except (CoverError, OSError, ValueError) as exc:
            log.warning("suggest search: %s", exc)
            found = {}  # the photo alone, as before
            if trace is not None:
                trace["search_error"] = str(exc)[:200]
    ans = ask(p, pngs, facts, lang, hint=found.get("ident") or None)
    if trace is not None:
        trace["answer"] = ans
        trace["basis"] = {k: found.get(k) for k in ("recognised", "comparable")} | {
            "relation": (facts or {}).get("relation"),
            "url": (facts or {}).get("url"),
        }
    out = proposal(ans)
    out["recognised"] = found.get("recognised")
    out["comparable"] = found.get("comparable")
    mark = "recognised" if facts and found.get("recognised") else "comparable"
    if facts and (found.get("recognised") or found.get("comparable")):
        # sizes from a found page: a good start, still the customer checks them (a recognised
        # product may come in more sizes; a similar one is never their own)
        for f, marks in out["flags"].items():
            if marks is not None and f in (ans.get("fields") or {}):
                out["flags"][f] = sorted({*marks, mark})
        out["check"] = [f for f, m in out["flags"].items() if m]
    return out, facts


# ---- the endpoints ------------------------------------------------------------------------------


def install(app: FastAPI, auth: Any, data: Path, store: Any) -> None:
    from coverapi.security import _address
    from coverapi.shop import link_ok, shop_params

    asked: dict[str, list[float]] = {}
    uploads: dict[str, list[float]] = {}
    sources = data / "order_sources"

    def visitor(request: Request) -> str:
        a = _address(request)
        if link_ok(auth, request):  # through the website: its visitor's own address
            a = request.headers.get("x-client-ip") or a
        return a

    @app.post("/api/shop/suggest")
    async def suggest(
        request: Request,
        url: str = Form(""),  # noqa: B008
        lang: str = Form("nl"),  # noqa: B008
        photos: list[UploadFile] = File(default_factory=list),  # noqa: B008
        website: str = Form(""),  # noqa: B008 - the honeypot: people never see it (ADR-103)
    ) -> dict[str, Any]:
        """Sizes suggested from a photo and/or a link (nothing is stored)."""
        from coverengine import match as mt
        from coverengine import spend
        from coverengine.errors import CoverError

        from coverapi import match_list

        if website:
            raise HTTPException(400, "this could not be sent")
        p = shop_params(auth)
        who, now = visitor(request), time.time()
        times = [t for t in asked.get(who, []) if now - t < DAY_S]
        if sum(now - t < HOUR_S for t in times) >= int(p["suggest.per_hour"]):  # type: ignore[arg-type]
            raise HTTPException(429, "you asked many times this hour; please choose by hand")
        if len(times) >= int(p["suggest.per_day"]):  # type: ignore[arg-type]
            raise HTTPException(429, "you asked many times today; please choose by hand")
        try:  # what this visitor's suggestions cost the AI today (ADR-103)
            spend.guard_visitor(p, who)
        except CoverError:
            raise HTTPException(429, "you asked many times today; please choose by hand") from None
        asked[who] = [*times, now]
        if len(asked) > 5000:  # noqa: PLR2004 - forget the visitors of yesterday
            for k in [k for k, v in asked.items() if now - v[-1] >= DAY_S]:
                del asked[k]
        if len(photos) > MAX_PHOTOS:
            raise HTTPException(400, f"at most {MAX_PHOTOS} photos")
        limit_bytes = int(p["suggest.photo_max_bytes"])  # type: ignore[arg-type]
        lang = lang if re.fullmatch(r"[a-z]{2}", lang or "") else "nl"
        try:
            pngs = []
            for ph in photos:
                raw = await ph.read(limit_bytes + 1)
                if len(raw) > limit_bytes:
                    raise SuggestError(f"a photo may be at most {limit_bytes // 1_000_000} MB")
                pngs.append(photo_png(raw))

            # the web and the AI take up to a minute: off the event loop, so the rest of the
            # app keeps answering meanwhile
            def read_for_visitor() -> tuple[dict[str, Any], dict[str, Any] | None]:
                with spend.for_visitor(who):  # every paid call on this visitor's line
                    return read(p, pngs, url, lang)

            out, facts = await run_in_threadpool(read_for_visitor)
        except SuggestError as exc:
            raise HTTPException(400, str(exc)) from None
        except CoverError as exc:  # the month's AI budget, or the AI did not answer
            msg = str(exc)
            log.warning("suggest: %s", msg)  # the reason only (no photo, no key)
            if "budget" in msg:
                raise HTTPException(503, "this service is resting for now; please choose by "
                                         "hand below") from None  # fmt: skip
            raise HTTPException(502, "we could not read it just now; please choose by hand"
                                ) from None  # fmt: skip
        out["source"] = {"url": facts["url"] if facts else None,
                         "title": facts["title"] if facts else None,
                         "photos": len(photos)}  # fmt: skip
        try:  # an existing cover that fits these sizes (ADR-064)
            rec = out.get("recognised") or {}
            hint = " ".join(str(x or "") for x in (out["source"]["title"], rec.get("name"),
                                                     rec.get("title")))  # fmt: skip
            r = mt.match(
                out["product"],
                out["sizes"],
                store.models,
                p,
                top=1,
                listing=match_list.for_data(data),
                hint=hint,
            )
            best = r["matches"][0] if r["matches"] else None
            out["match"] = best if best and r["decision"] != "custom" else None
        except (ValueError, CoverError, KeyError):
            out["match"] = None
        return out

    @app.post("/api/admin/shop/photo-test")
    async def photo_test(
        request: Request,
        url: str = Form(""),  # noqa: B008
        lang: str = Form("nl"),  # noqa: B008
        photos: list[UploadFile] = File(default_factory=list),  # noqa: B008
    ) -> dict[str, Any]:
        """The admin's photo test (ADR-112): the customer's flow on a photo and/or a link, with
        each step's own result (image search, identification, searches, comparison, the AI's
        answer, the proposal) and what it cost. Nothing is kept: the photo lives only for this
        request, the answer goes back to the admin's browser alone; the ledger gets the cost."""
        import secrets

        from coverengine import spend
        from coverengine.errors import CoverError

        from coverapi.security import require

        require(request, "admin")
        if len(photos) > MAX_PHOTOS:
            raise HTTPException(400, f"at most {MAX_PHOTOS} photos")
        p = shop_params(auth)
        limit_bytes = int(p["suggest.photo_max_bytes"])  # type: ignore[arg-type]
        lang = lang if re.fullmatch(r"[a-z]{2}", lang or "") else "nl"
        trace: dict[str, Any] = {}
        tag = f"photo-test-{secrets.token_hex(8)}"  # this test's own line in the ledger
        t0 = time.time()
        try:
            pngs = []
            for ph in photos:
                raw = await ph.read(limit_bytes + 1)
                if len(raw) > limit_bytes:
                    raise SuggestError(f"a photo may be at most {limit_bytes // 1_000_000} MB")
                pngs.append(photo_png(raw))

            def run() -> tuple[dict[str, Any], dict[str, Any] | None]:
                with spend.for_visitor(tag):
                    return read(p, pngs, url, lang, trace)

            out, _facts = await run_in_threadpool(run)
            error = None
        except (SuggestError, CoverError) as exc:
            out, error = None, str(exc)
        return {"proposal": out, "error": error, "trace": trace,
                "seconds": round(time.time() - t0, 1),
                "cost_eur": round(spend.visitor_eur(tag), 4),
                "settings": {k: p[f"suggest.{k}"] for k in (
                    "reverse_search", "reverse_max", "search_pages", "same_min",
                    "similar_min", "brand_min")}}  # fmt: skip

    @app.post("/api/shop/order/{token}/source")
    async def order_source(token: str, request: Request,
                           photos: list[UploadFile] = File(...)) -> dict[str, Any]:  # noqa: B008  # fmt: skip
        """The photos the customer started from, kept with their order for the workshop."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,60}", token):
            raise HTTPException(404, "no such order")
        who, now = visitor(request), time.time()
        times = [t for t in uploads.get(who, []) if now - t < HOUR_S]
        if len(times) >= MAX_SOURCE_UPLOADS:  # a public shop: no endless uploads (ADR-103)
            raise HTTPException(429, "too many uploads; try again later")
        uploads[who] = [*times, now]
        with sqlite3.connect(auth.path) as db:
            row = db.execute("SELECT id FROM orders WHERE token=?", (token,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such order")
        p = shop_params(auth)
        limit_bytes = int(p["suggest.photo_max_bytes"])  # type: ignore[arg-type]
        sources.mkdir(parents=True, exist_ok=True)
        kept = 0
        for i, ph in enumerate(photos[:MAX_PHOTOS]):
            raw = await ph.read(limit_bytes + 1)
            if len(raw) > limit_bytes:
                continue
            try:
                png = photo_png(raw)
            except SuggestError:
                continue
            (sources / f"order-{row[0]}-{i + 1}.png").write_bytes(png)
            kept += 1
        return {"kept": kept}
