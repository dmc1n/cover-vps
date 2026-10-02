"""Users, logins and rights (ADR-047).

The app is reachable from the internet (covers.suns.nu), so every request needs a logged-in
user. Users live in `<data>/app.db` (SQLite) with:

- a role: admin (everything, and the admin page), editor (upload, calculate, change settings),
  viewer (look and download);
- `can_approve`: may approve the definitive drawing of a cover (set by an admin per user);
- a password, stored as a scrypt hash with its own salt; never the password itself.

A login gives a session: a random token in an HttpOnly, SameSite=Strict cookie (Secure when
served over https), kept server side as its hash, valid for SESSION_DAYS. Repeated wrong
passwords lock that user and that address for LOCK_MINUTES. New users and password resets get a
one-time link (INVITE_HOURS valid), sent by mail or copied by the admin. Every login, change and
approval goes into the audit log.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROLES = ("admin", "editor", "viewer")
SESSION_COOKIE = "cover_session"
TRUSTED_COOKIE = "cover_device"  # a device that passed the mailed code (TRUSTED_DAYS)
TRUSTED_DAYS = 14
CODE_MINUTES = 10
CODE_TRIES = 5
CODE_DIGITS = 6
SESSION_DAYS = 14
INVITE_HOURS = 168  # an invitation link is valid for 7 days (the owner, 2 Oct 2026: kickoff)
LOCK_AFTER = 5  # wrong passwords in a row
LOCK_MINUTES = 15
MIN_PASSWORD = 12  # characters
SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}
DAY_S, HOUR_S, MINUTE_S = 86400, 3600, 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  email TEXT,
  role TEXT NOT NULL,
  can_approve INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  pw_hash TEXT,
  created REAL NOT NULL,
  last_login REAL,
  failed INTEGER NOT NULL DEFAULT 0,
  locked_until REAL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created REAL NOT NULL,
  expires REAL NOT NULL,
  address TEXT
);
CREATE TABLE IF NOT EXISTS invites (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  expires REAL NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY,
  time REAL NOT NULL,
  username TEXT,
  action TEXT NOT NULL,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS challenges (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  code_hash TEXT NOT NULL,
  expires REAL NOT NULL,
  tries INTEGER NOT NULL DEFAULT 0,
  address TEXT
);
CREATE TABLE IF NOT EXISTS trusted (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  created REAL NOT NULL,
  expires REAL NOT NULL,
  label TEXT
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS address_failures (
  address TEXT PRIMARY KEY,
  failed INTEGER NOT NULL,
  locked_until REAL
);
"""


