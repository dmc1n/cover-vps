"""Outgoing mail (ADR-047): invitations, password resets, approval notices.

The SMTP server is set on the admin page and kept in the settings table: host, port, security
(starttls | ssl | none), user name, password (never shown again once saved) and the sender
address. Without it the app still works: the admin copies the links by hand.

Every send attempt is logged in app.db (`mail_log`: when, kind, to, subject, sent or the error;
never the text, never a password; ADR-129). A mail counts as sent only once the SMTP server
accepted it for its recipient.

Mails that may wait (order notifications, reviews, the Desk's digests) go through the outbox
(`queue`): the text is kept in `mail_outbox` until the server accepts it, tried again with a
doubling wait (limits.mail_*), then shown as failed in Settings → System & logs, where a person
can send it again. The text of a sent mail is removed at once, a failed one's after
limits.mail_keep_hours. Mails with a secret in them (login codes, password links) are never put
in the outbox: they are sent at once, the person waiting asks again if one fails.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import smtplib
import sqlite3
import ssl
import threading
import time
import uuid
from collections.abc import Callable
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from coverapi.auth import Auth

log = logging.getLogger("coverapi.mail")
MAIL_KEY = "mail"
SECURITIES = ("starttls", "ssl", "none")
TIMEOUT_S = 20
TICK_S = 30  # the outbox looks for due mails this often
# a mail being tried is not picked up again for this long (its lease): well over one SMTP
# conversation (connect, TLS, login, send: each may take TIMEOUT_S)
CLAIM_S = TIMEOUT_S * 10
HOUR_S = 3600
ERROR_CHARS = 300  # of an error kept in the log
SUBJECT_CHARS = 200  # of a subject kept in the log

SCHEMA = """
CREATE TABLE IF NOT EXISTS mail_outbox (
  id INTEGER PRIMARY KEY, created REAL NOT NULL, kind TEXT NOT NULL, ref TEXT UNIQUE,
  recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed
  attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL, last_error TEXT, sent REAL,
  claim TEXT  -- the try that holds the mail now (its lease ends at next_try)
);
CREATE INDEX IF NOT EXISTS mail_outbox_due ON mail_outbox(status, next_try);
CREATE TABLE IF NOT EXISTS mail_log (
  id INTEGER PRIMARY KEY, time REAL NOT NULL, outbox_id INTEGER, kind TEXT NOT NULL,
  recipient TEXT NOT NULL, subject TEXT NOT NULL, result TEXT NOT NULL, error TEXT
);
"""

# kind -> what to do once a mail of that kind was accepted: f(app.db path, ref)
ON_SENT: dict[str, Callable[[Path, str], None]] = {}


def settings(auth: Auth, with_password: bool = False) -> dict[str, Any]:
    s = dict(auth.setting(MAIL_KEY, {}) or {})
    if not with_password:
        s["password_set"] = bool(s.pop("password", None))
    return s


def save(auth: Auth, changes: dict[str, Any]) -> dict[str, Any]:
    current = dict(auth.setting(MAIL_KEY, {}) or {})
    for key in ("host", "port", "security", "username", "sender", "password"):
        if key in changes:
            if key == "password" and not changes[key]:
                continue  # an empty field keeps the saved password
            current[key] = changes[key]
    if current.get("security", "starttls") not in SECURITIES:
        raise ValueError(f"security must be one of {', '.join(SECURITIES)}")
    current["port"] = int(current.get("port") or 587)
    auth.set_setting(MAIL_KEY, current)
    return settings(auth)


def configured(auth: Auth) -> bool:
    s = settings(auth, with_password=True)
    return bool(s.get("host") and s.get("sender"))


def _db(auth: Auth) -> sqlite3.Connection:
    db = sqlite3.connect(auth.path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    if "claim" not in {r[1] for r in db.execute("PRAGMA table_info(mail_outbox)")}:
        db.execute("ALTER TABLE mail_outbox ADD COLUMN claim TEXT")
    return db


def _clean_error(exc: BaseException, auth: Auth) -> str:
    """The error for the log: its type and message, short, with the password and anything
    that looks like a credential removed."""
    text = f"{type(exc).__name__}: {exc}"
    pw = str(settings(auth, with_password=True).get("password") or "")
    if pw:
        text = text.replace(pw, "***")
    text = re.sub(r"(?i)(auth\w*|password|pass)\s*[=:]\s*\S+", r"\1=***", text)
    return text[:ERROR_CHARS]


def _safe_subject(subject: str) -> str:
    """The subject for the log: a login code in it (six digits or more) is masked."""
    from coverapi.auth import CODE_DIGITS

    return re.sub(rf"\d{{{CODE_DIGITS},}}", "******", subject)[:SUBJECT_CHARS]


def _log(auth: Auth, kind: str, to: str, subject: str, result: str, error: str | None = None,
         outbox_id: int | None = None) -> None:  # fmt: skip
    with contextlib.closing(_db(auth)) as db:
        db.execute(
            "INSERT INTO mail_log (time, outbox_id, kind, recipient, subject, result, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time.time(), outbox_id, kind, to, _safe_subject(subject), result, error),
        )


def send(
    auth: Auth,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
    kind: str = "direct",
    outbox_id: int | None = None,
) -> None:
    """One mail, now; raises when it was not accepted. Every attempt is logged (no text).
    `attachments` are (file name, content, MIME type such as application/pdf). The outbox
    names its kind and row through `_current` (so a test's stand-in for send() sees the
    same four arguments as before)."""
    ctx_kind, ctx_id = getattr(_current, "value", (None, None))
    kind, outbox_id = ctx_kind or kind, ctx_id if ctx_id is not None else outbox_id
    try:
        _deliver(auth, to, subject, text, html, attachments)
    except Exception as exc:
        _log(auth, kind, to, subject, "error", _clean_error(exc, auth), outbox_id)
        raise
    _log(auth, kind, to, subject, "sent", None, outbox_id)


_current = threading.local()  # (kind, outbox id) of the outbox mail being sent


def _deliver(
    auth: Auth,
    to: str,
    subject: str,
    text: str,
    html: str | None,
    attachments: list[tuple[str, bytes, str]] | None,
) -> None:
    s = settings(auth, with_password=True)
    if not (s.get("host") and s.get("sender")):
        raise RuntimeError("no mail server set (admin page, Mail)")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["sender"], to, subject
    msg.set_content(text)
    if html:  # the same message with layout, for mail programs that show it
        msg.add_alternative(html, subtype="html")
    for name, data, mime in attachments or []:
        main, sub = mime.split("/", 1)
        msg.add_attachment(data, maintype=main, subtype=sub, filename=name)
    context = ssl.create_default_context()
    port = int(s.get("port") or 587)
    if s.get("security") == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(s["host"], port, timeout=TIMEOUT_S, context=context)
    else:
        server = smtplib.SMTP(s["host"], port, timeout=TIMEOUT_S)
    with server:
        if s.get("security", "starttls") == "starttls":
            server.starttls(context=context)
        if s.get("username"):
            server.login(s["username"], s.get("password", ""))
        refused = server.send_message(msg)
    if refused:  # accepted for nobody we sent it to: not sent
        raise smtplib.SMTPRecipientsRefused(refused)


# ---- the outbox -------------------------------------------------------------------------------


def _limits() -> dict[str, float]:
    from coverengine.params import Registry

    p = Registry.load(None).resolve()
    return {
        k: float(p[f"limits.mail_{k}"])  # type: ignore[arg-type]
        for k in ("attempts", "retry_first_s", "retry_max_s", "keep_hours")
    }


def queued(auth: Auth, ref: str) -> bool:
    """Is a mail with this reference in the outbox already (pending, sent or failed)?"""
    with contextlib.closing(_db(auth)) as db:
        return db.execute("SELECT 1 FROM mail_outbox WHERE ref=?", (ref,)).fetchone() is not None


def queue(auth: Auth, to: str, subject: str, text: str, kind: str,
          ref: str | None = None) -> int | None:  # fmt: skip
    """Put a mail in the outbox and try it at once; a failed try is repeated later until the
    server accepts it. With `ref`, a mail is queued once only (None: it was there already).
    Returns the outbox row; `is_sent` says whether the first try went."""
    now, claim = time.time(), uuid.uuid4().hex
    with contextlib.closing(_db(auth)) as db:
        try:
            cur = db.execute(
                "INSERT INTO mail_outbox (created, kind, ref, recipient, subject, body, next_try,"
                " claim) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, kind, ref, to, subject, text, now + CLAIM_S, claim),  # held by this try
            )
        except sqlite3.IntegrityError:
            return None
        oid = int(cur.lastrowid or 0)
        row = db.execute("SELECT * FROM mail_outbox WHERE id=?", (oid,)).fetchone()
        _attempt(auth, db, row, now, _limits())
    _register(auth)
    return oid


def is_sent(auth: Auth, outbox_id: int | None) -> bool:
    if outbox_id is None:
        return False
    with contextlib.closing(_db(auth)) as db:
        r = db.execute("SELECT status FROM mail_outbox WHERE id=?", (outbox_id,)).fetchone()
    return r is not None and r["status"] == "sent"


def _attempt(auth: Auth, db: sqlite3.Connection, r: sqlite3.Row, now: float,
             lim: dict[str, float]) -> str:  # fmt: skip
    """One try of one outbox mail that this try holds (`claim`): sent (its text removed), again
    later (a doubling wait) or, at the last try, failed. Every result is written only while the
    claim is still this try's, so a try whose lease ran out never overwrites a newer one."""
    attempts, mine = int(r["attempts"]) + 1, (r["id"], r["claim"])
    _current.value = (r["kind"], int(r["id"]))
    try:
        send(auth, r["recipient"], r["subject"], r["body"] or "")
    except Exception as exc:  # noqa: BLE001 - logged by send(); tried again later
        err = _clean_error(exc, auth)
        if attempts >= lim["attempts"]:
            db.execute("UPDATE mail_outbox SET status='failed', attempts=?, last_error=?, "
                       "claim=NULL WHERE id=? AND claim=?", (attempts, err, *mine))  # fmt: skip
            log.warning("mail %s to %s failed for good: %s", r["id"], r["recipient"], err)
            return "failed"
        wait = min(lim["retry_first_s"] * 2 ** (attempts - 1), lim["retry_max_s"])
        db.execute("UPDATE mail_outbox SET attempts=?, last_error=?, next_try=?, claim=NULL "
                   "WHERE id=? AND claim=?", (attempts, err, now + wait, *mine))  # fmt: skip
        return "retry"
    finally:
        _current.value = (None, None)
    db.execute("UPDATE mail_outbox SET status='sent', sent=?, attempts=?, body=NULL, "
               "last_error=NULL, claim=NULL WHERE id=? AND claim=?",
               (time.time(), attempts, *mine))  # fmt: skip
    hook = ON_SENT.get(r["kind"])
    if hook and r["ref"]:
        try:
            hook(Path(auth.path), str(r["ref"]))
        except Exception as exc:  # noqa: BLE001 - the mail went; say what did not
            _log(auth, r["kind"], r["recipient"], r["subject"], "after-send error",
                 _clean_error(exc, auth), int(r["id"]))  # fmt: skip
    return "sent"


