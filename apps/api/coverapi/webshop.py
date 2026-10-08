"""The webshop's public API and the customer requests (ADR-061, docs/plans/webshop-configurator.md).

`/api/public/v1/...` works without a login:

- options: what can be covered, the fields and the options;
- quote: a proposal from rough sizes (pieces, fabric, price), with a 3D preview;
- preview/<id>.glb: that preview, for the webshop's own viewer;
- request: the customer asks for the cover; it is stored and mailed.

A webshop's server calls it with an API key (X-Api-Key, made on the admin page). Our own
configurator page (#/configure, also in an iframe) calls it from our own address without a
key. Every address is limited to QUOTES_PER_MINUTE. Nothing internal can be reached here: no
models, no patterns, no users. The internal cost price is only on the admin page.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

QUOTES_PER_MINUTE = 30  # per address
KEYS_SETTING = "webshop_keys"  # [{name, hash, created}]
ORIGINS_SETTING = "embed_origins"  # the webshop addresses that may show the configurator
REQUEST_EMAIL_SETTING = "request_email"
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.I)

REQUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL NOT NULL,
  quote_id TEXT NOT NULL,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  note TEXT,
  source TEXT,
  status TEXT NOT NULL DEFAULT 'new'
)"""


class QuoteRequest(BaseModel):
    product: str = Field(max_length=40)
    sizes: dict[str, Any] = Field(default_factory=dict)
    colour: str | None = Field(default=None, max_length=40)
    vents: bool = True


class CustomerRequest(BaseModel):
    quote_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=2000)


class KeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class WebshopSettings(BaseModel):
    embed_origins: list[str] | None = None
    request_email: str | None = None
    revoke: str | None = None


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def install(app: FastAPI, auth: Any, quotes_dir: Path, models_dir: Path) -> None:
    from coverengine import quote as q
    from coverengine.errors import CoverError
    from coverengine.params import Registry

    from coverapi import mailer

    quotes_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(auth.path) as db:
        db.execute(REQUESTS_TABLE)
    recent: dict[str, deque[float]] = defaultdict(deque)

    def params() -> Any:
        return Registry.load(None).resolve()

    def caller(request: Request) -> str:
        """'key:<name>' for a webshop with a valid key, 'site' for our own pages; else 401."""
        key = request.headers.get("x-api-key")
        if key:
            for k in auth.setting(KEYS_SETTING, []) or []:
                if secrets.compare_digest(k["hash"], hash_key(key)):
                    return f"key:{k['name']}"
            raise HTTPException(401, "unknown API key")
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if origin and host and host in origin:
            return "site"
        if not origin and request.method == "GET":
            return "site"  # a plain GET (the preview file in a viewer)
        raise HTTPException(401, "an API key is needed (X-Api-Key)")

    def limit(request: Request) -> None:
        from coverapi.security import _address

        now, a = time.time(), _address(request)
        times = recent[a]
        while times and now - times[0] > 60:  # noqa: PLR2004 - a minute
            times.popleft()
        if len(times) >= QUOTES_PER_MINUTE:
            raise HTTPException(429, "too many requests; try again in a minute")
        times.append(now)

    def public_quote(full: dict[str, Any]) -> dict[str, Any]:
        """What the customer sees: no cost price, no labour."""
        price = full["price"]
        out = {k: v for k, v in full.items() if k != "price"}
        out["price"] = {
            "sale_eur": price["sale_eur"],
            "sale_ex_vat_eur": price["sale_ex_vat_eur"],
            "vat_eur": price["vat_eur"],
            "indicative": price["placeholder_prices"],
        }
        return out

    @app.get("/api/public/v1/options")
    def options(request: Request) -> dict[str, Any]:
        caller(request)
        return q.options(params())

    @app.post("/api/public/v1/quote")
    def make_quote(req: QuoteRequest, request: Request) -> dict[str, Any]:
        who = caller(request)
        limit(request)
        p = params()
        given = {**req.sizes, "vents": req.vents, "colour": req.colour}
        try:
            from coverapi.prices import current

            full = q.proposal(req.product, given, p, current(auth))
            glb = q.preview_glb(req.product, given, p)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        qid = q.new_id()
        full["id"] = qid
        full["near"] = q.nearest(req.product, given, models_dir)
        record = {"time": time.time(), "by": who, "input": req.model_dump(), "quote": full}
        (quotes_dir / f"{qid}.json").write_text(json.dumps(record), encoding="utf-8")
        (quotes_dir / f"{qid}.glb").write_bytes(glb)
        out = public_quote(full)
        out["preview"] = f"/api/public/v1/preview/{qid}.glb"
        return out

    @app.get("/api/public/v1/preview/{qid}.glb")
    def preview(qid: str, request: Request) -> Response:
        caller(request)
        if not re.fullmatch(r"[0-9a-f]{16}", qid):
            raise HTTPException(404, "no such preview")
        path = quotes_dir / f"{qid}.glb"
        if not path.is_file():
            raise HTTPException(404, "no such preview")
        return Response(path.read_bytes(), media_type="model/gltf-binary")

    @app.post("/api/public/v1/request")
    def customer_request(req: CustomerRequest, request: Request) -> dict[str, Any]:
        who = caller(request)
        limit(request)
        if not EMAIL.match(req.email.strip()):
            raise HTTPException(400, "please give a valid e-mail address")
        path = quotes_dir / f"{req.quote_id}.json"
        if not path.is_file():
            raise HTTPException(404, "no such proposal")
        record = json.loads(path.read_text(encoding="utf-8"))
        with sqlite3.connect(auth.path) as db:
            cur = db.execute(
                "INSERT INTO requests (created, quote_id, name, email, phone, note, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    time.time(),
                    req.quote_id,
                    req.name.strip(),
                    req.email.strip(),
                    (req.phone or "").strip(),
                    (req.note or "").strip(),
                    who,
                ),  # fmt: skip
            )
            rid = cur.lastrowid
        qd = record["quote"]
        to = auth.setting(REQUEST_EMAIL_SETTING, "rick@s2dio.industries")
        if mailer.configured(auth):
            try:
                mailer.send(
                    auth, to, f"Cover request #{rid}: {qd['product']} from {req.name.strip()}",
                    f"A customer asks for a cover ({who}).\n\n"
                    f"Name: {req.name}\nE-mail: {req.email}\nPhone: {req.phone or '-'}\n"
                    f"Note: {req.note or '-'}\n\nProduct: {qd['product']} ({qd['shape']})\n"
                    f"Sizes (cm, with room): {json.dumps(qd['sizes_cm'])}\n"
                    f"Colour: {qd['colour']}\nPieces: {len(qd['pieces'])}, fabric "
                    f"{qd['fabric_m2']} m2 ({qd['roll_m']} m of roll)\n"
                    f"Cost price: EUR {qd['price']['cost_eur']}, selling price EUR "
                    f"{qd['price']['sale_eur']} incl. VAT"
                    + (" (indicative)" if qd["price"]["placeholder_prices"] else "") + "\n\n"
                    "All requests: the admin page, Requests.\n",
                )  # fmt: skip
            except Exception:  # noqa: BLE001 - the request is stored; the mail is a courtesy
                pass
        return {"request": rid, "message": "Thank you: we have your request and will contact you."}

    @app.get("/api/admin/requests")
    def requests_list(request: Request) -> dict[str, Any]:
        from coverapi.security import require

        require(request, "admin")
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = [
                dict(r) for r in db.execute("SELECT * FROM requests ORDER BY id DESC LIMIT 200")
            ]
        for r in rows:
            path = quotes_dir / f"{r['quote_id']}.json"
            r["quote"] = json.loads(path.read_text())["quote"] if path.is_file() else None
        return {"requests": rows}

    @app.post("/api/admin/webshop/keys")
    def new_key(req: KeyRequest, request: Request) -> dict[str, Any]:
        from coverapi.security import require

        admin = require(request, "admin")
        key = "csk_" + secrets.token_urlsafe(32)
        keys = [k for k in (auth.setting(KEYS_SETTING, []) or []) if k["name"] != req.name]
        keys.append({"name": req.name, "hash": hash_key(key), "created": time.time()})
        auth.set_setting(KEYS_SETTING, keys)
        auth.log(admin, "webshop key made", {"name": req.name})
        return {"name": req.name, "key": key, "note": "shown once: store it in the webshop now"}

    @app.get("/api/admin/webshop")
    def webshop_settings(request: Request) -> dict[str, Any]:
        from coverapi.security import require

        require(request, "admin")
        return {
            "keys": [
                {"name": k["name"], "created": k["created"]}
                for k in auth.setting(KEYS_SETTING, []) or []
            ],  # fmt: skip
            "embed_origins": auth.setting(ORIGINS_SETTING, []) or [],
            "request_email": auth.setting(REQUEST_EMAIL_SETTING, "rick@s2dio.industries"),
        }

    @app.put("/api/admin/webshop")
    def change_webshop(req: WebshopSettings, request: Request) -> dict[str, Any]:
        from coverapi.security import require

        admin = require(request, "admin")
        if req.embed_origins is not None:
            ok = [o.strip().rstrip("/") for o in req.embed_origins if o.strip()]
            bad = [o for o in ok if not re.fullmatch(r"https://[a-z0-9.-]+(:\d+)?", o, re.I)]
            if bad:
                raise HTTPException(
                    400, f"an address looks like https://shop.example.com: {bad[0]}"
                )
            auth.set_setting(ORIGINS_SETTING, ok)
        if req.request_email is not None:
            if not EMAIL.match(req.request_email.strip()):
                raise HTTPException(400, "not an e-mail address")
            auth.set_setting(REQUEST_EMAIL_SETTING, req.request_email.strip())
        if req.revoke:
            keys = [k for k in (auth.setting(KEYS_SETTING, []) or []) if k["name"] != req.revoke]
            auth.set_setting(KEYS_SETTING, keys)
        auth.log(admin, "webshop settings", req.model_dump())
        return webshop_settings(request)
