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
  where it came from. A number written on the page beats an estimate from a picture; a picture
  alone gives estimates the customer is asked to measure.
- The sizes are checked against config/quote_products.json (clipped to the range, flagged), and
  the proposal carries the existing cover that fits (coverengine.match), if any.
- Per visitor (the Worker's x-client-ip) at most `suggest.per_hour` suggestions an hour. Nothing
  is stored: a photo lives only for the request. When the customer orders, the browser sends
  the link and the summary with the order, and the photos to /api/shop/order/{token}/source.
"""

from __future__ import annotations

import http.client
import io
import ipaddress
import json
import re
import socket
import sqlite3
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

MAX_REDIRECTS = 3
MAX_PHOTOS = 3
HOUR_S = 3600.0
PAGE_TYPES = ("text/html", "application/xhtml+xml")
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/avif")  # many shops send AVIF
PHOTO_EDGE_PX = 1600  # photos are made this small before the AI sees them (fewer tokens)
SNIPPET_CHARS = 220
SNIPPETS_MAX = 10
FACTS_MAX_CHARS = 4000
CHECK_BELOW = 0.6  # a size the AI is less sure of than this must be checked
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
    rgb = im.convert("RGB")
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
    params: Any, photos: list[bytes], facts: dict[str, Any] | None, lang: str
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
    for png in photos:
        b = base64.b64encode(png).decode()
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}})
    if not parts:
        raise SuggestError("give a photo or a link")
    ans = ask_parts(vision, system, parts)
    ans.pop("_usage", None)
    return ans


SEARCH = """Identify the outdoor furniture in this photo as exactly as you can and search the web
for its product page, or the pages of the most similar products for sale, that state its sizes.
Read the sizes from those pages (in cm; convert inches and mm). Answer JSON only (no markdown):
{"what": "a short name of the furniture",
"pages": [{"url": "<the product page URL>", "title": "<product name>",
"sizes_cm": {"length": <n>, "width": <n>, "depth": <n>, "height": <n>, "seat_height": <n>}}]}
with at most 5 pages, the best match first; leave out sizes a page does not state."""


def search_comparable(params: Any, png: bytes) -> list[dict[str, Any]]:
    """Comparable products on the web for a photo (owner, 7 Oct 2026): Gemini with Google Search
    names product pages; the grounding's own links come first (they are real search results).
    The costs go into the month's ledger."""
    import base64
    import urllib.request

    from coverengine import spend
    from coverengine.ai import _key

    spend.guard(params)
    model = str(params["ai.vision_model"])
    body = {"contents": [{"parts": [
        {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
        {"text": SEARCH}]}], "tools": [{"google_search": {}}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}  # fmt: skip
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "x-goog-api-key": _key("gemini")})  # fmt: skip
    timeout = float(params["suggest.search_timeout_s"])  # type: ignore[arg-type]
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - Google's API
        reply = json.loads(r.read())
    u = reply.get("usageMetadata") or {}
    out_tokens = int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
    usage = {"prompt_tokens": u.get("promptTokenCount"), "completion_tokens": out_tokens}
    spend.record(params, model, usage, "suggest search")
    fee = float(params["suggest.search_eur"])  # type: ignore[arg-type]
    spend.record_eur(model + " search", fee, "suggest search")
    cand = (reply.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    pages: list[dict[str, Any]] = []
    # the named pages first (they carry the sizes the search read), then the search's own
    # results (real pages, without sizes)
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            for pg in json.loads(m.group(0)).get("pages") or []:
                if isinstance(pg, dict) and str(pg.get("url", "")).startswith("http"):
                    raw = pg.get("sizes_cm")
                    sizes: dict[str, Any] = raw if isinstance(raw, dict) else {}
                    kept = {k: v for k, v in sizes.items() if isinstance(v, int | float) and v > 0}
                    pages.append({"url": str(pg["url"]), "title": str(pg.get("title") or ""),
                                  "sizes_cm": kept})  # fmt: skip
        except json.JSONDecodeError:
            pass
    for ch in (cand.get("groundingMetadata") or {}).get("groundingChunks") or []:
        web = ch.get("web") or {}
        if str(web.get("uri", "")).startswith("http"):
            pages.append({"url": str(web["uri"]), "title": str(web.get("title") or "")})
    seen, out = set(), []
    for pg in pages:
        if pg["url"] not in seen:
            seen.add(pg["url"])
            out.append(pg)
    return out


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


# ---- the endpoints ------------------------------------------------------------------------------


def install(app: FastAPI, auth: Any, data: Path, store: Any) -> None:
    from coverapi.security import _address
    from coverapi.shop import link_ok, shop_params

    asked: dict[str, list[float]] = {}
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
    ) -> dict[str, Any]:
        """Sizes suggested from a photo and/or a link (nothing is stored)."""
        from coverengine import match as mt
        from coverengine.errors import CoverError

        p = shop_params(auth)
        who, now = visitor(request), time.time()
        times = [t for t in asked.get(who, []) if now - t < HOUR_S]
        if len(times) >= int(p["suggest.per_hour"]):  # type: ignore[arg-type]
            raise HTTPException(429, "you asked many times this hour; please choose by hand")
        asked[who] = [*times, now]
        if len(photos) > MAX_PHOTOS:
            raise HTTPException(400, f"at most {MAX_PHOTOS} photos")
        limit_bytes = int(p["suggest.photo_max_bytes"])  # type: ignore[arg-type]
        timeout = float(p["suggest.fetch_timeout_s"])  # type: ignore[arg-type]
        page_max = int(p["suggest.fetch_max_bytes"])  # type: ignore[arg-type]
        lang = lang if re.fullmatch(r"[a-z]{2}", lang or "") else "nl"
        try:
            pngs = []
            for ph in photos:
                raw = await ph.read(limit_bytes + 1)
                if len(raw) > limit_bytes:
                    raise SuggestError(f"a photo may be at most {limit_bytes // 1_000_000} MB")
                pngs.append(photo_png(raw))
            facts = None
            url = (url or "").strip()
            if url:
                if not re.match(r"^https?://", url, re.I):
                    url = "https://" + url
                final, html = fetch(url, PAGE_TYPES, timeout, page_max)
                facts = page_facts(html, final)
                if facts["image"] and len(pngs) < MAX_PHOTOS:
                    try:
                        _, img = fetch(facts["image"], IMAGE_TYPES, timeout, limit_bytes)
                        pngs.append(photo_png(img))
                    except SuggestError:
                        pass  # the page's facts alone
            comparable = None
            if not facts and pngs and bool(p["suggest.search"]):
                # a photo alone: a comparable product's page gives written sizes (ADR-087)
                try:
                    found = search_comparable(p, pngs[0])
                    for pg in found[: int(p["suggest.search_pages"])]:  # type: ignore[arg-type]
                        try:
                            final, html = fetch(pg["url"], PAGE_TYPES, timeout, page_max)
                            f = page_facts(html, final)
                        except SuggestError:  # many shops refuse robots: the search read it
                            f, final = {}, pg["url"]
                        if not ((f.get("product") or {}).get("sizes") or f.get("sizes_text")):
                            if not pg.get("sizes_cm"):
                                continue
                            f = {"url": final, "title": pg.get("title", ""), "image": "",
                                 "product": {"name": pg.get("title"), "sizes": pg["sizes_cm"]},
                                 "sizes_text": [], "read_by": "the web search"}  # fmt: skip
                        facts = f
                        comparable = {"url": final, "title": f.get("title") or pg.get("title")}
                        break
                except (CoverError, OSError, ValueError):
                    comparable = None  # the photo alone, as before
            ans = ask(p, pngs, facts, lang)
            out = proposal(ans)
            if comparable is not None:
                # a comparable product's sizes: a good start, never the customer's own
                for f, marks in out["flags"].items():
                    if marks is not None and f in (ans.get("fields") or {}):
                        out["flags"][f] = sorted({*marks, "comparable"})
                out["check"] = [f for f, m in out["flags"].items() if m]
                out["comparable"] = comparable
        except SuggestError as exc:
            raise HTTPException(400, str(exc)) from None
        except CoverError as exc:  # the month's AI budget, or the AI did not answer
            msg = str(exc)
            if "budget" in msg:
                raise HTTPException(503, "this service is resting for now; please choose by "
                                         "hand below") from None  # fmt: skip
            raise HTTPException(502, "we could not read it just now; please choose by hand"
                                ) from None  # fmt: skip
        out["source"] = {"url": facts["url"] if facts else None,
                         "title": facts["title"] if facts else None,
                         "photos": len(photos)}  # fmt: skip
        try:  # an existing cover that fits these sizes (ADR-064)
            r = mt.match(out["product"], out["sizes"], store.models, p, top=1)
            best = r["matches"][0] if r["matches"] else None
            out["match"] = best if best and r["decision"] != "custom" else None
        except (ValueError, CoverError, KeyError):
            out["match"] = None
        return out

    @app.post("/api/shop/order/{token}/source")
    async def order_source(token: str, request: Request,
                           photos: list[UploadFile] = File(...)) -> dict[str, Any]:  # noqa: B008  # fmt: skip
        """The photos the customer started from, kept with their order for the workshop."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,60}", token):
            raise HTTPException(404, "no such order")
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