def deliver_due(auth: Auth, now: float | None = None) -> dict[str, int]:
    """Try every mail whose time has come (see `_attempt`); old texts and logs are removed."""
    now = time.time() if now is None else now
    lim = _limits()
    out = {"sent": 0, "retry": 0, "failed": 0}
    with contextlib.closing(_db(auth)) as db:
        due = [r["id"] for r in db.execute(
            "SELECT id FROM mail_outbox WHERE status='pending' AND next_try<=? ORDER BY id",
            (now,))]  # fmt: skip
        for oid in due:
            # each mail is claimed just before its try (a lease of CLAIM_S from now), so a long
            # backlog never sends a mail whose claim another worker took meanwhile
            claim = uuid.uuid4().hex
            if not db.execute(
                "UPDATE mail_outbox SET claim=?, next_try=? WHERE id=? AND status='pending' "
                "AND next_try<=?", (claim, max(now, time.time()) + CLAIM_S, oid, now)
            ).rowcount:  # fmt: skip
                continue
            r = db.execute("SELECT * FROM mail_outbox WHERE id=?", (oid,)).fetchone()
            out[_attempt(auth, db, r, now, lim)] += 1
        old = now - lim["keep_hours"] * HOUR_S
        db.execute("UPDATE mail_outbox SET body=NULL WHERE status='failed' AND created<?", (old,))
        db.execute("DELETE FROM mail_outbox WHERE status='sent' AND sent<?", (old,))
        db.execute("DELETE FROM mail_log WHERE time<?", (old,))
    return out


