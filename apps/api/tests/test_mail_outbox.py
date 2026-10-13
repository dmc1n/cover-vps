"""Mails that must not fail silently (ADR-129): every attempt is logged in app.db, a mail counts
as sent only once the SMTP server accepted it, the outbox tries again with a doubling wait, and
failures show in Settings → System & logs. No texts in the log, never a password."""

import smtplib
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest
from coverapi import mailer
from coverapi.main import create_app
from fastapi.testclient import TestClient

PASSWORD = "s3cret-smtp-pw"


class FakeSMTP:
    """Stands in for smtplib.SMTP: `plan` says what each next delivery does."""

    plan: list[str] = []
    accepted: list[str] = []

    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *a: Any) -> None:
        pass

    def starttls(self, **k: Any) -> None:
        pass

    def login(self, user: str, password: str) -> None:
        if FakeSMTP.plan and FakeSMTP.plan[0] == "auth":
            FakeSMTP.plan.pop(0)
            raise smtplib.SMTPAuthenticationError(535, f"bad login {user}/{password}".encode())

    def send_message(self, msg: Any) -> dict[str, Any]:
        what = FakeSMTP.plan.pop(0) if FakeSMTP.plan else "ok"
        if what == "down":
            raise smtplib.SMTPServerDisconnected("connection unexpectedly closed")
        if what == "refused":
            return {msg["To"]: (550, b"no such user")}
        FakeSMTP.accepted.append(msg["To"])
        return {}


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.plan, FakeSMTP.accepted = [], []
    a = create_app(tmp_path / "data")
    a.state.auth.set_setting("mail", {
        "host": "smtp.example.com", "port": 587,
        "security": "starttls", "username": "studio",
        "password": PASSWORD, "sender": "studio@example.com"})  # fmt: skip
    return a


def _rows(app: Any, sql: str) -> list[sqlite3.Row]:
    db = sqlite3.connect(app.state.auth.path)
    db.row_factory = sqlite3.Row
    try:
        return db.execute(sql).fetchall()
    finally:
        db.close()


def test_sent_only_after_the_server_accepted_and_retried_with_backoff(app: Any) -> None:
    auth = app.state.auth
    FakeSMTP.plan = ["down", "refused"]
    t0 = time.time()
    oid = mailer.queue(auth, "anna@example.com", "Order 7", "Dear Anna, your cover ...", "shop")
    assert oid and not mailer.is_sent(auth, oid)
    (row,) = _rows(app, "SELECT * FROM mail_outbox")
    assert row["status"] == "pending" and row["attempts"] == 1
    assert 55 <= row["next_try"] - t0 <= 65  # limits.mail_retry_first_s
    assert mailer.deliver_due(auth, now=t0 + 30) == {"sent": 0, "retry": 0, "failed": 0}
    # the second try: the server answers but refuses the recipient: still not sent
    assert mailer.deliver_due(auth, now=t0 + 61)["retry"] == 1
    (row,) = _rows(app, "SELECT * FROM mail_outbox")
    assert row["attempts"] == 2 and row["next_try"] - (t0 + 61) == pytest.approx(120, abs=1)
    assert "SMTPRecipientsRefused" in row["last_error"]
    assert mailer.deliver_due(auth, now=t0 + 200)["sent"] == 1
    (row,) = _rows(app, "SELECT * FROM mail_outbox")
    assert row["status"] == "sent" and row["body"] is None  # the text goes once sent
    assert FakeSMTP.accepted == ["anna@example.com"]
    log = [r["result"] for r in _rows(app, "SELECT result FROM mail_log ORDER BY id")]
    assert log == ["error", "error", "sent"]


