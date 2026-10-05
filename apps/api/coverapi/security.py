"""The app's front door (ADR-047): logins, rights, the admin API, and the safety rules every
request passes before it reaches the rest of the app.

- Every /api request needs a logged-in user, except the health check, the login and the
  one-time password links. The built pages (/, /assets) load without login and show the login.
- Rights: changing anything needs editor or admin; the admin API needs admin; approving a
  drawing needs `can_approve`.
- Requests that change something must come from the app's own pages (the Origin header must
  match the host); the session cookie is SameSite=Strict besides.
- Security headers on every answer (no framing, no sniffing, a content security policy).
- Every change is written to the audit log with the user's name.

With `required=False` (the tests, and a local run without users) everything is allowed and the
user is "local".
"""

from __future__ import annotations

import os
import shutil
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from coverapi import mailer
from coverapi.auth import (
    CODE_MINUTES,
    ROLES,
    SESSION_COOKIE,
    SESSION_DAYS,
    TRUSTED_COOKIE,
    TRUSTED_DAYS,
    Auth,
    AuthError,
    User,
)

OPEN_PATHS = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/verify",
    "/api/auth/invite/",
    "/api/public/",  # the webshop's API: its own key check and limits (webshop.py, ADR-061)
    "/api/shop/",  # the cover webshop: its own limits; payments only through Mollie (ADR-062)
)
TWO_FACTOR_KEY = "two_factor"  # a code by mail after the password (owner, 2 Oct 2026)
CHANGING = ("POST", "PUT", "PATCH", "DELETE")
PUBLIC_URL_KEY = "public_url"
DEFAULT_PUBLIC_URL = "https://covers.suns.nu"
LOCAL = User(0, "local", "Local user", None, "admin", True, True)
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' "
    "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; connect-src 'self'; frame-src 'self'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'self'; form-action 'self'"
)


class LoginRequest(BaseModel):
    username: str
    password: str


class VerifyRequest(BaseModel):
    challenge: str
    code: str
    remember: bool = True


class TwoFactorRequest(BaseModel):
    on: bool


class PasswordRequest(BaseModel):
    password: str


class ChangePassword(BaseModel):
    old: str
    new: str


class NewUserRequest(BaseModel):
    username: str
    name: str = ""
    email: str | None = None
    role: str = "viewer"
    can_approve: bool = False
    send_invite: bool = True  # false: add now, invite later (e.g. all at once for a kickoff)
    note: str = ""


class InviteRequest(BaseModel):
    note: str = ""  # a line of your own at the top of the invitation (the kickoff's date)


NOTE_MAX = 600  # characters of that line


class UserChange(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    can_approve: bool | None = None
    active: bool | None = None


class MailRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    security: str | None = None
    username: str | None = None
    password: str | None = None
    sender: str | None = None


class TestMailRequest(BaseModel):
    to: str


class PublicUrlRequest(BaseModel):
    url: str


def current_user(request: Request) -> User:
    user: User | None = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(401, "please log in")
    return user


def require(request: Request, right: str) -> User:
    user = current_user(request)
    if not user.may(right):
        raise HTTPException(403, f"your account may not {right}")
    return user


def _mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:2]}…@{domain}"