class AuthError(Exception):
    """A login or right problem; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class User:
    id: int
    username: str
    name: str
    email: str | None
    role: str
    can_approve: bool
    active: bool
    last_login: float | None = None
    has_password: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "can_approve": self.can_approve,
            "active": self.active,
            "last_login": self.last_login,
            "has_password": self.has_password,
        }

    def may(self, right: str) -> bool:
        if not self.active:
            return False
        if right == "admin":
            return self.role == "admin"
        if right == "edit":
            return self.role in ("admin", "editor")
        if right == "approve":
            return self.can_approve
        return right == "view"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)  # type: ignore[arg-type]
    return f"scrypt${salt.hex()}${key.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, key = stored.split("$")
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)  # type: ignore[arg-type]
    return hmac.compare_digest(got.hex(), key)


def password_problem(password: str, username: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"use at least {MIN_PASSWORD} characters"
    if username.lower() in password.lower():
        return "do not use your user name in the password"
    if len(set(password)) < 6:
        return "use more different characters"
    return None


class Auth:
    def __init__(self, db_path: Path) -> None:
        self.path = db_path
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript(SCHEMA)
        db_path.chmod(0o600)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    # ---- users
    def _user(self, row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            row["id"], row["username"], row["name"], row["email"], row["role"],
            bool(row["can_approve"]), bool(row["active"]), row["last_login"],
            bool(row["pw_hash"]),
        )  # fmt: skip

    def users(self) -> list[User]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM users ORDER BY name").fetchall()
        return [u for u in (self._user(r) for r in rows) if u]

    def open_invites(self) -> dict[int, float]:
        """user id -> until when their unused invitation link works."""
        with self._db() as db:
            rows = db.execute(
                "SELECT user_id, expires FROM invites WHERE used=0 AND expires>?", (time.time(),)
            ).fetchall()
        return {int(r["user_id"]): float(r["expires"]) for r in rows}

    def user(self, user_id: int) -> User:
        with self._db() as db:
            u = self._user(db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
        if u is None:
            raise AuthError("no such user", 404)
        return u

    def add_user(
        self, username: str, name: str, role: str, email: str | None = None,
        can_approve: bool = False,
    ) -> User:  # fmt: skip
        username = username.strip().lower()
        if not username.replace(".", "").replace("-", "").replace("_", "").isalnum():
            raise AuthError("a user name has letters, digits, dots and dashes only", 400)
        if role not in ROLES:
            raise AuthError(f"role must be one of {', '.join(ROLES)}", 400)
        with self._lock, self._db() as db:
            try:
                cur = db.execute(
                    "INSERT INTO users (username, name, email, role, can_approve, created) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (username, name.strip() or username, email or None, role, int(can_approve),
                     time.time()),
                )  # fmt: skip
            except sqlite3.IntegrityError:
                raise AuthError(f"the user name {username!r} is taken", 400) from None
            uid = int(cur.lastrowid or 0)
        return self.user(uid)

    def update_user(self, user_id: int, changes: dict[str, Any]) -> User:
        allowed = {"name", "email", "role", "can_approve", "active"}
        bad = set(changes) - allowed
        if bad:
            raise AuthError(f"cannot change {', '.join(sorted(bad))}", 400)
        if "role" in changes and changes["role"] not in ROLES:
            raise AuthError(f"role must be one of {', '.join(ROLES)}", 400)
        current = self.user(user_id)
        losing_admin = current.role == "admin" and (
            changes.get("role", "admin") != "admin" or changes.get("active") is False
        )
        if losing_admin and sum(u.role == "admin" and u.active for u in self.users()) <= 1:
            raise AuthError("this is the last admin: make someone else admin first", 400)
        with self._lock, self._db() as db:
            for key, value in changes.items():
                if key in ("can_approve", "active"):
                    value = int(bool(value))
                db.execute(f"UPDATE users SET {key}=? WHERE id=?", (value, user_id))  # noqa: S608
            if changes.get("active") is False:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                db.execute("DELETE FROM trusted WHERE user_id=?", (user_id,))
        return self.user(user_id)

    # ---- invites (first password, or a reset)
    def invite(self, user_id: int) -> str:
        """A one-time token to set a password; the old password stops working."""
        token = secrets.token_urlsafe(32)
        with self._lock, self._db() as db:
            db.execute("DELETE FROM invites WHERE user_id=?", (user_id,))
            db.execute(
                "INSERT INTO invites (token_hash, user_id, expires) VALUES (?, ?, ?)",
                (_hash_token(token), user_id, time.time() + INVITE_HOURS * HOUR_S),
            )
            db.execute("UPDATE users SET pw_hash=NULL WHERE id=?", (user_id,))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM trusted WHERE user_id=?", (user_id,))
        return token

    def invite_user(self, token: str) -> User:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM invites WHERE token_hash=? AND used=0 AND expires>?",
                (_hash_token(token), time.time()),
            ).fetchone()
        if row is None:
            raise AuthError("this link is no longer valid: ask an admin for a new one", 400)
        return self.user(int(row["user_id"]))

    def set_password(self, token: str, password: str) -> User:
        user = self.invite_user(token)
        problem = password_problem(password, user.username)
        if problem:
            raise AuthError(problem, 400)
        with self._lock, self._db() as db:
            db.execute(
                "UPDATE users SET pw_hash=?, failed=0, locked_until=NULL WHERE id=?",
                (hash_password(password), user.id),
            )
            db.execute("UPDATE invites SET used=1 WHERE token_hash=?", (_hash_token(token),))
        return user

    def change_password(self, user_id: int, old: str, new: str, keep: str | None = None) -> None:
        """A logged-in user's own change; the user's other sessions end (`keep`: this one)."""
        with self._db() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None or not check_password(old, row["pw_hash"]):
            raise AuthError("the current password is not right", 400)
        problem = password_problem(new, row["username"])
        if problem:
            raise AuthError(problem, 400)
        with self._lock, self._db() as db:
            db.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(new), user_id))
            db.execute(
                "DELETE FROM sessions WHERE user_id=? AND token_hash<>?",
                (user_id, _hash_token(keep) if keep else ""),
            )
            db.execute("DELETE FROM trusted WHERE user_id=?", (user_id,))

    # ---- second step: a code by mail, and devices that passed it (owner, 2 Oct 2026)
    def challenge(self, user: User, address: str) -> tuple[str, str]:
        """A new code for this user (an older one stops working): (challenge id, code)."""
        cid = secrets.token_urlsafe(24)
        code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
        with self._lock, self._db() as db:
            db.execute(
                "DELETE FROM challenges WHERE user_id=? OR expires<?", (user.id, time.time())
            )
            db.execute(
                "INSERT INTO challenges (id, user_id, code_hash, expires, address) "
                "VALUES (?, ?, ?, ?, ?)",
                (_hash_token(cid), user.id, _hash_token(code),
                 time.time() + CODE_MINUTES * MINUTE_S, address),
            )  # fmt: skip
        return cid, code

    def verify(self, cid: str, code: str, address: str) -> tuple[User, str]:
        """The mailed code: a session for the user (the same as a login)."""
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM challenges WHERE id=? AND expires>?", (_hash_token(cid), time.time())
            ).fetchone()
        if row is None:
            raise AuthError("the code has expired: log in again", 400)
        if row["tries"] >= CODE_TRIES:
            raise AuthError("too many wrong codes: log in again", 429)
        if not hmac.compare_digest(_hash_token(code.strip()), row["code_hash"]):
            with self._lock, self._db() as db:
                db.execute("UPDATE challenges SET tries=tries+1 WHERE id=?", (row["id"],))
            raise AuthError("wrong code", 400)
        with self._lock, self._db() as db:
            db.execute("DELETE FROM challenges WHERE id=?", (row["id"],))
        return self._session(int(row["user_id"]), address)

    def trust(self, user_id: int, label: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock, self._db() as db:
            db.execute(
                "INSERT INTO trusted (token_hash, user_id, created, expires, label) "
                "VALUES (?, ?, ?, ?, ?)",
                (_hash_token(token), user_id, time.time(), time.time() + TRUSTED_DAYS * DAY_S,
                 label[:200]),
            )  # fmt: skip
        return token

    def trusted(self, user_id: int, token: str | None) -> bool:
        if not token:
            return False
        with self._db() as db:
            row = db.execute(
                "SELECT 1 FROM trusted WHERE token_hash=? AND user_id=? AND expires>?",
                (_hash_token(token), user_id, time.time()),
            ).fetchone()
        return row is not None

    def forget_devices(self, user_id: int) -> None:
        with self._lock, self._db() as db:
            db.execute("DELETE FROM trusted WHERE user_id=?", (user_id,))

    def _session(self, user_id: int, address: str) -> tuple[User, str]:
        now = time.time()
        token = secrets.token_urlsafe(32)
        with self._lock, self._db() as db:
            db.execute("UPDATE users SET last_login=? WHERE id=?", (now, user_id))
            db.execute(
                "INSERT INTO sessions (token_hash, user_id, created, expires, address) "
                "VALUES (?, ?, ?, ?, ?)",
                (_hash_token(token), user_id, now, now + SESSION_DAYS * DAY_S, address),
            )
        return self.user(user_id), token

    def check_login(self, username: str, password: str, address: str) -> User:
        """The first step: the password (with the lock-outs), without a session yet."""
        return self._password(username, password, address)

    # ---- login and sessions
    def login(self, username: str, password: str, address: str) -> tuple[User, str]:
        user = self._password(username, password, address)
        return self._session(user.id, address)

    def _password(self, username: str, password: str, address: str) -> User:
        now = time.time()
        with self._db() as db:
            arow = db.execute(
                "SELECT * FROM address_failures WHERE address=?", (address,)
            ).fetchone()
            row = db.execute(
                "SELECT * FROM users WHERE username=?", (username.strip().lower(),)
            ).fetchone()
        if arow and arow["locked_until"] and arow["locked_until"] > now:
            raise AuthError("too many wrong passwords: try again in a few minutes", 429)
        if row is not None and row["locked_until"] and row["locked_until"] > now:
            raise AuthError("too many wrong passwords: try again in a few minutes", 429)
        ok = row is not None and bool(row["active"]) and check_password(password, row["pw_hash"])
        if row is None:
            check_password(password, hash_password("timing"))  # the same work either way
        if not ok:
            self._failed(row, address, now)
            raise AuthError("wrong user name or password")
        with self._lock, self._db() as db:
            db.execute("UPDATE users SET failed=0, locked_until=NULL WHERE id=?", (row["id"],))
            db.execute("DELETE FROM address_failures WHERE address=?", (address,))
        user = self._user(row)
        assert user is not None
        return user

    def _failed(self, row: sqlite3.Row | None, address: str, now: float) -> None:
        lock = now + LOCK_MINUTES * MINUTE_S
        with self._lock, self._db() as db:
            if row is not None:
                failed = int(row["failed"]) + 1
                db.execute(
                    "UPDATE users SET failed=?, locked_until=? WHERE id=?",
                    (failed, lock if failed >= LOCK_AFTER else None, row["id"]),
                )
            a = db.execute(
                "SELECT failed FROM address_failures WHERE address=?", (address,)
            ).fetchone()
            n = (int(a["failed"]) if a else 0) + 1
            db.execute(
                "INSERT OR REPLACE INTO address_failures (address, failed, locked_until) "
                "VALUES (?, ?, ?)",
                (address, n, lock if n >= LOCK_AFTER * 2 else None),
            )

    def session_user(self, token: str | None) -> User | None:
        if not token:
            return None
        with self._db() as db:
            row = db.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash=? AND s.expires>?",
                (_hash_token(token), time.time()),
            ).fetchone()
        user = self._user(row)
        return user if user and user.active else None

    def logout(self, token: str | None) -> None:
        if token:
            with self._lock, self._db() as db:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))

    def sessions(self) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT u.username, s.created, s.expires, s.address FROM sessions s "
                "JOIN users u ON u.id = s.user_id WHERE s.expires>? ORDER BY s.created DESC",
                (time.time(),),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- audit log and settings
    def log(self, user: User | str | None, action: str, detail: Any = None) -> None:
        name = user.username if isinstance(user, User) else user
        text = detail if isinstance(detail, str) or detail is None else json.dumps(detail)
        with self._lock, self._db() as db:
            db.execute(
                "INSERT INTO audit (time, username, action, detail) VALUES (?, ?, ?, ?)",
                (time.time(), name, action, text),
            )

    def audit(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT time, username, action, detail FROM audit ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def setting(self, key: str, default: Any = None) -> Any:
        with self._db() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock, self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