def test_after_the_last_try_it_fails_visibly_and_can_be_sent_again(app: Any) -> None:
    auth = app.state.auth
    attempts = int(mailer._limits()["attempts"])
    FakeSMTP.plan = ["down"] * attempts
    oid = mailer.queue(auth, "rens@example.com", "3 new questions", "digest text", "digest")
    now = time.time()
    for _ in range(attempts - 1):
        now += 7 * 3600  # past any wait (limits.mail_retry_max_s)
        mailer.deliver_due(auth, now=now)
    c = TestClient(app)
    r0 = c.get("/api/admin/mail/outbox")
    assert r0.status_code == 200 and "failed" in r0.json(), r0.text
    seen = r0.json()
    assert seen["failed"] == 1 and seen["outbox"][0]["status"] == "failed"
    assert seen["outbox"][0]["attempts"] == attempts and seen["outbox"][0]["can_retry"]
    assert "digest text" not in str(seen)  # the overview never shows a text
    assert len(seen["log"]) == attempts
    r = c.post(f"/api/admin/mail/outbox/{oid}/retry")
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert mailer.deliver_due(auth)["sent"] == 1
    assert c.post(f"/api/admin/mail/outbox/{oid}/retry").status_code == 409  # sent: no again
    assert c.post("/api/admin/mail/outbox/999/retry").status_code == 404


def test_the_log_holds_no_password_and_no_text(app: Any) -> None:
    auth = app.state.auth
    FakeSMTP.plan = ["auth"]
    with pytest.raises(smtplib.SMTPAuthenticationError):
        mailer.send(auth, "x@example.com", "Your login code", "code 123456")  # direct, a secret
    (row,) = _rows(app, "SELECT * FROM mail_log")
    assert row["result"] == "error" and row["kind"] == "direct"
    assert PASSWORD not in row["error"] and "SMTPAuthenticationError" in row["error"]
    assert "123456" not in str(dict(row))
    assert "body" not in row.keys()
    # a mail with a secret is never put in the outbox by the callers: nothing kept
    assert _rows(app, "SELECT * FROM mail_outbox") == []


def test_a_reference_is_queued_once_and_its_hook_runs_only_once_accepted(app: Any) -> None:
    auth = app.state.auth
    done: list[str] = []
    mailer.ON_SENT["test-kind"] = lambda db, ref: done.append(ref)
    try:
        FakeSMTP.plan = ["down"]
        assert mailer.queue(auth, "a@example.com", "s", "t", "test-kind", ref="r:1")
        assert mailer.queued(auth, "r:1") and done == []
        assert mailer.queue(auth, "a@example.com", "s", "t", "test-kind", ref="r:1") is None
        mailer.deliver_due(auth, now=time.time() + 120)
        assert done == ["r:1"]
    finally:
        mailer.ON_SENT.pop("test-kind")


def test_the_fit_question_counts_as_sent_only_once_accepted(app: Any) -> None:
    """The shop's review question after delivery (feedback_sent) waits for the server."""
    import json

    from coverapi.shop import _fit_mail_sent

    with sqlite3.connect(app.state.auth.path) as db:
        db.execute(
            "INSERT INTO orders (created, updated, status, email, data, token, total_eur) "
            "VALUES (?, ?, 'shipped', 'anna@example.com', ?, 'tok', 100)",
            (time.time(), time.time() - 30 * 86400, json.dumps({"lang": "nl"})),
        )
    assert mailer.ON_SENT["fit"] is _fit_mail_sent
    app.state.auth.set_setting("shop", {"domain": "shop.example.com",
                                        "fit_mail": {"enabled": True, "days": 14}})  # fmt: skip
    FakeSMTP.plan = ["down"]
    assert app.state.fit_mails() == 1
    sent_at = _rows(app, "SELECT feedback_sent, feedback_token FROM orders")[0]
    assert sent_at["feedback_sent"] is None and sent_at["feedback_token"]
    assert app.state.fit_mails() == 0  # queued once, not again every hour
    mailer.deliver_due(app.state.auth, now=time.time() + 120)
    assert _rows(app, "SELECT feedback_sent FROM orders")[0]["feedback_sent"] is not None
    assert FakeSMTP.accepted == ["anna@example.com"]
