"""The B2B shop (ADR-104, docs/handbook/b2b.md): business customers (Sunsit, dealers) log in at
`/b2b` on the website's domain and order covers at their own price list, ex VAT, on account.

- **Business accounts** are their own thing, never studio users: a company (name, VAT number,
  contact, invoice address, delivery addresses, its price list and its own fixed prices, a
  status: requested → invited → active, or blocked / rejected) with one or more people who log
  in (`b2b_users`). Studio admins manage them (Admin → B2B customers): invite by mail, approve a
  request, block, see the orders. Nobody signs up alone: "request an account" lands in Admin.
- **Logins** follow the studio's rules (auth.py): scrypt hashes, a lock after LOCK_AFTER wrong
  passwords per person and twice that per address, one-time links for the first password and
  for a reset (by mail), every login and change in the audit log ("b2b:<e-mail>"). The session
  is its own cookie (`b2b_session`, HttpOnly, SameSite=Strict, Secure over https, path
  /api/b2b/ only), so a studio session never opens the B2B shop and the other way round.
  Changes need the session's CSRF token in a header and an Origin from our own domains.
- **Prices** come from the published price set (ADR-098): the company's price list (the b2b
  channel by default), always shown ex VAT; a fixed price in that list for a catalogue cover,
  then the company's own fixed price, win. The VAT is the list's rate, or none when the
  company's VAT is reverse-charged.
- **Orders** are "on account" (an invoice, no online payment; the switch for online payment is
  kept for later). Each line becomes an order in the studio's `orders` table, flagged B2B, so it
  follows the consumer orders' production flow (Admin → Orders, into production); the B2B order
  itself (PO number, delivery address, lines) is `b2b_orders`, which the customer's "previous
  orders" and "order again" read. A confirmation goes to the customer and to the alert address.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from coverapi.auth import (
    LOCK_AFTER,
    LOCK_MINUTES,
    SESSION_DAYS,
    check_password,
    hash_password,
    password_problem,
)

SETTING = "b2b"
DEFAULTS: dict[str, Any] = {
    "online_payment": False,  # later: Mollie for B2B too; now every order is on account
    "min_order_eur": 0,  # ex VAT; 0: no minimum (to confirm, QUESTIONS 72)
    "shipping_eur": 0,  # ex VAT per order on top; 0: shipping is in the price list's extras
    "payment_days": 30,  # the invoice's term, shown in the confirmation (to confirm)
    "auto_produce": True,  # an order on account goes into production at once, like a paid one
}
COOKIE = "b2b_session"
COOKIE_PATH = "/api/b2b/"
CSRF_HEADER = "x-b2b-csrf"
STATUSES = ("requested", "invited", "active", "blocked", "rejected")
TOKEN_HOURS = {"invite": 168, "reset": 2}
QTY_MAX = 999
HOUR_S, MINUTE_S, DAY_S = 3600, 60, 86400
PER_MINUTE = 60  # B2B calls per minute per address
PER_HOUR_MAILS = 5  # "forgot password" and "request an account" per address per hour
PERCENT = 100.0
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.I)
MODEL_ID = re.compile(r"^suns-[a-z0-9-]{1,120}$")
ACCESSORY_KEYS = ("balloon", "frame")

SCHEMA = """
CREATE TABLE IF NOT EXISTS b2b_companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL NOT NULL,
  updated REAL,
  name TEXT NOT NULL,
  vat_number TEXT,
  contact TEXT,
  email TEXT,
  phone TEXT,
  street TEXT,
  postcode TEXT,
  city TEXT,
  country TEXT,
  addresses TEXT NOT NULL DEFAULT '[]',
  price_list TEXT NOT NULL DEFAULT 'b2b',
  fixed TEXT NOT NULL DEFAULT '{}',
  reverse_charge INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  note TEXT,
  request TEXT
);
CREATE TABLE IF NOT EXISTS b2b_users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL,
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  lang TEXT,
  pw_hash TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created REAL NOT NULL,
  last_login REAL,
  failed INTEGER NOT NULL DEFAULT 0,
  locked_until REAL
);
CREATE TABLE IF NOT EXISTS b2b_sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created REAL NOT NULL,
  expires REAL NOT NULL,
  address TEXT
);
CREATE TABLE IF NOT EXISTS b2b_tokens (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  expires REAL NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS b2b_failures (
  address TEXT PRIMARY KEY,
  failed INTEGER NOT NULL,
  locked_until REAL
);
CREATE TABLE IF NOT EXISTS b2b_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created REAL NOT NULL,
  company_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  po TEXT,
  note TEXT,
  address TEXT NOT NULL,
  lines TEXT NOT NULL,
  net_eur REAL NOT NULL,
  vat_eur REAL NOT NULL,
  gross_eur REAL NOT NULL,
  payment TEXT NOT NULL
);
"""


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_of(token: str) -> str:
    """The CSRF token of a session: derived from its secret, so nothing more is stored."""
    return hmac.new(token.encode(), b"b2b-csrf", hashlib.sha256).hexdigest()


# ---- the requests' shapes -------------------------------------------------------------------


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    lang: str | None = Field(default=None, pattern=r"^[a-z]{2}$")


class EmailIn(BaseModel):
    email: str = Field(max_length=254)
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")


class PasswordIn(BaseModel):
    password: str = Field(max_length=200)


class ChangePasswordIn(BaseModel):
    old: str = Field(max_length=200)
    new: str = Field(max_length=200)


class Address(BaseModel):
    id: str | None = Field(default=None, max_length=40)
    label: str = Field(default="", max_length=80)
    name: str = Field(default="", max_length=120)
    street: str = Field(min_length=1, max_length=160)
    postcode: str = Field(min_length=1, max_length=20)
    city: str = Field(min_length=1, max_length=80)
    country: str = Field(min_length=2, max_length=2)


class AddressesIn(BaseModel):
    addresses: list[Address] = Field(max_length=50)


class RequestIn(BaseModel):
    company: str = Field(min_length=1, max_length=160)
    vat_number: str = Field(default="", max_length=40)
    contact: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    phone: str = Field(default="", max_length=40)
    street: str = Field(default="", max_length=160)
    postcode: str = Field(default="", max_length=20)
    city: str = Field(default="", max_length=80)
    country: str = Field(default="NL", min_length=2, max_length=2)
    message: str = Field(default="", max_length=2000)
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")


class QuoteIn(BaseModel):
    product: str = Field(max_length=40)
    sizes: dict[str, Any] = Field(default_factory=dict)
    colour: str | None = Field(default=None, max_length=40)
    vents: bool = True
    support: str = Field(default="none", pattern=r"^(none|balloons|frame)$")
    stock_model: str | None = Field(default=None, pattern=r"^suns-[a-z0-9-]{1,120}$")
    rain: bool = True  # the rain check (the catalogue's tested covers skip it)


class LineIn(BaseModel):
    quote_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    qty: int = Field(ge=1, le=QTY_MAX)


class OrderIn(BaseModel):
    lines: list[LineIn] = Field(min_length=1, max_length=100)
    address_id: str | None = Field(default=None, max_length=40)  # none: the invoice address
    po: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=2000)
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")
    payment: str = Field(default="account", pattern=r"^(account|online)$")


class CompanyIn(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    vat_number: str | None = Field(default=None, max_length=40)
    contact: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    street: str | None = Field(default=None, max_length=160)
    postcode: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, max_length=2)
    price_list: str | None = Field(default=None, max_length=20)
    fixed: dict[str, float] | None = None
    reverse_charge: bool | None = None
    addresses: list[Address] | None = None
    status: str | None = None
    note: str | None = Field(default=None, max_length=2000)


class NewCompanyIn(CompanyIn):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(max_length=254)  # the first person who logs in
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")
    send_invite: bool = True


class NewUserIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(default="", max_length=120)
    lang: str = Field(default="nl", pattern=r"^[a-z]{2}$")


class UserChangeIn(BaseModel):
    active: bool | None = None
    name: str | None = Field(default=None, max_length=120)


# ---- the store ------------------------------------------------------------------------------


class Store:
    """The B2B tables in app.db: companies, their people, sessions, one-time links, orders."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    # companies
    def company(self, cid: int) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT * FROM b2b_companies WHERE id=?", (cid,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such company")
        return _company(row)

    def companies(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM b2b_companies ORDER BY status, name").fetchall()
        return [_company(r) for r in rows]

    def add_company(self, fields: dict[str, Any], status: str) -> int:
        cols = {k: v for k, v in fields.items() if k in COMPANY_COLUMNS}
        cols = {**cols, "created": time.time(), "updated": time.time(), "status": status}
        for k in ("addresses", "fixed", "request"):
            if k in cols and not isinstance(cols[k], str):
                cols[k] = json.dumps(cols[k])
        if "reverse_charge" in cols:
            cols["reverse_charge"] = int(bool(cols["reverse_charge"]))
        with self._lock, self._db() as db:
            cur = db.execute(
                f"INSERT INTO b2b_companies ({', '.join(cols)}) "  # noqa: S608 - our column names
                f"VALUES ({', '.join('?' for _ in cols)})",
                tuple(cols.values()),
            )
            return int(cur.lastrowid or 0)

    def change_company(self, cid: int, changes: dict[str, Any]) -> dict[str, Any]:
        self.company(cid)
        with self._lock, self._db() as db:
            for k, v in changes.items():
                if k not in COMPANY_COLUMNS:
                    continue
                if k in ("addresses", "fixed"):
                    v = json.dumps(v)
                elif k == "reverse_charge":
                    v = int(bool(v))
                db.execute(f"UPDATE b2b_companies SET {k}=? WHERE id=?", (v, cid))  # noqa: S608
            db.execute("UPDATE b2b_companies SET updated=? WHERE id=?", (time.time(), cid))
            if changes.get("status") in ("blocked", "rejected"):  # out at once, everywhere
                db.execute(
                    "DELETE FROM b2b_sessions WHERE user_id IN "
                    "(SELECT id FROM b2b_users WHERE company_id=?)",
                    (cid,),
                )
        return self.company(cid)

    # people
    def user(self, uid: int) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT * FROM b2b_users WHERE id=?", (uid,)).fetchone()
        if row is None:
            raise HTTPException(404, "no such person")
        return dict(row)

    def user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM b2b_users WHERE email=?", (email.strip().lower(),)
            ).fetchone()
        return dict(row) if row else None

    def users_of(self, cid: int) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT id, email, name, lang, active, created, last_login, "
                "pw_hash IS NOT NULL AS has_password FROM b2b_users WHERE company_id=? "
                "ORDER BY id",
                (cid,),
            ).fetchall()
            invites = {
                int(r["user_id"]): float(r["expires"])
                for r in db.execute(
                    "SELECT user_id, expires FROM b2b_tokens WHERE used=0 AND expires>? "
                    "AND kind='invite'",
                    (time.time(),),
                )
            }
        return [
            {**dict(r), "has_password": bool(r["has_password"]), "active": bool(r["active"]),
             "invited_until": invites.get(int(r["id"]))}
            for r in rows
        ]  # fmt: skip

    def add_user(self, cid: int, email: str, name: str, lang: str) -> int:
        email = email.strip().lower()
        if not EMAIL.match(email):
            raise HTTPException(400, "please give a valid e-mail address")
        with self._lock, self._db() as db:
            try:
                cur = db.execute(
                    "INSERT INTO b2b_users (company_id, email, name, lang, created) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (cid, email, name.strip() or None, lang, time.time()),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(400, f"{email} already has a business account") from None
            return int(cur.lastrowid or 0)

    def set_lang(self, uid: int, lang: str) -> None:
        with self._lock, self._db() as db:
            db.execute("UPDATE b2b_users SET lang=? WHERE id=?", (lang, uid))

    def change_user(self, uid: int, changes: dict[str, Any]) -> None:
        with self._lock, self._db() as db:
            if "active" in changes:
                db.execute("UPDATE b2b_users SET active=? WHERE id=?",
                           (int(bool(changes["active"])), uid))  # fmt: skip
                if not changes["active"]:
                    db.execute("DELETE FROM b2b_sessions WHERE user_id=?", (uid,))
            if "name" in changes:
                db.execute("UPDATE b2b_users SET name=? WHERE id=?", (changes["name"], uid))

    # one-time links: the first password (an invitation) and a reset
    def token(self, uid: int, kind: str) -> str:
        """A new link; for an invitation the old password stops working (as in the studio)."""
        token = secrets.token_urlsafe(32)
        with self._lock, self._db() as db:
            db.execute("DELETE FROM b2b_tokens WHERE user_id=?", (uid,))
            db.execute(
                "INSERT INTO b2b_tokens (token_hash, user_id, kind, expires) VALUES (?, ?, ?, ?)",
                (_h(token), uid, kind, time.time() + TOKEN_HOURS[kind] * HOUR_S),
            )
            if kind == "invite":
                db.execute("UPDATE b2b_users SET pw_hash=NULL WHERE id=?", (uid,))
                db.execute("DELETE FROM b2b_sessions WHERE user_id=?", (uid,))
        return token

    def token_user(self, token: str) -> tuple[dict[str, Any], str]:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM b2b_tokens WHERE token_hash=? AND used=0 AND expires>?",
                (_h(token), time.time()),
            ).fetchone()
        if row is None:
            raise HTTPException(400, "this link is no longer valid: ask for a new one")
        return self.user(int(row["user_id"])), str(row["kind"])

    def set_password(self, token: str, password: str) -> dict[str, Any]:
        user, _ = self.token_user(token)
        problem = password_problem(password, user["email"].split("@")[0])
        if problem:
            raise HTTPException(400, problem)
        with self._lock, self._db() as db:
            db.execute(
                "UPDATE b2b_users SET pw_hash=?, failed=0, locked_until=NULL WHERE id=?",
                (hash_password(password), user["id"]),
            )
            db.execute("UPDATE b2b_tokens SET used=1 WHERE token_hash=?", (_h(token),))
            db.execute("DELETE FROM b2b_sessions WHERE user_id=?", (user["id"],))
            db.execute(
                "UPDATE b2b_companies SET status='active', updated=? WHERE id=? "
                "AND status='invited'",
                (time.time(), user["company_id"]),
            )
        return self.user(int(user["id"]))

    # logins, with the studio's lock-outs
    def check(self, email: str, password: str, address: str) -> dict[str, Any]:
        now = time.time()
        with self._db() as db:
            arow = db.execute("SELECT * FROM b2b_failures WHERE address=?", (address,)).fetchone()
            row = db.execute(
                "SELECT * FROM b2b_users WHERE email=?", (email.strip().lower(),)
            ).fetchone()
        if arow and arow["locked_until"] and arow["locked_until"] > now:
            raise HTTPException(429, "too many wrong passwords: try again in a few minutes")
        if row is not None and row["locked_until"] and row["locked_until"] > now:
            raise HTTPException(429, "too many wrong passwords: try again in a few minutes")
        ok = row is not None and bool(row["active"]) and check_password(password, row["pw_hash"])
        if row is None:
            check_password(password, hash_password("timing"))  # the same work either way
        if not ok:
            self._failed(row, address, now)
            raise HTTPException(401, "wrong e-mail address or password")
        with self._lock, self._db() as db:
            db.execute("UPDATE b2b_users SET failed=0, locked_until=NULL WHERE id=?", (row["id"],))
            db.execute("DELETE FROM b2b_failures WHERE address=?", (address,))
        return dict(row)

    def _failed(self, row: sqlite3.Row | None, address: str, now: float) -> None:
        lock = now + LOCK_MINUTES * MINUTE_S
        with self._lock, self._db() as db:
            if row is not None:
                failed = int(row["failed"]) + 1
                db.execute(
                    "UPDATE b2b_users SET failed=?, locked_until=? WHERE id=?",
                    (failed, lock if failed >= LOCK_AFTER else None, row["id"]),
                )
            a = db.execute("SELECT failed FROM b2b_failures WHERE address=?", (address,)).fetchone()
            n = (int(a["failed"]) if a else 0) + 1
            db.execute(
                "INSERT OR REPLACE INTO b2b_failures (address, failed, locked_until) "
                "VALUES (?, ?, ?)",
                (address, n, lock if n >= LOCK_AFTER * 2 else None),
            )

    def session(self, uid: int, address: str) -> str:
        now = time.time()
        token = secrets.token_urlsafe(32)
        with self._lock, self._db() as db:
            db.execute("UPDATE b2b_users SET last_login=? WHERE id=?", (now, uid))
            db.execute(
                "INSERT INTO b2b_sessions (token_hash, user_id, created, expires, address) "
                "VALUES (?, ?, ?, ?, ?)",
                (_h(token), uid, now, now + SESSION_DAYS * DAY_S, address),
            )
        return token

    def session_user(self, token: str | None) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """The person and their company, while both may order (active, not blocked)."""
        if not token:
            return None
        with self._db() as db:
            row = db.execute(
                "SELECT u.* FROM b2b_sessions s JOIN b2b_users u ON u.id = s.user_id "
                "WHERE s.token_hash=? AND s.expires>? AND u.active=1",
                (_h(token), time.time()),
            ).fetchone()
        if row is None:
            return None
        company = self.company(int(row["company_id"]))
        if company["status"] != "active":
            return None
        return dict(row), company

    def logout(self, token: str | None) -> None:
        if token:
            with self._lock, self._db() as db:
                db.execute("DELETE FROM b2b_sessions WHERE token_hash=?", (_h(token),))

    def change_password(self, uid: int, old: str, new: str, keep: str) -> None:
        user = self.user(uid)
        if not check_password(old, user["pw_hash"]):
            raise HTTPException(400, "the current password is not right")
        problem = password_problem(new, user["email"].split("@")[0])
        if problem:
            raise HTTPException(400, problem)
        with self._lock, self._db() as db:
            db.execute("UPDATE b2b_users SET pw_hash=? WHERE id=?", (hash_password(new), uid))
            db.execute(
                "DELETE FROM b2b_sessions WHERE user_id=? AND token_hash<>?", (uid, _h(keep))
            )

    # orders
    def add_order(self, row: dict[str, Any]) -> int:
        with self._lock, self._db() as db:
            cur = db.execute(
                "INSERT INTO b2b_orders (created, company_id, user_id, po, note, address, lines, "
                "net_eur, vat_eur, gross_eur, payment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time(), row["company_id"], row["user_id"], row["po"], row["note"],
                 json.dumps(row["address"]), json.dumps(row["lines"]), row["net_eur"],
                 row["vat_eur"], row["gross_eur"], row["payment"]),
            )  # fmt: skip
            return int(cur.lastrowid or 0)

    def order_lines(self, bid: int, cid: int) -> list[dict[str, Any]] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT lines FROM b2b_orders WHERE id=? AND company_id=?", (bid, cid)
            ).fetchone()
        return json.loads(row["lines"]) if row else None

    def totals(self, cid: int) -> tuple[int, float]:
        with self._db() as db:
            n = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(net_eur), 0) FROM b2b_orders WHERE company_id=?",
                (cid,),
            ).fetchone()
        return int(n[0]), round(float(n[1]), 2)

    def set_lines(self, bid: int, lines: list[dict[str, Any]]) -> None:
        with self._lock, self._db() as db:
            db.execute("UPDATE b2b_orders SET lines=? WHERE id=?", (json.dumps(lines), bid))

    def orders(self, cid: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
        """The company's B2B orders (all, for the admin), newest first, with the status of
        every line from the studio's orders table."""
        with self._db() as db:
            rows = db.execute(
                "SELECT o.*, c.name AS company FROM b2b_orders o "
                "JOIN b2b_companies c ON c.id = o.company_id "
                + ("WHERE o.company_id=? " if cid is not None else "")
                + "ORDER BY o.id DESC LIMIT ?",
                ((cid, limit) if cid is not None else (limit,)),
            ).fetchall()
            out = []
            for r in rows:
                d = {**dict(r), "address": json.loads(r["address"]),
                     "lines": json.loads(r["lines"])}  # fmt: skip
                ids = [x["order_id"] for x in d["lines"] if x.get("order_id")]
                st = {
                    int(x["id"]): (x["status"], x["model_id"])
                    for x in db.execute(
                        f"SELECT id, status, model_id FROM orders WHERE id IN "  # noqa: S608
                        f"({', '.join('?' for _ in ids)})",
                        ids,
                    )
                } if ids else {}  # fmt: skip
                for x in d["lines"]:
                    x["status"], x["model_id"] = st.get(int(x.get("order_id") or 0), (None, None))
                out.append(d)
        return out


COMPANY_COLUMNS = (
    "name", "vat_number", "contact", "email", "phone", "street", "postcode", "city", "country",
    "addresses", "price_list", "fixed", "reverse_charge", "status", "note", "request",
)  # fmt: skip


def _company(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["addresses"] = json.loads(d.get("addresses") or "[]")
    d["fixed"] = json.loads(d.get("fixed") or "{}")
    d["request"] = json.loads(d["request"]) if d.get("request") else None
    d["reverse_charge"] = bool(d.get("reverse_charge"))
    return d


def invoice_address(c: dict[str, Any]) -> dict[str, Any]:
    return {"id": None, "label": "", "name": c["name"], "street": c.get("street") or "",
            "postcode": c.get("postcode") or "", "city": c.get("city") or "",
            "country": c.get("country") or ""}  # fmt: skip


def public_company(c: dict[str, Any], ps: dict[str, Any]) -> dict[str, Any]:
    """What the customer sees of their own account (no notes, no request, no status history)."""
    ch = ps["channels"].get(c["price_list"]) or ps["channels"]["b2b"]
    return {
        "name": c["name"], "vat_number": c.get("vat_number"), "contact": c.get("contact"),
        "email": c.get("email"), "phone": c.get("phone"),
        "invoice_address": invoice_address(c), "addresses": c["addresses"],
        "price_list": ch.get("name", c["price_list"]),
        "vat_pct": 0.0 if c["reverse_charge"] else float(ch["vat_pct"]),
        "reverse_charge": c["reverse_charge"],
        "fixed": sorted(c["fixed"]),
    }  # fmt: skip


# ---- prices: the company's list, ex VAT --------------------------------------------------------


def channel_of(ps: dict[str, Any], company: dict[str, Any]) -> str:
    return company["price_list"] if company["price_list"] in ps["channels"] else "b2b"


def _list_fixed(ps: dict[str, Any], channel: str, key: str) -> float | None:
    """A fixed price in the price list, ex VAT (a list that shows VAT stores it with VAT)."""
    ch = ps["channels"][channel]
    v = (ch.get("fixed") or {}).get(key)
    if not v:
        return None
    return float(v) / (1 + float(ch["vat_pct"]) / PERCENT) if ch["show_vat"] else float(v)


def unit_price(
    ps: dict[str, Any],
    company: dict[str, Any],
    costing_channels: dict[str, Any],
    stock: str | None,
    support: str,
    supports: int,
) -> dict[str, Any]:
    """The price of one cover for this company, ex VAT: its list's price (from the costing), a
    fixed price in the list for a catalogue cover, then the company's own fixed price; the
    support (balloons, a frame) the same way."""
    from coverengine import costing

    channel = channel_of(ps, company)
    cover, source = float(costing_channels[channel]["net_eur"]), "list"
    if stock:
        lf = _list_fixed(ps, channel, stock)
        if lf:
            cover, source = lf, "list_fixed"
        cf = company["fixed"].get(stock)
        if cf:
            cover, source = float(cf), "company_fixed"
    extra = 0.0
    if support in ("balloons", "frame"):
        key = "balloon" if support == "balloons" else "frame"
        each = float(costing.accessory_price(ps, key, channel)["net_eur"])
        each = _list_fixed(ps, channel, key) or each
        each = float(company["fixed"].get(key) or each)
        extra = each * (supports if support == "balloons" else 1)
    return {
        "cover_eur": round(cover, 2),
        "support_eur": round(extra, 2),
        "unit_eur": round(cover + extra, 2),
        "source": source,
        "channel": channel,
    }


def vat_pct(ps: dict[str, Any], company: dict[str, Any]) -> float:
    return 0.0 if company["reverse_charge"] else float(ps["channels"][channel_of(ps, company)]
                                                        ["vat_pct"])  # fmt: skip


def money(x: float) -> str:
    return f"EUR {x:,.2f}"


# ---- the routes -------------------------------------------------------------------------------


def install(app: FastAPI, auth: Any, data: Path, store: Any) -> None:  # noqa: C901, PLR0915
    from coverengine import match as mt
    from coverengine import quote as q
    from coverengine.errors import CoverError

    from coverapi import mailer, prices
    from coverapi.security import SESSION_COOKIE, _address, _https, require
    from coverapi.shop import SHOP_DEFAULTS, SHOP_SETTING, link_ok, merged, shop_params, shop_root

    db = Store(auth.path)
    app.state.b2b = db
    quotes = data / "b2b_quotes"
    quotes.mkdir(parents=True, exist_ok=True)
    recent: dict[str, list[float]] = {}

    def settings() -> dict[str, Any]:
        return merged(DEFAULTS, auth.setting(SETTING, {}) or {})

    def address(request: Request) -> str:
        if link_ok(auth, request):  # through the website: its visitor's own address
            return request.headers.get("x-client-ip") or _address(request)
        return _address(request)

    def limit(request: Request, key: str = "", per: int = PER_MINUTE, window: float = 60) -> None:
        a, now = f"{key}:{address(request)}", time.time()
        times = [t for t in recent.get(a, []) if now - t < window]
        if len(times) >= per:
            raise HTTPException(429, "too many requests; please wait a little")
        recent[a] = [*times, now]

    def words(lang: str) -> dict[str, str]:
        """The B2B words in one language (the site's live content, ui.b2b; ADR-064)."""
        ui = app.state.site.read("live")["ui"]
        b = ui.get("b2b") or {}
        return {k: str(v.get(lang) or v.get("en") or v.get("nl") or "") for k, v in b.items()}

    def link(request: Request, page: str) -> str:
        return f"{shop_root(auth, request)}b2b/{page}"

    def mail(to: str, subject: str, text: str) -> bool:
        if not mailer.configured(auth):
            return False
        try:
            mailer.send(auth, to, subject, text)
        except Exception:  # noqa: BLE001 - a mail never stops an order or a login link
            return False
        return True

    def studio_mail(subject: str, text: str) -> None:
        mail(str(auth.setting("alert_email", "rick@s2dio.industries")), subject, text)

    def who(user: dict[str, Any]) -> str:
        return f"b2b:{user['email']}"

    # ---- the front door for /api/b2b/ ----------------------------------------------------
    @app.middleware("http")
    async def b2b_gate(request: Request, call_next: Any) -> Any:
        """With the website link closed (ADR-066), the B2B API answers only the website and
        colleagues; a change must come from one of our own pages (the Origin header)."""
        from fastapi.responses import JSONResponse

        path = request.url.path
        if not path.startswith("/api/b2b/"):
            return await call_next(request)
        s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
        if s["website_link"].get("closed") and not link_ok(auth, request):
            if auth.session_user(request.cookies.get(SESSION_COOKIE)) is None:
                return JSONResponse({"detail": "the shop is on the website"}, status_code=403)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc not in own_hosts(request, s):
                return JSONResponse({"detail": "request from another site"}, status_code=403)
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def own_hosts(request: Request, s: dict[str, Any]) -> set[str]:
        hosts = {request.headers.get("host", ""), request.headers.get("x-forwarded-host", "")}
        dom = str(s.get("domain") or "").removeprefix("https://").strip("/")
        if dom:
            hosts |= {dom, "www." + dom}
            if "." in dom:  # the preview of the website (preview.<zone>)
                hosts.add("preview." + dom.split(".", 1)[1])
        return {h for h in hosts if h}

    def customer(request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
        got = db.session_user(request.cookies.get(COOKIE))
        if got is None:
            raise HTTPException(401, "please log in")
        return got

    def changing(request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
        """A logged-in change: the session's CSRF token must be in the header."""
        user, company = customer(request)
        token = request.cookies.get(COOKIE) or ""
        given = request.headers.get(CSRF_HEADER, "")
        if not given or not hmac.compare_digest(given, csrf_of(token)):
            raise HTTPException(403, "this page is out of date: please reload it")
        return user, company

    def set_cookie(response: Response, token: str, request: Request) -> None:
        response.set_cookie(
            COOKIE, token, max_age=SESSION_DAYS * DAY_S, httponly=True, secure=_https(request),
            samesite="strict", path=COOKIE_PATH,
        )  # fmt: skip

    def me_doc(user: dict[str, Any], company: dict[str, Any], token: str) -> dict[str, Any]:
        s = settings()
        return {
            "user": {"email": user["email"], "name": user["name"], "lang": user["lang"]},
            "company": public_company(company, prices.current(auth)),
            "csrf": csrf_of(token),
            "settings": {k: s[k] for k in ("online_payment", "min_order_eur", "shipping_eur",
                                           "payment_days")},
        }  # fmt: skip

    # ---- logging in ---------------------------------------------------------------------
    @app.post("/api/b2b/login")
    def login(req: LoginIn, request: Request, response: Response) -> dict[str, Any]:
        limit(request)
        a = address(request)
        try:
            user = db.check(req.email, req.password, a)
        except HTTPException:
            auth.log(f"b2b:{req.email.strip().lower()[:80]}", "b2b login failed", a)
            raise
        company = db.company(int(user["company_id"]))
        if company["status"] != "active" and not (
            company["status"] == "invited" and user["pw_hash"]
        ):
            auth.log(who(user), "b2b login refused", {"status": company["status"]})
            raise HTTPException(403, "this account is not open (any more): please contact us")
        if company["status"] == "invited":  # has a password, so the invitation was taken
            db.change_company(company["id"], {"status": "active"})
            company = db.company(company["id"])
        if req.lang:
            db.set_lang(int(user["id"]), req.lang)
        token = db.session(int(user["id"]), a)
        set_cookie(response, token, request)
        auth.log(who(user), "b2b login", a)
        return me_doc(db.user(int(user["id"])), company, token)

    @app.post("/api/b2b/logout")
    def logout(request: Request, response: Response) -> dict[str, Any]:
        db.logout(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path=COOKIE_PATH)
        return {"ok": True}

    @app.get("/api/b2b/me")
    def me(request: Request) -> dict[str, Any]:
        user, company = customer(request)
        return me_doc(user, company, request.cookies.get(COOKIE) or "")

    @app.post("/api/b2b/password/forgot")
    def forgot(req: EmailIn, request: Request) -> dict[str, Any]:
        """A reset link by mail; the same answer whether the address is known or not."""
        limit(request, "mail", PER_HOUR_MAILS, HOUR_S)
        user = db.user_by_email(req.email)
        if user and user["active"] and user["pw_hash"]:
            company = db.company(int(user["company_id"]))
            if company["status"] == "active":
                w = words(user["lang"] or req.lang)
                token = db.token(int(user["id"]), "reset")
                url = link(request, f"reset/{token}")
                mail(user["email"], w.get("mail_reset_subject") or "A new password",
                     f"{w.get('mail_reset_text', '')}\n\n{url}\n")  # fmt: skip
                auth.log(who(user), "b2b password reset asked", address(request))
        return {"ok": True}

    @app.get("/api/b2b/token/{token}")
    def token_info(token: str, request: Request) -> dict[str, Any]:
        limit(request)
        user, kind = db.token_user(token)
        company = db.company(int(user["company_id"]))
        if company["status"] in ("blocked", "rejected"):
            raise HTTPException(400, "this link is no longer valid: ask for a new one")
        return {"email": user["email"], "name": user["name"], "company": company["name"],
                "kind": kind}  # fmt: skip

    @app.post("/api/b2b/token/{token}")
    def token_password(
        token: str, req: PasswordIn, request: Request, response: Response
    ) -> dict[str, Any]:
        """The first password (an invitation) or a new one (a reset); then logged in."""
        limit(request)
        user, _ = db.token_user(token)
        if db.company(int(user["company_id"]))["status"] in ("blocked", "rejected"):
            raise HTTPException(400, "this link is no longer valid: ask for a new one")
        user = db.set_password(token, req.password)
        company = db.company(int(user["company_id"]))
        session = db.session(int(user["id"]), address(request))
        set_cookie(response, session, request)
        auth.log(who(user), "b2b password set", address(request))
        return me_doc(user, company, session)

    @app.post("/api/b2b/password")
    def change_password(req: ChangePasswordIn, request: Request) -> dict[str, Any]:
        user, _ = changing(request)
        db.change_password(int(user["id"]), req.old, req.new, request.cookies.get(COOKIE) or "")
        auth.log(who(user), "b2b password changed")
        return {"ok": True}

    @app.post("/api/b2b/request")
    def request_account(req: RequestIn, request: Request) -> dict[str, Any]:
        """The "request an account" form: it lands in Admin → B2B customers for approval."""
        limit(request, "mail", PER_HOUR_MAILS, HOUR_S)
        email = req.email.strip().lower()
        if not EMAIL.match(email):
            raise HTTPException(400, "please give a valid e-mail address")
        cid = db.add_company(
            {"name": req.company.strip(), "vat_number": req.vat_number.strip(),
             "contact": req.contact.strip(), "email": email, "phone": req.phone.strip(),
             "street": req.street.strip(), "postcode": req.postcode.strip(),
             "city": req.city.strip(), "country": req.country.upper(),
             "request": {"message": req.message, "lang": req.lang, "time": time.time(),
                         "address": address(request)}},
            "requested",
        )  # fmt: skip
        auth.log(f"b2b:{email}", "b2b account requested", {"company": req.company, "id": cid})
        studio_mail(
            f"B2B account requested: {req.company}",
            f"{req.contact} <{email}> asks for a business account for {req.company} "
            f"(VAT {req.vat_number or '-'}, {req.city} {req.country}).\n\n{req.message}\n\n"
            "Approve or reject it on the admin page, B2B customers.",
        )
        return {"ok": True}

    # ---- the catalogue and the configurator ----------------------------------------------
    @app.get("/api/b2b/catalogue")
    def catalogue(request: Request) -> dict[str, Any]:
        """The covers of our range (the SUNS catalogue's size cards), with the fixed prices
        this company has; other prices come per cover (POST quote with stock_model)."""
        _, company = customer(request)
        ps = prices.current(auth)
        channel = channel_of(ps, company)
        products = set(q.options(shop_params(auth))["products"])
        items = []
        for c in mt.cards(store.models):
            if c["kind"] not in products:
                continue
            fixed = company["fixed"].get(c["model_id"]) or _list_fixed(ps, channel, c["model_id"])
            items.append({k: c[k] for k in ("model_id", "name", "category", "kind", "size_cm",
                                            "side", "photo")}
                         | {"fixed_eur": round(float(fixed), 2) if fixed else None})  # fmt: skip
        return {"items": items}

    @app.get("/api/b2b/catalogue/{model_id}.jpg")
    def catalogue_photo(model_id: str, request: Request) -> Response:
        customer(request)
        path = store.models / model_id / "product.jpg"
        if not MODEL_ID.match(model_id) or not path.is_file():
            raise HTTPException(404, "no photo")
        return Response(path.read_bytes(), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})  # fmt: skip

    def make_quote(req: QuoteIn, company: dict[str, Any]) -> dict[str, Any]:
        p = shop_params(auth)
        ps = prices.current(auth)
        stock = None
        sizes = req.sizes
        if req.stock_model:
            stock = mt.card(store.models / req.stock_model)
            if stock is None or stock["kind"] != req.product:
                raise HTTPException(400, "this cover is not in our range for this furniture")
            sizes = {**req.sizes, **mt.fields_for(req.product, stock["size_cm"])}
        given = {**sizes, "vents": req.vents, "colour": req.colour}
        try:
            full = q.proposal(req.product, given, p, ps)
            rain = q.rain_check(req.product, given, p, ps) if req.rain and not stock else None
            glb = q.scene_glb(req.product, given, p, req.support)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        price = unit_price(ps, company, full["price"]["costing"]["channels"], req.stock_model,
                           req.support, int(full["balloons"] or 1))  # fmt: skip
        qid = q.new_id()
        if rain:
            for support, r in rain["options"].items():
                water = r.pop("_water_glb", None)
                r["water"] = f"/api/b2b/scene/{qid}-{support}.glb" if water else None
                if water:
                    (quotes / f"{qid}-{support}.glb").write_bytes(water)
            if rain.get("advice"):  # the advice at this company's price, ex VAT
                adv = rain["advice"]
                alt = unit_price(ps, company, full["price"]["costing"]["channels"], None,
                                 adv["support"], int(adv["count"]))  # fmt: skip
                adv["price_eur"] = alt["support_eur"]
        label = stock["name"] if stock else None
        # the same record as the consumer shop's (shop.produce reads it), plus the company
        record = {"time": time.time(), "input": {**req.model_dump(), "match_token": None},
                  "quote": full, "rain": rain, "support_eur": price["support_eur"],
                  "stock": ({"model_id": stock["model_id"], "name": stock["name"]}
                            if stock else None),
                  "match_token": None, "b2b": {"company_id": company["id"], **price}}  # fmt: skip
        (quotes / f"{qid}.json").write_text(json.dumps(record), encoding="utf-8")
        (quotes / f"{qid}.glb").write_bytes(glb)
        return {
            "id": qid, "product": full["product"], "label": label,
            "pieces": len(full["pieces"]), "cover_area_m2": full["cover_area_m2"],
            "vents": full["vents"], "balloons": full["balloons"], "colour": full["colour"],
            "sizes_cm": full["sizes_cm"], "support": req.support,
            "price": {**price, "ex_vat": True, "vat_pct": vat_pct(ps, company),
                      "indicative": full["price"]["placeholder_prices"]},
            "rain": rain, "scene": f"/api/b2b/scene/{qid}.glb", "stock": record["stock"],
        }  # fmt: skip

    @app.post("/api/b2b/quote")
    def b2b_quote(req: QuoteIn, request: Request) -> dict[str, Any]:
        limit(request)
        _, company = customer(request)
        return make_quote(req, company)

    @app.get("/api/b2b/scene/{qid}.glb")
    def scene(qid: str, request: Request) -> Response:
        customer(request)
        if (
            not re.fullmatch(r"[0-9a-f]{16}(-(none|balloons|frame))?", qid)
            or not (quotes / f"{qid}.glb").is_file()
        ):
            raise HTTPException(404, "no such scene")
        return Response((quotes / f"{qid}.glb").read_bytes(), media_type="model/gltf-binary")

    # ---- the company's own delivery addresses ---------------------------------------------
    @app.put("/api/b2b/addresses")
    def put_addresses(req: AddressesIn, request: Request) -> dict[str, Any]:
        user, company = changing(request)
        out = []
        for a in req.addresses:
            d = a.model_dump()
            d["id"] = d["id"] or secrets.token_hex(4)
            d["country"] = d["country"].upper()
            out.append(d)
        db.change_company(company["id"], {"addresses": out})
        auth.log(who(user), "b2b addresses", {"company": company["id"], "count": len(out)})
        return {"addresses": out}

    # ---- ordering on account --------------------------------------------------------------
    def place(
        req: OrderIn, user: dict[str, Any], company: dict[str, Any], request: Request
    ) -> dict[str, Any]:
        s = settings()
        ps = prices.current(auth)
        if req.payment == "online" and not s["online_payment"]:
            raise HTTPException(400, "online payment is not switched on: order on account")
        if req.payment == "online":
            raise HTTPException(501, "online payment for business orders is not built yet")
        lines, records = [], []
        for ln in req.lines:
            path = quotes / f"{ln.quote_id}.json"
            if not path.is_file():
                raise HTTPException(404, "a price has expired; please make it again")
            rec = json.loads(path.read_text(encoding="utf-8"))
            if (rec.get("b2b") or {}).get("company_id") != company["id"]:
                raise HTTPException(404, "a price has expired; please make it again")
            unit = float(rec["b2b"]["unit_eur"])
            records.append(rec)
            qd = rec["quote"]
            lines.append({
                "quote_id": ln.quote_id, "qty": ln.qty, "unit_eur": unit,
                "total_eur": round(unit * ln.qty, 2), "product": qd["product"],
                "label": (rec.get("stock") or {}).get("name"),
                "stock_model": (rec.get("stock") or {}).get("model_id"),
                "colour": qd["colour"], "sizes_cm": qd["sizes_cm"],
                "support": rec["input"]["support"], "input": rec["input"],
            })  # fmt: skip
        net = round(sum(x["total_eur"] for x in lines) + float(s["shipping_eur"] or 0), 2)
        if net < float(s["min_order_eur"] or 0):
            raise HTTPException(400, f"the minimum order is {money(float(s['min_order_eur']))} "
                                     "ex VAT")  # fmt: skip
        if req.address_id:
            addr = next((a for a in company["addresses"] if a["id"] == req.address_id), None)
            if addr is None:
                raise HTTPException(400, "no such delivery address")
        else:
            addr = invoice_address(company)
        if not (addr.get("street") and addr.get("city")):
            raise HTTPException(400, "please give a delivery address")
        vat = round(net * vat_pct(ps, company) / PERCENT, 2)
        bid = db.add_order({"company_id": company["id"], "user_id": user["id"],
                            "po": req.po.strip(), "note": req.note.strip(), "address": addr,
                            "lines": lines, "net_eur": net, "vat_eur": vat,
                            "gross_eur": round(net + vat, 2), "payment": "account"})  # fmt: skip
        # each line an order of the studio's own, flagged B2B: the same way into production
        customer_doc = {
            "name": addr.get("name") or company["name"], "email": user["email"],
            "phone": company.get("phone") or "", "street": addr["street"],
            "postcode": addr["postcode"], "city": addr["city"], "country": addr["country"],
            "note": req.note, "terms": True, "lang": req.lang, "company": company["name"],
            "vat_number": company.get("vat_number") or "",
        }  # fmt: skip
        with sqlite3.connect(auth.path) as c:
            for i, (line, rec) in enumerate(zip(lines, records, strict=True)):
                data = {"customer": customer_doc, "quote": rec, "shipping_eur": 0.0,
                        "lang": req.lang,
                        "b2b": {"order": bid, "line": i + 1, "lines": len(lines),
                                "company_id": company["id"], "company": company["name"],
                                "po": req.po.strip(), "qty": line["qty"],
                                "unit_eur": line["unit_eur"], "ex_vat": True,
                                "payment": "account"}}  # fmt: skip
                cur = c.execute(
                    "INSERT INTO orders (created, token, status, email, data, total_eur, updated) "
                    "VALUES (?, ?, 'on_account', ?, ?, ?, ?)",
                    (time.time(), secrets.token_urlsafe(18), user["email"], json.dumps(data),
                     line["total_eur"], time.time()),
                )  # fmt: skip
                line["order_id"] = int(cur.lastrowid or 0)
        db.set_lines(bid, lines)
        auth.log(who(user), "b2b order", {"order": bid, "lines": len(lines), "net_eur": net,
                                          "po": req.po})  # fmt: skip
        produce_later([x["order_id"] for x in lines])
        doc = {"order": bid, "net_eur": net, "vat_eur": vat, "gross_eur": round(net + vat, 2),
               "lines": lines, "address": addr, "po": req.po.strip()}  # fmt: skip
        confirm_mails(doc, user, company, req.lang, s)
        return doc

    def produce_later(order_ids: list[int]) -> None:
        """An order on account goes into production like a paid one (shop.produce), in the
        background so the customer is not kept waiting."""
        if not settings()["auto_produce"]:
            return
        produce = getattr(app.state, "shop_produce", None)
        if produce is None:
            return

        def run() -> None:
            for oid in order_ids:
                try:
                    produce(oid)
                except Exception as exc:  # noqa: BLE001 - the studio is told; the order stays
                    studio_mail(f"B2B order line {oid}: not into production",
                                f"{exc}\nAdmin → Orders → Into production.")  # fmt: skip

        threading.Thread(target=run, daemon=True, name="b2b-produce").start()

    def confirm_mails(
        doc: dict[str, Any], user: dict[str, Any], company: dict[str, Any], lang: str,
        s: dict[str, Any],
    ) -> None:  # fmt: skip
        w = words(lang)
        ui = app.state.site.read("live")["ui"]

        def product(k: str) -> str:
            t = (ui.get("product") or {}).get(k) or {}
            return str(t.get(lang) or t.get("en") or k)

        rows = "\n".join(
            f"- {x['qty']} x {x['label'] or product(x['product'])}, {x['colour']}"
            f"{', ' + str(x['support']) if x['support'] != 'none' else ''}"
            f" ({', '.join(f'{v}' for k, v in x['sizes_cm'].items() if isinstance(v, int | float))}"
            f" cm): {money(x['unit_eur'])} = {money(x['total_eur'])}"
            for x in doc["lines"]
        )
        a = doc["address"]
        vat_line = (w.get("reverse_charge") or "VAT reverse-charged") if company[
            "reverse_charge"] else f"{w.get('vat') or 'VAT'}: {money(doc['vat_eur'])}"  # fmt: skip
        body = (
            f"{w.get('order_n', 'Order {n}').replace('{n}', str(doc['order']))}"
            f" · {company['name']}\n"
            + (f"{w.get('po') or 'PO'}: {doc['po']}\n" if doc["po"] else "")
            + f"\n{rows}\n\n{w.get('subtotal') or 'Subtotal ex VAT'}: {money(doc['net_eur'])}\n"
            f"{vat_line}\n{w.get('incl_vat') or 'Total incl. VAT'}: {money(doc['gross_eur'])}\n\n"
            f"{w.get('deliver_to') or 'Deliver to'}: {a.get('name') or ''}, {a['street']}, "
            f"{a['postcode']} {a['city']}, {a['country']}\n"
            f"{w.get('on_account') or 'On account'} ({s['payment_days']} d)\n\n"
            f"{w.get('ordered_text') or ''}\n"
        )
        subject = (w.get("mail_order_subject") or "Order {n} received").replace(
            "{n}", str(doc["order"]))  # fmt: skip
        mail(user["email"], subject, body)
        if company.get("email") and company["email"] != user["email"]:
            mail(company["email"], subject, body)
        studio_mail(
            f"B2B order {doc['order']}: {company['name']}, {money(doc['net_eur'])} ex VAT",
            f"{user['email']} ordered on account for {company['name']} "
            f"(VAT {company.get('vat_number') or '-'}).\n\n{body}\n"
            "The lines are on the admin page, Orders (flagged B2B).",
        )

    @app.post("/api/b2b/order")
    def order(req: OrderIn, request: Request) -> dict[str, Any]:
        limit(request, "order", 10)
        user, company = changing(request)
        return place(req, user, company, request)

    @app.get("/api/b2b/orders")
    def my_orders(request: Request) -> dict[str, Any]:
        _, company = customer(request)
        out = db.orders(company["id"])
        for o in out:  # the customer sees no internal fields
            for x in o["lines"]:
                x.pop("input", None)
        return {"orders": out}

    @app.post("/api/b2b/orders/{bid}/reorder")
    def reorder(bid: int, request: Request) -> dict[str, Any]:
        """Order again: every line priced anew at today's prices, for the order list."""
        limit(request)
        _, company = changing(request)
        lines = db.order_lines(bid, company["id"])
        if lines is None:
            raise HTTPException(404, "no such order")
        out = []
        for ln in lines:
            inp = {k: v for k, v in ln["input"].items() if k in QuoteIn.model_fields}
            qt = make_quote(QuoteIn(**{**inp, "rain": False}), company)
            out.append({"quote": qt, "qty": ln["qty"]})
        return {"lines": out}

    # ---- the admin page: B2B customers ------------------------------------------------------
    def invite(uid: int, request: Request, admin: Any) -> dict[str, Any]:
        user = db.user(uid)
        company = db.company(int(user["company_id"]))
        token = db.token(uid, "invite")
        url = link(request, f"welcome/{token}")
        w = words(user["lang"] or "nl")
        mailed = mail(
            user["email"],
            w.get("mail_invite_subject") or "Your business account",
            f"{w.get('mail_invite_text', '')}\n\n{company['name']}\n{url}\n",
        )
        auth.log(admin, "b2b invite", {"company": company["name"], "email": user["email"],
                                       "mailed": mailed})  # fmt: skip
        return {"link": url, "mailed": mailed, "days": TOKEN_HOURS["invite"] // 24}

    def company_doc(c: dict[str, Any]) -> dict[str, Any]:
        n, eur = db.totals(c["id"])
        return {**c, "users": db.users_of(c["id"]), "orders": n, "ordered_eur": eur}

    def checked(changes: dict[str, Any]) -> dict[str, Any]:
        ps = prices.current(auth)
        if "price_list" in changes and changes["price_list"] not in ps["channels"]:
            raise HTTPException(400, f"price list: one of {', '.join(ps['channels'])}")
        if "status" in changes and changes["status"] not in STATUSES:
            raise HTTPException(400, f"status: one of {', '.join(STATUSES)}")
        if "fixed" in changes:
            for k, v in changes["fixed"].items():
                if not (MODEL_ID.match(k) or k in ACCESSORY_KEYS) or float(v) <= 0:
                    raise HTTPException(400, f"fixed price {k}: a catalogue cover (suns-…), "
                                             "balloon or frame, above 0")  # fmt: skip
        if "addresses" in changes:
            out = []
            for a in changes["addresses"]:
                d = a.model_dump() if isinstance(a, Address) else Address(**a).model_dump()
                out.append({**d, "id": d["id"] or secrets.token_hex(4),
                            "country": d["country"].upper()})  # fmt: skip
            changes["addresses"] = out
        if changes.get("country"):
            changes["country"] = changes["country"].upper()
        return changes

    @app.get("/api/admin/b2b/companies")
    def admin_companies(request: Request) -> dict[str, Any]:
        require(request, "admin")
        ps = prices.current(auth)
        return {"companies": [company_doc(c) for c in db.companies()],
                "price_lists": {k: v.get("name", k) for k, v in ps["channels"].items()},
                "statuses": list(STATUSES), "settings": settings(),
                "shop_url": shop_root(auth, request) + "b2b/"}  # fmt: skip

    @app.post("/api/admin/b2b/companies")
    def admin_add_company(req: NewCompanyIn, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        fields = checked(req.model_dump(exclude={"lang", "send_invite"}, exclude_none=True))
        fields["email"] = req.email.strip().lower()
        fields.pop("status", None)
        if db.user_by_email(fields["email"]):
            raise HTTPException(400, f"{fields['email']} already has a business account")
        cid = db.add_company(fields, "invited")
        uid = db.add_user(cid, req.email, req.contact or "", req.lang)
        auth.log(admin, "b2b company added", {"company": req.name, "id": cid})
        out = invite(uid, request, admin) if req.send_invite else {"link": None, "mailed": False}
        return {"company": company_doc(db.company(cid)), **out}

    @app.put("/api/admin/b2b/companies/{cid}")
    def admin_change_company(cid: int, req: CompanyIn, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        changes = checked(req.model_dump(exclude_none=True))
        c = db.change_company(cid, changes)
        auth.log(admin, "b2b company changed",
                 {"company": c["name"], **{k: ("…" if k in ("addresses", "fixed") else v)
                                           for k, v in changes.items()}})  # fmt: skip
        return {"company": company_doc(c)}

    @app.post("/api/admin/b2b/companies/{cid}/approve")
    def admin_approve(cid: int, request: Request) -> dict[str, Any]:
        """A request becomes an account: the person who asked is invited by mail."""
        admin = require(request, "admin")
        c = db.company(cid)
        if c["status"] != "requested":
            raise HTTPException(400, "only a request can be approved")
        if db.user_by_email(c["email"] or ""):
            raise HTTPException(400, f"{c['email']} already has a business account")
        lang = (c["request"] or {}).get("lang") or "nl"
        uid = db.add_user(cid, c["email"] or "", c.get("contact") or "", lang)
        db.change_company(cid, {"status": "invited"})
        auth.log(admin, "b2b request approved", {"company": c["name"]})
        return {"company": company_doc(db.company(cid)), **invite(uid, request, admin)}

    @app.post("/api/admin/b2b/companies/{cid}/users")
    def admin_add_user(cid: int, req: NewUserIn, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        c = db.company(cid)
        if c["status"] in ("requested", "rejected"):
            raise HTTPException(400, "approve the company first")
        uid = db.add_user(cid, req.email, req.name, req.lang)
        return {"company": company_doc(db.company(cid)), **invite(uid, request, admin)}

    @app.post("/api/admin/b2b/users/{uid}/invite")
    def admin_reinvite(uid: int, request: Request) -> dict[str, Any]:
        """A new link to set a password (also: a reset for someone who lost it)."""
        admin = require(request, "admin")
        return invite(uid, request, admin)

    @app.put("/api/admin/b2b/users/{uid}")
    def admin_change_user(uid: int, req: UserChangeIn, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        user = db.user(uid)
        db.change_user(uid, req.model_dump(exclude_none=True))
        auth.log(admin, "b2b person changed", {"email": user["email"],
                                               **req.model_dump(exclude_none=True)})  # fmt: skip
        return {"company": company_doc(db.company(int(user["company_id"])))}

    @app.get("/api/admin/b2b/orders")
    def admin_orders(request: Request, company: int | None = None) -> dict[str, Any]:
        require(request, "admin")
        return {"orders": db.orders(company)}

    @app.put("/api/admin/b2b/settings")
    async def admin_settings(request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "settings: a JSON object")
        new = {k: v for k, v in body.items() if k in DEFAULTS}
        for k in ("min_order_eur", "shipping_eur", "payment_days"):
            if k in new and (not isinstance(new[k], int | float) or new[k] < 0):
                raise HTTPException(400, f"{k}: a number, 0 or more")
        auth.set_setting(SETTING, {**(auth.setting(SETTING, {}) or {}), **new})
        auth.log(admin, "b2b settings", new)
        return {"settings": settings()}


def install_pages(app: FastAPI, web_dir: Path) -> None:
    """/shop/b2b/... : the B2B shop's page (b2b.html). The website (the Worker) serves it at
    /b2b; it is a logged-in shop, so it is never indexed."""
    from fastapi.responses import HTMLResponse

    page = web_dir / "b2b.html"

    def serve() -> HTMLResponse:
        if not page.is_file():
            raise HTTPException(404, "the B2B shop is not built")
        return HTMLResponse(
            page.read_text(encoding="utf-8"),
            headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-cache"},
        )

    @app.get("/shop/b2b", include_in_schema=False)
    @app.get("/shop/b2b/", include_in_schema=False)
    def b2b_home() -> HTMLResponse:
        return serve()

    @app.get("/shop/b2b/{rest:path}", include_in_schema=False)
    def b2b_page(rest: str) -> HTMLResponse:
        return serve()
