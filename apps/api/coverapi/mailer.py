"""Outgoing mail (ADR-047): invitations, password resets, approval notices.

The SMTP server is set on the admin page and kept in the settings table: host, port, security
(starttls | ssl | none), user name, password (never shown again once saved) and the sender
address. Without it the app still works: the admin copies the links by hand.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from coverapi.auth import Auth

MAIL_KEY = "mail"
SECURITIES = ("starttls", "ssl", "none")
TIMEOUT_S = 20


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


def send(auth: Auth, to: str, subject: str, text: str) -> None:
    s = settings(auth, with_password=True)
    if not (s.get("host") and s.get("sender")):
        raise RuntimeError("no mail server set (admin page, Mail)")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s["sender"], to, subject
    msg.set_content(text)
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
        server.send_message(msg)