def _address(request: Request) -> str:
    # behind the reverse proxy on this server the real address is in X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and request.client and request.client.host in ("127.0.0.1", "::1"):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def install(app: FastAPI, auth: Auth, required: bool) -> None:
    app.state.auth = auth

    @app.middleware("http")
    async def front_door(request: Request, call_next: Any) -> Response:
        path = request.url.path
        if path.startswith("/api/"):
            if required:
                user = auth.session_user(request.cookies.get(SESSION_COOKIE))
                if user is None and not path.startswith(OPEN_PATHS):
                    return JSONResponse({"detail": "please log in"}, status_code=401)
                if request.method in CHANGING and not path.startswith(
                    ("/api/public/", "/api/shop/")
                ):
                    origin = request.headers.get("origin")
                    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
                    if origin and urlparse(origin).netloc != host:
                        return JSONResponse({"detail": "request from another site"}, 403)
                    if user is not None and not _change_allowed(user, path):
                        return JSONResponse({"detail": "your account may not change this"}, 403)
                request.state.user = user
            else:
                request.state.user = LOCAL
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # the configurator may be shown in an iframe on the webshop addresses set on the admin
        # page (ADR-061); everything else only on our own pages
        shops = [o for o in (auth.setting("embed_origins", []) or []) if o]
        if shops:
            response.headers.setdefault(
                "Content-Security-Policy",
                CSP.replace("frame-ancestors 'self'", "frame-ancestors 'self' " + " ".join(shops)),
            )
        else:
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if _https(request):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        if (
            path.startswith("/api/")
            and request.method in CHANGING
            and response.status_code < 400  # noqa: PLR2004
            and not path.startswith("/api/auth/")
        ):
            u = getattr(request.state, "user", None)
            auth.log(u, f"{request.method} {path}")
        return response

    def _change_allowed(user: User, path: str) -> bool:
        if path.startswith("/api/auth/"):
            return True
        if path.startswith(("/api/admin/cms", "/api/admin/matches")):
            return user.may("edit")  # colleagues edit the site, answer matches (ADR-062, 064)
        if path.startswith("/api/admin/"):
            return user.may("admin")
        if path.endswith("/approve") or path.endswith("/approval-request"):
            return user.may("view")  # the route itself checks can_approve / edit
        return user.may("edit")

    # ---- login
    @app.post("/api/auth/login")
    def login(req: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        """Step 1, the password. Then, unless this browser passed the mailed code in the last
        14 days, step 2: a code by mail (/api/auth/verify)."""
        address = _address(request)
        try:
            user = auth.check_login(req.username, req.password, address)
        except AuthError as exc:
            auth.log(req.username[:64], "login failed", address)
            raise HTTPException(exc.status, str(exc)) from None
        if not _two_factor() or auth.trusted(user.id, request.cookies.get(TRUSTED_COOKIE)):
            user, token = auth._session(user.id, address)
            auth.log(user, "login", address)
            _set_cookie(response, token, request)
            return {"user": user.public()}
        if not user.email:
            auth.log(user, "login refused: no e-mail for the code", address)
            raise HTTPException(
                403, "your account has no e-mail address for the login code: ask an admin"
            )
        cid, code = auth.challenge(user, address)
        try:
            mailer.send(
                auth, user.email, f"Cover Studio login code: {code}",
                f"Hello {user.name},\n\nYour login code for Cover Studio is:\n\n    {code}\n\n"
                f"It is valid for {CODE_MINUTES} minutes. If you did not just log in, change your "
                f"password and tell an admin.\n",
            )  # fmt: skip
        except Exception as exc:  # noqa: BLE001
            auth.log(user, "login code not sent", str(exc))
            raise HTTPException(
                503, "the login code could not be mailed: try again later"
            ) from None
        auth.log(user, "login code sent", address)
        return {"two_factor": True, "challenge": cid, "sent_to": _mask(user.email)}

    @app.post("/api/auth/verify")
    def verify(req: VerifyRequest, request: Request, response: Response) -> dict[str, Any]:
        address = _address(request)
        try:
            user, token = auth.verify(req.challenge, req.code, address)
        except AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        auth.log(user, "login (with code)", address)
        _set_cookie(response, token, request)
        if req.remember:
            device = auth.trust(user.id, request.headers.get("user-agent", ""))
            response.set_cookie(
                TRUSTED_COOKIE, device, max_age=TRUSTED_DAYS * 86400, httponly=True,
                secure=_https(request), samesite="strict", path="/",
            )  # fmt: skip
        return {"user": user.public()}

    def _two_factor() -> bool:
        return bool(auth.setting(TWO_FACTOR_KEY, True)) and mailer.configured(auth)

    def _set_cookie(response: Response, token: str, request: Request) -> None:
        response.set_cookie(
            SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
            secure=_https(request), samesite="strict", path="/",
        )  # fmt: skip

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict[str, Any]:
        auth.logout(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(request: Request) -> dict[str, Any]:
        return {"user": current_user(request).public(), "auth": required}

    @app.post("/api/auth/password")
    def change_password(req: ChangePassword, request: Request) -> dict[str, Any]:
        user = current_user(request)
        if user.id == 0:
            raise HTTPException(400, "no account to change (logins are off)")
        try:
            auth.change_password(user.id, req.old, req.new, request.cookies.get(SESSION_COOKIE))
        except AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        auth.log(user, "password changed")
        return {"ok": True}

    @app.get("/api/auth/invite/{token}")
    def invite_info(token: str) -> dict[str, Any]:
        try:
            u = auth.invite_user(token)
        except AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        return {"username": u.username, "name": u.name}

    @app.post("/api/auth/invite/{token}")
    def set_password(
        token: str, req: PasswordRequest, request: Request, response: Response
    ) -> dict[str, Any]:
        try:
            u = auth.set_password(token, req.password)
            user, session = auth.login(u.username, req.password, _address(request))
        except AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        auth.log(user, "password set")
        _set_cookie(response, session, request)
        return {"user": user.public()}

    # ---- admin
    def _link(token: str) -> str:
        base = str(auth.setting(PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL)).rstrip("/")
        return f"{base}/#/welcome/{token}"

    @app.get("/api/admin/users")
    def users(request: Request) -> dict[str, Any]:
        require(request, "admin")
        until = auth.open_invites()
        return {
            "users": [{**u.public(), "invited_until": until.get(u.id)} for u in auth.users()],
            "roles": list(ROLES),
        }

    @app.post("/api/admin/users")
    def add_user(req: NewUserRequest, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        try:
            u = auth.add_user(req.username, req.name, req.role, req.email, req.can_approve)
        except AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        auth.log(admin, "user added", u.public())
        if not req.send_invite:
            return {"user": u.public(), "link": None, "mailed": False, "mail_problem": None}
        return {"user": u.public(), **_invite(u, admin, req.note)}

    @app.put("/api/admin/users/{user_id}")
    def change_user(user_id: int, req: UserChange, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        changes = {k: v for k, v in req.model_dump().items() if v is not None}
        try:
            u = auth.update_user(user_id, changes)
        except AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        auth.log(admin, "user changed", {"user": u.username, **changes})
        return {"user": u.public()}

    @app.post("/api/admin/users/{user_id}/invite")
    def reinvite(
        user_id: int, request: Request, req: InviteRequest | None = None
    ) -> dict[str, Any]:
        admin = require(request, "admin")
        try:
            u = auth.user(user_id)
        except AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        return _invite(u, admin, (req.note if req else "") or "")

    @app.post("/api/admin/users/invite-all")
    def invite_all(request: Request, req: InviteRequest | None = None) -> dict[str, Any]:
        """Everyone active with an e-mail address who has no password yet (the kickoff)."""
        admin = require(request, "admin")
        if not mailer.configured(auth):
            raise HTTPException(400, "no mail server set (Mail and address)")
        out = []
        for u in auth.users():
            if u.active and u.email and not u.has_password:
                r = _invite(u, admin, (req.note if req else "") or "")
                out.append({"name": u.name, "email": u.email, "mailed": r["mailed"],
                            "mail_problem": r["mail_problem"]})  # fmt: skip
        return {"invited": out}

    def _invite(u: User, admin: User, note: str = "") -> dict[str, Any]:
        from coverapi import invitation
        from coverapi.auth import INVITE_HOURS

        link = _link(auth.invite(u.id))
        base = str(auth.setting(PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL)).rstrip("/")
        days = INVITE_HOURS // 24  # param-ok: hours per day
        mailed, problem = False, None
        if u.email and mailer.configured(auth):
            args = (u.name or u.username, u.username, link, base, admin.name or admin.username,
                    note[:NOTE_MAX], days)  # fmt: skip
            try:
                mailer.send(auth, u.email, invitation.SUBJECT, invitation.text(*args),
                            invitation.html(*args))  # fmt: skip
                mailed = True
            except Exception as exc:  # noqa: BLE001 - show the admin why
                problem = str(exc)
        auth.log(admin, "invite", {"user": u.username, "mailed": mailed})
        return {"link": link, "mailed": mailed, "mail_problem": problem, "days": days}

    @app.get("/api/admin/sessions")
    def sessions(request: Request) -> dict[str, Any]:
        require(request, "admin")
        return {"sessions": auth.sessions()}

    @app.get("/api/admin/audit")
    def audit(request: Request, limit: int = 300) -> dict[str, Any]:
        require(request, "admin")
        return {"audit": auth.audit(min(limit, 2000))}

    @app.get("/api/admin/mail")
    def mail_settings(request: Request) -> dict[str, Any]:
        require(request, "admin")
        return {"mail": mailer.settings(auth), "public_url": auth.setting(
            PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL), "two_factor": bool(auth.setting(
            TWO_FACTOR_KEY, True))}  # fmt: skip

    @app.put("/api/admin/mail")
    def save_mail(req: MailRequest, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        try:
            out = mailer.save(auth, {k: v for k, v in req.model_dump().items() if v is not None})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        auth.log(admin, "mail settings changed", {k: v for k, v in out.items()})
        return {"mail": out}

    @app.post("/api/admin/mail/test")
    def test_mail(req: TestMailRequest, request: Request) -> dict[str, Any]:
        require(request, "admin")
        try:
            mailer.send(auth, req.to, "Cover Studio: test mail", "The mail server works.\n")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"the mail did not go: {exc}") from None
        return {"ok": True}

    @app.put("/api/admin/two-factor")
    def two_factor(req: TwoFactorRequest, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        auth.set_setting(TWO_FACTOR_KEY, req.on)
        auth.log(admin, "login code by mail " + ("on" if req.on else "off"))
        return {"two_factor": req.on}

    @app.put("/api/admin/public-url")
    def public_url(req: PublicUrlRequest, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        if not req.url.startswith("https://"):
            raise HTTPException(400, "the address must start with https://")
        auth.set_setting(PUBLIC_URL_KEY, req.url.rstrip("/"))
        auth.log(admin, "public address changed", req.url)
        return {"public_url": req.url.rstrip("/")}

    @app.get("/api/admin/system")
    def system(request: Request) -> dict[str, Any]:
        require(request, "admin")
        from coverengine import __version__

        store = app.state.store
        disk = shutil.disk_usage(store.root)
        backup = store.root / "last_backup.txt"
        from coverengine.params.registry import repo_root

        root = repo_root()
        history = root.parent / "history.log"  # ~/releases/history.log (ADR-053)
        return {
            "engine": __version__,
            "release": root.name if root.name.startswith("v") else "development",
            "releases": history.read_text().splitlines()[-5:] if history.is_file() else [],
            "models": sum(1 for d in store.models.iterdir() if d.is_dir()),
            "disk_free_gb": round(disk.free / 1e9, 1),
            "disk_total_gb": round(disk.total / 1e9, 1),
            "last_backup": backup.read_text().strip() if backup.is_file() else None,
            "ai": bool(os.environ.get("DEEPSEEK_API_KEY")) or _env_has("DEEPSEEK_API_KEY"),
            "mail": mailer.configured(auth),
            "login_required": required,
            "alert_email": auth.setting("alert_email", "rick@s2dio.industries"),
            "alerts": _tail(store.root / "alerts.log", 15),
            "open_problems": _problems(store.root / "watchdog.json"),
        }

    @app.put("/api/admin/alert-email")
    def alert_email(req: TestMailRequest, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        if "@" not in req.to:
            raise HTTPException(400, "that is not an e-mail address")
        auth.set_setting("alert_email", req.to.strip())
        auth.log(admin, "alert address changed", req.to)
        return {"alert_email": req.to.strip()}


def _tail(path: Any, n: int) -> list[str]:
    return path.read_text(errors="ignore").splitlines()[-n:] if path.is_file() else []


def _problems(path: Any) -> list[str]:
    import json

    if not path.is_file():
        return []
    return [v.get("text", k) for k, v in json.loads(path.read_text() or "{}").items()]


def _env_has(name: str) -> bool:
    from coverengine.params.registry import repo_root

    env = repo_root() / "deploy" / ".env"
    return env.is_file() and any(
        line.startswith(f"{name}=") for line in env.read_text().splitlines()
    )