def retry(auth: Auth, outbox_id: int) -> dict[str, Any]:
    """Send again (Settings → System & logs): a failed mail goes back in the outbox."""
    with contextlib.closing(_db(auth)) as db:
        r = db.execute("SELECT * FROM mail_outbox WHERE id=?", (outbox_id,)).fetchone()
        if r is None:
            raise KeyError(outbox_id)
        if r["status"] != "failed" or r["body"] is None:
            raise ValueError("only a failed mail whose text is still kept can be sent again")
        db.execute(
            "UPDATE mail_outbox SET status='pending', attempts=0, next_try=?, claim=NULL "
            "WHERE id=?",
            (time.time(), outbox_id),
        )
    _register(auth)
    _wake.set()
    return {"id": outbox_id, "status": "pending"}


def overview(auth: Auth, limit: int = 100) -> dict[str, Any]:
    """For Settings → System & logs: the outbox's waiting and failed mails and the last
    attempts (no texts)."""
    cols = "id, created, kind, recipient, subject, status, attempts, next_try, last_error, sent"
    with contextlib.closing(_db(auth)) as db:
        open_ = db.execute(
            f"SELECT {cols}, body IS NOT NULL AS can_retry FROM mail_outbox "  # noqa: S608
            "WHERE status<>'sent' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()  # fmt: skip
        log = db.execute(
            "SELECT time, kind, recipient, subject, result, error FROM mail_log "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()  # fmt: skip
        counts = dict(
            db.execute("SELECT status, COUNT(*) FROM mail_outbox GROUP BY status").fetchall()
        )
    return {
        "configured": configured(auth),
        "pending": int(counts.get("pending", 0)),
        "failed": int(counts.get("failed", 0)),
        "outbox": [dict(r) for r in open_],
        "log": [dict(r) for r in log],
    }


# one thread per process walks the outboxes of every app.db in use
_auths: dict[str, Auth] = {}
_wake = threading.Event()
_started = threading.Lock()
_thread: list[threading.Thread] = []


def _register(auth: Auth) -> None:
    _auths.setdefault(str(auth.path), auth)


def start(auth: Auth) -> None:
    """The outbox's worker for this app.db (one thread for the process)."""
    _register(auth)
    if os.environ.get("COVER_MAIL_WORKER", "on") == "off":  # the tests call deliver_due()
        return
    with _started:
        if not _thread:
            t = threading.Thread(target=_loop, daemon=True, name="mail-outbox")
            t.start()
            _thread.append(t)
    _wake.set()


def _loop() -> None:
    while True:
        _wake.wait(TICK_S)
        _wake.clear()
        for a in list(_auths.values()):
            try:
                if Path(a.path).is_file():
                    deliver_due(a)
            except Exception:  # noqa: BLE001 - said in the journal; the next tick tries again
                log.exception("mail outbox of %s", a.path)


def install(app: Any, auth: Auth) -> None:
    """Settings → System & logs: the outbox and the send attempts; "Send again" (ADR-129)."""

    from coverapi.security import require

    start(auth)

    @app.get("/api/admin/mail/outbox")
    def mail_outbox(request: Request) -> dict[str, Any]:
        require(request, "admin")
        return overview(auth)

    @app.post("/api/admin/mail/outbox/{outbox_id}/retry")
    def mail_retry(outbox_id: int, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        try:
            out = retry(auth, outbox_id)
        except KeyError:
            raise HTTPException(404, "no such mail") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        auth.log(admin, "mail sent again", {"outbox": outbox_id})
        return out
