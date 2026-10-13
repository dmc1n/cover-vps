"""`cover-users`: users from the command line, for the first admin and for emergencies.

    COVER_DATA_DIR=~/cover-data uv run cover-users list
    COVER_DATA_DIR=~/cover-data uv run cover-users add rick --name Rick --email rick@... \\
        --role admin --approve
    cover-users add werkplaats --name Werkplaats --role workshop
    COVER_DATA_DIR=~/cover-data uv run cover-users invite rick     # a new password link
    COVER_DATA_DIR=~/cover-data uv run cover-users two-factor off|on|status

The links are printed here; they are as good as a password until used (7 days), so pass them
on privately. With the login code on and no mail server set, nobody can log in with a password
alone (ADR-123): `invite` is the way in for an admin (the link sets a new password and logs in),
and `two-factor off` switches the code off (a scratch copy for tests, or while mail is broken).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from coverapi.auth import ROLES, Auth, AuthError
from coverapi.security import DEFAULT_PUBLIC_URL, PUBLIC_URL_KEY


def main() -> int:
    ap = argparse.ArgumentParser(prog="cover-users")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("add")
    a.add_argument("username")
    a.add_argument("--name", default="")
    a.add_argument("--email")
    a.add_argument("--role", choices=ROLES, default="viewer")
    a.add_argument(
        "--approve", action="store_true", help="approves at the Desk (never with --role workshop)"
    )
    i = sub.add_parser("invite")
    i.add_argument("username")
    t = sub.add_parser("two-factor", help="the login code by mail: on, off or status")
    t.add_argument("state", choices=("on", "off", "status"))
    args = ap.parse_args()
    data = Path(os.environ.get("COVER_DATA_DIR", "data"))
    data.mkdir(parents=True, exist_ok=True)
    auth = Auth(data / "app.db")
    base = str(auth.setting(PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL)).rstrip("/")
    try:
        if args.cmd == "list":
            for u in auth.users():
                flags = ("may approve " if u.can_approve else "") + ("" if u.active else "inactive")
                pw = "password set" if u.has_password else "no password yet"
                print(f"{u.username:<12} {u.name:<16} {u.role:<8} {pw:<16} {u.email or ''} {flags}")
            return 0
        if args.cmd == "two-factor":
            from coverapi import mailer
            from coverapi.security import TWO_FACTOR_KEY

            if args.state != "status":
                auth.set_setting(TWO_FACTOR_KEY, args.state == "on")
                auth.log("cover-users", "login code by mail " + args.state)
            on = bool(auth.setting(TWO_FACTOR_KEY, True))
            mail = mailer.configured(auth)
            state = f"login code: {'on' if on else 'off'}; mail server: "
            print(state + ("set" if mail else "not set"))
            if on and not mail:
                print("logins are refused until a mail server is set (cover-users invite <name>)")
            return 0
        if args.cmd == "add":
            u = auth.add_user(args.username, args.name, args.role, args.email, args.approve)
            auth.log("cover-users", "user added", u.public())
        else:
            found = next((x for x in auth.users() if x.username == args.username.lower()), None)
            if found is None:
                raise AuthError(f"no user {args.username!r}")
            u = found
        token = auth.invite(u.id)
        auth.log("cover-users", "invite", {"user": u.username})
        print(f"{u.username}: {base}/#/welcome/{token}")
        return 0
    except AuthError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
